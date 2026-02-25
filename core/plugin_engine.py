import importlib.util
import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    """
    所有插件的抽象基类，定义三个生命周期 Hook。
    插件开发者继承此类并实现所需的 Hook 方法即可。

    Hook 说明：
    - on_init:       系统启动时调用一次，适合做初始化（如加载模型、建立连接）
    - after_scraped: 每次刮削完成后调用，适合做后处理（如字幕生成、通知推送）
    - on_error:      刮削失败时调用，适合做报警（如发送通知）

    插件可以是 .py 源码文件，也可以是 Cython 编译后的 .so 二进制文件。
    """
    name: str = ""
    version: str = "0.0.1"

    def on_init(self, config: dict) -> None:
        """系统启动时调用，config 为完整的 settings.yaml 内容"""
        pass

    def after_scraped(self, media_item: dict) -> None:
        """刮削完成后触发，media_item 包含 MediaDetail 的序列化数据"""
        pass

    def on_error(self, error: Exception, media_item: dict) -> None:
        """刮削失败时触发，error 为异常对象，media_item 为触发失败的媒体信息"""
        pass


class PluginEngine:
    """
    插件加载与 Hook 调度引擎。

    加载机制：
    - 扫描指定目录下所有 .py 和 .so 文件
    - 通过 importlib 动态加载模块，自动发现 BasePlugin 子类并实例化
    - .py 和 .so 使用相同的加载路径，对上层透明

    异常隔离：
    - 单个插件的 Hook 抛出异常时，只打印日志，不影响其他插件和主流程
    """

    def __init__(self):
        self._plugins: list[BasePlugin] = []

    def load_plugins(self, plugin_dir: str) -> None:
        """扫描并加载目录下所有 .py 和 .so 插件，跳过以 _ 开头的文件"""
        plugin_path = Path(plugin_dir)
        if not plugin_path.exists():
            logger.warning("插件目录不存在，跳过加载: %s", plugin_dir)
            return
        for path in plugin_path.iterdir():
            if path.suffix in (".py", ".so") and not path.name.startswith("_"):
                self._load_one(path)

    def _load_one(self, path: Path) -> None:
        """加载单个插件文件，自动发现并实例化其中的 BasePlugin 子类"""
        spec = importlib.util.spec_from_file_location(path.stem, str(path))
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for attr in dir(module):
            obj = getattr(module, attr)
            if (isinstance(obj, type)
                    and issubclass(obj, BasePlugin)
                    and obj is not BasePlugin):
                self._plugins.append(obj())
                logger.info("已加载插件: %s v%s", obj.name, obj.version)

    def trigger(self, hook_name: str, **kwargs) -> None:
        """
        触发指定 Hook，依次调用所有插件的对应方法。
        单个插件抛出异常时记录日志并继续，不中断其他插件。
        """
        for plugin in self._plugins:
            handler = getattr(plugin, hook_name, None)
            if callable(handler):
                try:
                    handler(**kwargs)
                except Exception as e:
                    logger.error("插件 %s hook %s 异常: %s", plugin.name, hook_name, e)
