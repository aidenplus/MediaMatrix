import yaml
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pathlib import Path

from api.routes import router
from core.scanner import MediaScanner
from core.identifier import MediaIdentifier
from core.scraper import Scraper
from core.nfo_writer import NFOWriter
from core.image_downloader import ImageDownloader
from core.plugin_engine import PluginEngine
from providers.registry import ProviderRegistry
from providers.tmdb import TMDBProvider

# 加载配置文件
CONFIG_PATH = Path(__file__).parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

# 注册内置 Provider
# 音乐 Provider（如 MusicBrainz）由对应插件在 on_init hook 中自行注册
registry = ProviderRegistry()
registry.register(TMDBProvider(
    api_key=config["providers"]["tmdb"]["api_key"],
    language=config["providers"]["tmdb"]["language"],
))

# 初始化核心模块
# scrape_mode 将在 ImageDownloader 实现 missing_only/overwrite 策略时使用
scrape_mode = config["media"]["scrape_mode"]
identifier = MediaIdentifier()
scraper = Scraper(registry, max_concurrency=config["concurrency"]["max_requests"])
nfo_writer = NFOWriter()
image_downloader = ImageDownloader()

# 加载插件目录下所有 .py / .so 插件，并触发 on_init hook
plugin_engine = PluginEngine()
plugin_engine.load_plugins(config["plugins"]["dir"])
plugin_engine.trigger("on_init", config=config)


def on_file(path: str):
    """
    文件扫描器回调：识别文件类型后推入处理流程。
    TODO: 改为推入异步任务队列，完整流程为：
          scrape -> nfo_writer -> image_downloader -> plugin after_scraped hook
    """
    query = identifier.identify(path)
    if query:
        print(f"[Scanner] detected: {path} -> {query}")


# 初始化文件扫描器，注册所有媒体根目录
scanner = MediaScanner(on_file=on_file)
for path in config["media"]["paths"]:
    scanner.add_path(path)

# 创建 FastAPI 应用
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: 启动文件监控（取消注释以启用）
    # scanner.start()
    yield
    # shutdown: 应用关闭时释放资源
    scanner.stop()
    image_downloader.close()


app = FastAPI(title="MediaMatrix", version="1.0.0", lifespan=lifespan)
app.include_router(router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config["app"]["host"],
        port=config["app"]["port"],
        reload=False,
    )
