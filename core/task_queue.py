import asyncio
import logging
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
        logger.info("开始处理: %s", file_name)
        update_status(task.task_id, "running")
        file_path = Path(task.file_path)
        output_dir = str(file_path.parent)

        # Step 1: 识别
        query = self._identifier.identify(task.file_path)
        if not query:
            logger.warning("识别失败，无法解析文件类型: %s", file_name)
            update_status(task.task_id, "failed", error="无法识别文件类型")
            return
        logger.debug("识别结果: title=%r, type=%s, year=%s", query.title, query.media_type, query.year)

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

        # Step 6: 自动整理目录（仅电影，且配置开启）
        if self._config.auto_organize and detail.media_type == "movie":
            self._organize(file_path, detail.title, detail.year)

        update_status(task.task_id, "done")
        logger.info("完成: %s (%s) [%s]", detail.title, detail.year, task.task_id[:8])

    def _organize(self, file_path: Path, title: str, year: Optional[int]) -> None:
        """
        将视频文件及同目录生成的 NFO/图片移入 '电影名 (年份)/' 子目录。
        目标目录已存在时跳过，避免覆盖。
        """
        year_str = f" ({year})" if year else ""
        target_dir = file_path.parent / f"{title}{year_str}"

        if target_dir.exists():
            return

        target_dir.mkdir(parents=True)

        # 移动视频文件
        shutil.move(str(file_path), str(target_dir / file_path.name))

        # 移动同目录生成的资产文件
        for asset in ["movie.nfo", "tvshow.nfo", "poster.jpg", "fanart.jpg", "logo.png"]:
            src = file_path.parent / asset
            if src.exists():
                shutil.move(str(src), str(target_dir / asset))
