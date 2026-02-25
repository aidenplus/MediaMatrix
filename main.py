import yaml
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pathlib import Path

from core.logger import setup_logging

from api.routes import router
from core.scanner import MediaScanner
from core.identifier import MediaIdentifier
from core.scraper import Scraper
from core.nfo_writer import NFOWriter
from core.image_downloader import ImageDownloader
from core.plugin_engine import PluginEngine
from core.task_queue import TaskQueue, TaskQueueConfig
from providers.registry import ProviderRegistry
from providers.tmdb import TMDBProvider

# 加载配置文件
CONFIG_PATH = Path(__file__).parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

# 初始化日志（必须在其他模块之前）
setup_logging(
    level=config["logging"]["level"],
    log_file=config["logging"]["file"],
)
logger = logging.getLogger(__name__)

# 注册内置 Provider
# 音乐 Provider（如 MusicBrainz）由对应插件在 on_init hook 中自行注册
registry = ProviderRegistry()
registry.register(TMDBProvider(
    api_key=config["providers"]["tmdb"]["api_key"],
    language=config["providers"]["tmdb"]["language"],
))

# 初始化核心模块
video_extensions = set(config["media"]["video_extensions"])
music_extensions = set(config["media"]["music_extensions"])
identifier = MediaIdentifier(
    video_extensions=video_extensions,
    music_extensions=music_extensions,
)
scraper = Scraper(registry, max_concurrency=config["concurrency"]["max_requests"])
nfo_writer = NFOWriter()
image_downloader = ImageDownloader()

# 加载插件目录下所有 .py / .so 插件，并触发 on_init hook
plugin_engine = PluginEngine()
plugin_engine.load_plugins(config["plugins"]["dir"])
plugin_engine.trigger("on_init", config=config)

# 初始化任务队列
task_queue = TaskQueue(
    identifier=identifier,
    scraper=scraper,
    nfo_writer=nfo_writer,
    image_downloader=image_downloader,
    plugin_engine=plugin_engine,
    config=TaskQueueConfig(
        scrape_mode=config["media"]["scrape_mode"],
        auto_organize=config["media"]["auto_organize"],
        video_extensions=video_extensions,
    ),
)


def on_file(path: str) -> None:
    """文件扫描器回调：将新增文件推入任务队列"""
    task_queue.enqueue(path)


# 初始化文件扫描器，注册所有媒体根目录
scanner = MediaScanner(on_file=on_file)
for path in config["media"]["paths"]:
    scanner.add_path(path)

# 创建 FastAPI 应用
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MediaMatrix 启动中...")
    task_queue.start_worker()
    scanner.start()
    existing = scanner.scan_existing()
    enqueued = sum(1 for path in existing if task_queue.enqueue(path) is not None)
    skipped = len(existing) - enqueued
    logger.info("全量扫描完成: 发现 %d 个文件，入队 %d 个，跳过 %d 个", len(existing), enqueued, skipped)
    logger.info("MediaMatrix 已就绪")
    yield
    logger.info("MediaMatrix 关闭中...")
    await task_queue.stop()
    scanner.stop()
    image_downloader.close()
    logger.info("MediaMatrix 已关闭")


app = FastAPI(title="MediaMatrix", version="1.0.0", lifespan=lifespan)
app.state.task_queue = task_queue  # type: ignore[attr-defined]
app.include_router(router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config["app"]["host"],
        port=config["app"]["port"],
        reload=False,
    )
