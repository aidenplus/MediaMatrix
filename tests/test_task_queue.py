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
