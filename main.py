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
from core.llm_identifier import LLMIdentifier
from core.scraper import Scraper
from core.nfo_writer import NFOWriter
from core.image_downloader import ImageDownloader
from core.plugin_engine import PluginEngine
from core.task_queue import TaskQueue, TaskQueueConfig
from providers.registry import ProviderRegistry
from providers.tmdb import TMDBProvider
from providers.tvdb import TVDbProvider
from providers.omdb import OMDbProvider
from providers.llm import LLMProvider

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

tmdb_cfg = config["providers"]["tmdb"]
tmdb = TMDBProvider(api_key=tmdb_cfg["api_key"], language=tmdb_cfg["language"])
if "priority" in tmdb_cfg:
    tmdb.priority = tmdb_cfg["priority"]
registry.register(tmdb)

# TVDb 为可选数据源，api_key 为空时跳过注册
tvdb_cfg = config.get("providers", {}).get("tvdb", {})
tvdb_key = tvdb_cfg.get("api_key", "")
if tvdb_key:
    tvdb = TVDbProvider(api_key=tvdb_key, language=tvdb_cfg.get("language", "zho"))
    if "priority" in tvdb_cfg:
        tvdb.priority = tvdb_cfg["priority"]
    registry.register(tvdb)

# OMDb 为可选数据源，api_key 为空时跳过注册
omdb_cfg = config.get("providers", {}).get("omdb", {})
omdb_key = omdb_cfg.get("api_key", "")
if omdb_key:
    omdb = OMDbProvider(api_key=omdb_key)
    if "priority" in omdb_cfg:
        omdb.priority = omdb_cfg["priority"]
    registry.register(omdb)

# LLM 为可选兜底数据源，api_key 为空时跳过注册
llm_cfg = config.get("providers", {}).get("llm", {})
llm_key = llm_cfg.get("api_key", "")
if llm_key:
    llm = LLMProvider(
        api_key=llm_key,
        model=llm_cfg.get("model", "gpt-4o-mini"),
        base_url=llm_cfg.get("base_url", "https://api.openai.com/v1"),
    )
    if "priority" in llm_cfg:
        llm.priority = llm_cfg["priority"]
    registry.register(llm)

# 初始化核心模块
video_extensions = set(config["media"]["video_extensions"])
music_extensions = set(config["media"]["music_extensions"])

identifier_cfg = config.get("identifier", {})
if identifier_cfg.get("engine") == "llm":
    # LLM identifier：优先用 identifier 自己的配置，留空则复用 providers.llm
    id_api_key = identifier_cfg.get("api_key") or llm_key
    id_base_url = identifier_cfg.get("base_url") or llm_cfg.get("base_url", "https://api.openai.com/v1")
    id_model = identifier_cfg.get("model") or llm_cfg.get("model", "gpt-4o-mini")
    identifier = LLMIdentifier(
        api_key=id_api_key,
        model=id_model,
        base_url=id_base_url,
        video_extensions=video_extensions,
        music_extensions=music_extensions,
    )
    logger.info("文件名识别引擎: LLM (%s)", id_model)
else:
    identifier = MediaIdentifier(
        video_extensions=video_extensions,
        music_extensions=music_extensions,
    )
    logger.info("文件名识别引擎: regex")
scraper = Scraper(registry, max_concurrency=config["concurrency"]["max_requests"])
nfo_writer = NFOWriter()
image_downloader = ImageDownloader()

# 加载插件目录下所有 .py / .so 插件，并触发 on_init hook
plugin_engine = PluginEngine()
plugin_engine.load_plugins(config["plugins"]["dir"])
plugin_engine.trigger("on_init", config=config, registry=registry)

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
        media_paths=set(config["media"]["paths"]),
    ),
)


def on_file(path: str) -> None:
    """文件扫描器回调：将新增文件推入任务队列"""
    task_queue.enqueue(path)


# 初始化文件扫描器，注册所有媒体根目录
scanner = MediaScanner(
    on_file=on_file,
    media_extensions=video_extensions | music_extensions,
    poll_interval=config["media"].get("poll_interval", 5),
)
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
    if hasattr(identifier, "close"):
        identifier.close()
    logger.info("MediaMatrix 已关闭")


app = FastAPI(title="MediaMatrix", version="1.0.0", lifespan=lifespan)
app.state.task_queue = task_queue  # type: ignore[attr-defined]
app.include_router(router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config["app"]["host"],
        port=config["app"]["port"],
        reload=False,
    )
