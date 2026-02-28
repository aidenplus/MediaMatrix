"""
core/task_queue.py 的单元测试
使用 pytest-mock 模拟所有外部依赖，验证任务队列的核心流程和边界情况。
"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from core.task_queue import TaskQueue, TaskQueueConfig
from core.task_store import ScrapeTask
import core.task_store as task_store
from providers.base import MediaQuery, MediaDetail


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """每个测试使用独立的临时数据库"""
    db_file = tmp_path / "tasks.db"
    monkeypatch.setattr(task_store, "DB_PATH", db_file)
    from core.task_store import init_db
    init_db()


@pytest.fixture
def mock_deps():
    """构造所有依赖的 Mock 对象"""
    identifier = MagicMock()
    scraper = MagicMock()
    scraper.scrape = AsyncMock()
    nfo_writer = MagicMock()
    image_downloader = MagicMock()
    plugin_engine = MagicMock()
    return identifier, scraper, nfo_writer, image_downloader, plugin_engine


@pytest.fixture
def queue(mock_deps):
    identifier, scraper, nfo_writer, image_downloader, plugin_engine = mock_deps
    return TaskQueue(
        identifier=identifier,
        scraper=scraper,
        nfo_writer=nfo_writer,
        image_downloader=image_downloader,
        plugin_engine=plugin_engine,
        config=TaskQueueConfig(
            scrape_mode="overwrite",
            auto_organize=False,
            video_extensions={".mp4", ".mkv"},
        ),
    )


class TestEnqueue:
    def test_enqueue_valid_file_returns_task_id(self, queue):
        """合法视频文件应返回 task_id"""
        task_id = queue.enqueue("/media/movie.mp4")
        assert task_id is not None

    def test_enqueue_non_video_returns_none(self, queue):
        """非视频文件应被过滤，返回 None"""
        assert queue.enqueue("/media/subtitle.srt") is None

    def test_enqueue_missing_only_skips_existing_nfo(self, queue, tmp_path):
        """missing_only 模式下，已有 movie.nfo 的目录应跳过"""
        queue._config.scrape_mode = "missing_only"
        nfo = tmp_path / "movie.nfo"
        nfo.touch()
        result = queue.enqueue(str(tmp_path / "movie.mp4"))
        assert result is None

    def test_enqueue_overwrite_ignores_existing_nfo(self, queue, tmp_path):
        """overwrite 模式下，即使已有 NFO 也应入队"""
        (tmp_path / "movie.nfo").touch()
        result = queue.enqueue(str(tmp_path / "movie.mp4"))
        assert result is not None

    def test_enqueue_skips_file_in_season_dir(self, queue, tmp_path):
        """missing_only 模式下，已在 Season 子目录中的文件应跳过，防止 watchdog 触发循环"""
        queue._config.scrape_mode = "missing_only"
        season_dir = tmp_path / "Season 01"
        season_dir.mkdir()
        result = queue.enqueue(str(season_dir / "show.mp4"))
        assert result is None

    def test_enqueue_overwrite_allows_file_in_season_dir(self, queue, tmp_path):
        """overwrite 模式下，已在 Season 子目录中的文件应重新入队刮削"""
        season_dir = tmp_path / "Season 01"
        season_dir.mkdir()
        result = queue.enqueue(str(season_dir / "show.mp4"))
        assert result is not None


class TestOrganizeMovie:
    def test_creates_standard_dir_and_moves_files(self, queue, tmp_path):
        """电影整理：创建 '电影名 (年份)/' 并移入视频和资产"""
        video = tmp_path / "movie.mp4"
        video.touch()
        (tmp_path / "movie.nfo").touch()
        (tmp_path / "poster.jpg").touch()

        queue._organize_movie(video, "测试电影", 2023)

        target = tmp_path / "测试电影 (2023)"
        assert target.exists()
        assert (target / "movie.mp4").exists()
        assert (target / "movie.nfo").exists()
        assert (target / "poster.jpg").exists()

    def test_renames_dir_when_parent_matches_title(self, queue, tmp_path):
        """情况1：父目录名等于标题（缺少年份），直接重命名目录，添加年份"""
        movie_dir = tmp_path / "爆裂鼓手"
        movie_dir.mkdir()
        video = movie_dir / "爆裂鼓手.mp4"
        video.touch()
        (movie_dir / "movie.nfo").touch()
        (movie_dir / "poster.jpg").touch()

        queue._organize_movie(video, "爆裂鼓手", 2014)

        standard_dir = tmp_path / "爆裂鼓手 (2014)"
        assert standard_dir.exists()
        assert not (tmp_path / "爆裂鼓手").exists()
        # 目录重命名后，原文件应仍在目录内
        assert (standard_dir / "爆裂鼓手.mp4").exists()
        assert (standard_dir / "movie.nfo").exists()
        assert (standard_dir / "poster.jpg").exists()

    def test_skips_if_already_in_standard_dir(self, queue, tmp_path):
        """情况3：父目录名已是标准格式，跳过整理"""
        movie_dir = tmp_path / "测试电影 (2023)"
        movie_dir.mkdir()
        video = movie_dir / "movie.mp4"
        video.touch()

        queue._organize_movie(video, "测试电影", 2023)
        assert video.exists()  # 文件未被移动

    def test_skips_if_target_exists(self, queue, tmp_path):
        """目标目录已存在时跳过，不重复移动"""
        video = tmp_path / "movie.mp4"
        video.touch()
        (tmp_path / "测试电影 (2023)").mkdir()

        queue._organize_movie(video, "测试电影", 2023)
        assert video.exists()  # 文件未被移动


class TestOrganizeTv:
    def test_case1_root_dir_creates_show_dir(self, queue, tmp_path):
        """情况1：文件在媒体根目录，应创建 '剧集名 (年份)/Season 01/'"""
        video = tmp_path / "大宋提刑官S01E01.mp4"
        video.touch()

        queue._organize_tv(video, "大宋提刑官", 2005, 1, 1)

        show_dir = tmp_path / "大宋提刑官 (2005)"
        assert (show_dir / "Season 01" / "大宋提刑官 S01E01.mp4").exists()

    def test_case2_non_standard_dir_renamed(self, queue, tmp_path):
        """情况2：文件在同名非标准目录，目录应被直接重命名为标准格式"""
        show_dir = tmp_path / "大宋提刑官"
        show_dir.mkdir()
        video = show_dir / "大宋提刑官S01E02.mp4"
        video.touch()

        queue._organize_tv(video, "大宋提刑官", 2005, 1, 2)

        standard_dir = tmp_path / "大宋提刑官 (2005)"
        assert standard_dir.exists()
        assert not (tmp_path / "大宋提刑官").exists()
        assert (standard_dir / "Season 01" / "大宋提刑官 S01E02.mp4").exists()

    def test_case3_standard_dir_uses_existing(self, queue, tmp_path):
        """情况3：文件已在标准目录，直接在内创建 Season 子目录"""
        show_dir = tmp_path / "大宋提刑官 (2005)"
        show_dir.mkdir()
        video = show_dir / "大宋提刑官S01E03.mp4"
        video.touch()

        queue._organize_tv(video, "大宋提刑官", 2005, 1, 3)

        assert (show_dir / "Season 01" / "大宋提刑官 S01E03.mp4").exists()

    def test_show_assets_moved_only_once(self, queue, tmp_path):
        """tvshow.nfo 等资产只在首次整理时移入，不重复移动"""
        show_dir = tmp_path / "大宋提刑官 (2005)"
        show_dir.mkdir()
        (show_dir / "tvshow.nfo").touch()  # 已有 NFO

        video = show_dir / "大宋提刑官S01E04.mp4"
        video.touch()
        extra_nfo = show_dir / "tvshow.nfo"

        queue._organize_tv(video, "大宋提刑官", 2005, 1, 4)

        # 原 tvshow.nfo 应仍在 show_dir，不被移走
        assert extra_nfo.exists()


class TestFindShowDir:
    def test_finds_existing_show_dir(self, queue, tmp_path):
        """能找到含 tvshow.nfo 的剧集目录"""
        show_dir = tmp_path / "大宋提刑官 (2005)"
        show_dir.mkdir()
        (show_dir / "tvshow.nfo").touch()

        result = queue._find_show_dir(tmp_path, "大宋提刑官")
        assert result == show_dir

    def test_returns_none_if_not_found(self, queue, tmp_path):
        """不存在匹配目录时返回 None"""
        result = queue._find_show_dir(tmp_path, "不存在的剧集")
        assert result is None

    def test_ignores_dir_without_nfo(self, queue, tmp_path):
        """目录名匹配但无 tvshow.nfo 时不应返回"""
        (tmp_path / "大宋提刑官 (2005)").mkdir()
        result = queue._find_show_dir(tmp_path, "大宋提刑官")
        assert result is None


class TestWorkerProcess:
    @pytest.mark.asyncio
    async def test_successful_movie_scrape(self, mock_deps, tmp_path):
        """完整刮削流程：identify → scrape → nfo → images → after_scraped hook"""
        identifier, scraper, nfo_writer, image_downloader, plugin_engine = mock_deps

        query = MediaQuery(title="测试电影", year=2020, media_type="movie")
        detail = MediaDetail(
            title="测试电影", original_title="Test Movie", year=2020, media_type="movie",
            provider_id="movie:123", overview="简介", genres=["剧情"],
            poster_url="http://example.com/poster.jpg",
            fanart_url=None, logo_url=None, rating=8.0, provider="tmdb",
        )
        identifier.identify.return_value = query
        scraper.scrape.return_value = detail

        q = TaskQueue(
            identifier=identifier, scraper=scraper,
            nfo_writer=nfo_writer, image_downloader=image_downloader,
            plugin_engine=plugin_engine,
            config=TaskQueueConfig(scrape_mode="overwrite", auto_organize=False,
                                   video_extensions={".mp4"}),
        )

        (tmp_path / "movie.mp4").touch()
        task = ScrapeTask(
            task_id="test-id", file_path=str(tmp_path / "movie.mp4"),
            status="pending", created_at=datetime.now().isoformat(),
        )
        await q._process(task)

        identifier.identify.assert_called_once()
        scraper.scrape.assert_called_once_with(query)
        nfo_writer.write_movie_nfo.assert_called_once()
        image_downloader.download_poster.assert_called_once()
        plugin_engine.trigger.assert_called_once_with("after_scraped", media_item={
            "file_path": task.file_path,
            "title": "测试电影",
            "year": 2020,
            "media_type": "movie",
        })

    @pytest.mark.asyncio
    async def test_identify_failure_marks_task_failed(self, mock_deps, tmp_path):
        """identify 返回 None 时，任务应标记为 failed，不继续后续步骤"""
        identifier, scraper, nfo_writer, image_downloader, plugin_engine = mock_deps
        identifier.identify.return_value = None

        q = TaskQueue(
            identifier=identifier, scraper=scraper,
            nfo_writer=nfo_writer, image_downloader=image_downloader,
            plugin_engine=plugin_engine,
            config=TaskQueueConfig(scrape_mode="overwrite", auto_organize=False,
                                   video_extensions={".mp4"}),
        )
        task = ScrapeTask(
            task_id="test-id", file_path=str(tmp_path / "unknown.mp4"),
            status="pending", created_at=datetime.now().isoformat(),
        )
        await q._process(task)

        scraper.scrape.assert_not_called()
        nfo_writer.write_movie_nfo.assert_not_called()

    @pytest.mark.asyncio
    async def test_scrape_failure_marks_task_failed(self, mock_deps, tmp_path):
        """scrape 返回 None 时，任务应标记为 failed，不写 NFO"""
        identifier, scraper, nfo_writer, image_downloader, plugin_engine = mock_deps
        identifier.identify.return_value = MediaQuery(title="未知", media_type="movie")
        scraper.scrape.return_value = None

        q = TaskQueue(
            identifier=identifier, scraper=scraper,
            nfo_writer=nfo_writer, image_downloader=image_downloader,
            plugin_engine=plugin_engine,
            config=TaskQueueConfig(scrape_mode="overwrite", auto_organize=False,
                                   video_extensions={".mp4"}),
        )
        task = ScrapeTask(
            task_id="test-id", file_path=str(tmp_path / "movie.mp4"),
            status="pending", created_at=datetime.now().isoformat(),
        )
        await q._process(task)

        nfo_writer.write_movie_nfo.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_organize_moves_files(self, mock_deps, tmp_path):
        """auto_organize=True 时，刮削成功后应移动文件到子目录"""
        identifier, scraper, nfo_writer, image_downloader, plugin_engine = mock_deps

        video = tmp_path / "movie.mp4"
        video.touch()
        nfo = tmp_path / "movie.nfo"
        nfo.touch()

        query = MediaQuery(title="整理测试", year=2023, media_type="movie")
        detail = MediaDetail(
            title="整理测试", original_title="Organize Test", year=2023, media_type="movie",
            provider_id="movie:999", overview="", genres=[],
            poster_url=None, fanart_url=None, logo_url=None, rating=None, provider="tmdb",
        )
        identifier.identify.return_value = query
        scraper.scrape.return_value = detail

        q = TaskQueue(
            identifier=identifier, scraper=scraper,
            nfo_writer=nfo_writer, image_downloader=image_downloader,
            plugin_engine=plugin_engine,
            config=TaskQueueConfig(scrape_mode="overwrite", auto_organize=True,
                                   video_extensions={".mp4"}),
        )
        task = ScrapeTask(
            task_id="test-id", file_path=str(video),
            status="pending", created_at=datetime.now().isoformat(),
        )
        await q._process(task)

        target_dir = tmp_path / "整理测试 (2023)"
        assert target_dir.exists()
        assert (target_dir / "movie.mp4").exists()
