import asyncio
import logging
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.identifier import MediaIdentifier
from core.scraper import Scraper
from core.nfo_writer import NFOWriter
from core.image_downloader import ImageDownloader
from core.plugin_engine import PluginEngine
from core.task_store import ScrapeTask, init_db, insert_task, update_status

logger = logging.getLogger(__name__)


@dataclass
class TaskQueueConfig:
    scrape_mode: str = "missing_only"   # missing_only | overwrite
    auto_organize: bool = False
    video_extensions: set[str] = field(default_factory=lambda: {".mkv", ".mp4", ".avi", ".mov", ".ts"})


class TaskQueue:
    """
    异步任务队列，串联完整刮削流程。

    入队来源：
    - POST /api/scan 接口（手动触发）
    - watchdog 文件监控回调（自动触发）

    Worker 流程：
    identify → scrape → write_nfo → download_images → after_scraped hook → [auto_organize]

    异常隔离：单个任务失败只标记为 failed，不影响队列其他任务。
    """

    def __init__(
        self,
        identifier: MediaIdentifier,
        scraper: Scraper,
        nfo_writer: NFOWriter,
        image_downloader: ImageDownloader,
        plugin_engine: PluginEngine,
        config: TaskQueueConfig,
    ):
        self._identifier = identifier
        self._scraper = scraper
        self._nfo_writer = nfo_writer
        self._image_downloader = image_downloader
        self._plugin_engine = plugin_engine
        self._config = config
        self._queue: asyncio.Queue[ScrapeTask] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        init_db()

    def enqueue(self, file_path: str) -> Optional[str]:
        """
        将文件路径推入队列。
        missing_only 模式下，同目录已有 movie.nfo 则跳过。
        返回 task_id，跳过时返回 None。
        """
        path = Path(file_path)

        # 过滤非媒体文件
        if path.suffix.lower() not in self._config.video_extensions:
            return None

        # 已在 Season 子目录中（auto_organize 移动后触发的 watchdog 事件），无条件跳过
        if re.match(r"^Season\s+\d+$", path.parent.name):
            logger.debug("跳过（已在 Season 目录）: %s", path.name)
            return None

        # missing_only 策略：已有 NFO 则跳过
        if self._config.scrape_mode == "missing_only":
            if (path.parent / "movie.nfo").exists() or (path.parent / "tvshow.nfo").exists():
                logger.debug("跳过（已有 NFO）: %s", path.name)
                return None

        task = ScrapeTask(
            task_id=str(uuid.uuid4()),
            file_path=file_path,
            status="pending",
            created_at=datetime.now().isoformat(),
        )
        insert_task(task)
        self._queue.put_nowait(task)
        logger.info("入队: %s", path.name)
        return task.task_id

    def start_worker(self) -> None:
        """启动后台 worker 协程"""
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """等待队列清空后停止 worker"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._worker_task is not None and not self._worker_task.done()

    async def _worker(self) -> None:
        """后台 worker，持续消费队列任务"""
        logger.info("Worker 已启动")
        while True:
            task = await self._queue.get()
            try:
                await self._process(task)
            except Exception as e:
                logger.error("任务失败 [%s]: %s", Path(task.file_path).name, e)
                update_status(task.task_id, "failed", error=str(e))
                self._plugin_engine.trigger("on_error", error=e, media_item={"file_path": task.file_path})
            finally:
                self._queue.task_done()

    async def _process(self, task: ScrapeTask) -> None:
        """执行单个任务的完整刮削流程"""
        file_name = Path(task.file_path).name
        file_path = Path(task.file_path)

        if not file_path.exists():
            logger.debug("文件已不存在，跳过: %s", file_name)
            update_status(task.task_id, "failed", error="文件已不存在（可能已被移动）")
            return

        logger.info("开始处理: %s", file_name)
        update_status(task.task_id, "running")
        output_dir = str(file_path.parent)

        # Step 1: 识别
        query = self._identifier.identify(task.file_path)
        if not query:
            logger.warning("识别失败，无法解析文件类型: %s", file_name)
            update_status(task.task_id, "failed", error="无法识别文件类型")
            return
        logger.debug("识别结果: title=%r, type=%s, year=%s", query.title, query.media_type, query.year)

        # Step 2: 若已有剧集目录（同名 tvshow.nfo），直接移入跳过刮削
        if query.media_type == "tv" and self._config.auto_organize:
            # 在当前目录或上一级目录查找已有剧集目录
            existing_show_dir = (
                self._find_show_dir(file_path.parent, query.title) or
                self._find_show_dir(file_path.parent.parent, query.title)
            )
            if existing_show_dir:
                season_num = query.season or 1
                episode_num = query.episode or 1
                season_dir = existing_show_dir / f"Season {season_num:02d}"
                season_dir.mkdir(exist_ok=True)
                new_name = f"{query.title} S{season_num:02d}E{episode_num:02d}{file_path.suffix}"
                shutil.move(str(file_path), str(season_dir / new_name))
                logger.info("已归入现有剧集目录: %s → %s/Season %02d/%s",
                            file_path.name, existing_show_dir.name, season_num, new_name)
                update_status(task.task_id, "done")
                return

        # Step 2: 抓取元数据
        logger.debug("抓取元数据: %r", query.title)
        detail = await self._scraper.scrape(query)
        if not detail:
            logger.warning("未找到匹配元数据: %r", query.title)
            update_status(task.task_id, "failed", error="未找到匹配的元数据")
            return
        logger.info("抓取成功: %s (%s)", detail.title, detail.year)

        # Step 3: 写 NFO
        if detail.media_type == "movie":
            self._nfo_writer.write_movie_nfo(detail, output_dir)
        elif detail.media_type == "tv":
            self._nfo_writer.write_tv_nfo(detail, output_dir)
        logger.debug("NFO 已生成: %s", output_dir)

        # Step 4: 下载图片
        if detail.poster_url:
            self._image_downloader.download_poster(detail.poster_url, output_dir)
        if detail.fanart_url:
            self._image_downloader.download_fanart(detail.fanart_url, output_dir)
        if detail.logo_url:
            self._image_downloader.download_logo(detail.logo_url, output_dir)
        logger.debug("图片已下载: %s", output_dir)

        # Step 5: 触发插件 after_scraped hook
        self._plugin_engine.trigger("after_scraped", media_item={
            "file_path": task.file_path,
            "title": detail.title,
            "year": detail.year,
            "media_type": detail.media_type,
        })

        # Step 6: 自动整理目录（配置开启时）
        if self._config.auto_organize:
            if detail.media_type == "movie":
                self._organize_movie(file_path, detail.title, detail.year)
            elif detail.media_type == "tv":
                self._organize_tv(file_path, detail.title, detail.year, query.season, query.episode)

        update_status(task.task_id, "done")
        logger.info("完成: %s (%s) [%s]", detail.title, detail.year, task.task_id[:8])

    def _find_show_dir(self, parent: Path, title: str) -> Optional[Path]:
        """在父目录中查找已存在的剧集目录（目录名以 title 开头且含 tvshow.nfo）"""
        if not parent.exists():
            return None
        for d in parent.iterdir():
            if d.is_dir() and d.name.startswith(title) and (d / "tvshow.nfo").exists():
                return d
        return None

    def _organize_movie(self, file_path: Path, title: str, year: Optional[int]) -> None:
        """将视频文件及同目录生成的 NFO/图片移入 '电影名 (年份)/' 子目录。"""
        year_str = f" ({year})" if year else ""
        target_dir = file_path.parent / f"{title}{year_str}"

        if target_dir.exists():
            logger.debug("目标目录已存在，跳过整理: %s", target_dir.name)
            return

        target_dir.mkdir(parents=True)
        moved = []

        shutil.move(str(file_path), str(target_dir / file_path.name))
        moved.append(file_path.name)

        for asset in ["movie.nfo", "poster.jpg", "fanart.jpg", "logo.png"]:
            src = file_path.parent / asset
            if src.exists():
                shutil.move(str(src), str(target_dir / asset))
                moved.append(asset)

        logger.info("目录整理完成: %s → %s/ (%s)", file_path.name, target_dir.name, ", ".join(moved))

    def _organize_tv(self, file_path: Path, title: str, year: Optional[int], season: Optional[int], episode: Optional[int]) -> None:
        """
        将剧集文件整理到标准目录结构，处理三种情况：
        1. 文件在媒体根目录：在根目录创建 '剧集名 (年份)/'
        2. 文件在同名剧集目录（如 '大宋提刑官/'）：在上一级创建标准目录，清理原目录
        3. 文件已在标准目录（如 '大宋提刑官 (2005)/'）：直接在内创建 Season 子目录
        """
        year_str = f" ({year})" if year else ""
        standard_name = f"{title}{year_str}"
        season_num = season or 1
        episode_num = episode or 1
        new_filename = f"{title} S{season_num:02d}E{episode_num:02d}{file_path.suffix}"

        parent = file_path.parent

        # 情况 3：已在标准目录（目录名以 title 开头且含年份括号格式）
        if re.match(rf"^{re.escape(title)}\s*\(\d{{4}}\)$", parent.name):
            show_dir = parent
        # 情况 2：在同名非标准目录（目录名等于 title，不含年份）
        elif parent.name == title:
            show_dir = parent.rename(parent.parent / standard_name)
            file_path = show_dir / file_path.name  # 目录重命名后更新文件路径
            logger.info("目录已重命名: %s → %s", title, standard_name)
        # 情况 1：在媒体根目录或其他目录
        else:
            show_dir = parent / standard_name
            show_dir.mkdir(parents=True, exist_ok=True)

        season_dir = show_dir / f"Season {season_num:02d}"
        season_dir.mkdir(exist_ok=True)

        # 移动剧集根目录资产（仅首次）
        if not (show_dir / "tvshow.nfo").exists():
            for asset in ["tvshow.nfo", "poster.jpg", "fanart.jpg", "logo.png"]:
                src = parent / asset
                if src.exists():
                    shutil.move(str(src), str(show_dir / asset))

        # 移动视频文件并重命名为标准格式
        shutil.move(str(file_path), str(season_dir / new_filename))

        logger.info("目录整理完成: %s → %s/Season %02d/%s",
                    file_path.name, show_dir.name, season_num, new_filename)
