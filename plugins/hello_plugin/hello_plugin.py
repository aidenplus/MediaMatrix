import logging
from core.plugin_engine import BasePlugin

logger = logging.getLogger(__name__)


class HelloPlugin(BasePlugin):
    name = "hello_plugin"
    version = "1.0.0"

    def on_init(self, config: dict, **kwargs) -> None:
        logger.info("[HelloPlugin] 已加载，当前刮削模式: %s", config["media"]["scrape_mode"])

    def after_scraped(self, media_item: dict) -> None:
        logger.info("[HelloPlugin] 刮削完成: %s (%s)", media_item["title"], media_item["year"])

    def on_error(self, error: Exception, media_item: dict) -> None:
        logger.warning("[HelloPlugin] 刮削失败: %s，原因: %s", media_item["file_path"], error)
