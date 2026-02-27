import importlib.util
import json
import logging
from abc import ABC
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

    插件可以是单个 .py/.so 文件，也可以是文件夹插件（Bundle 格式）。
    """
    name: str = ""
    version: str = "0.0.1"

    def on_init(self, config: dict) -> None:
        """系统启动时调用，config 为完整的 settings.yaml 内容"""
        pass

    def after_scraped(self, media_item: dict) -> None:
        """刮削完成后触发，media_item 包含文件路径、标题、年份、媒体类型"""
        pass

    def on_error(self, error: Exception, media_item: dict) -> None:
        """刮削失败时触发，error 为异常对象，media_item 为触发失败的媒体信息"""
        pass


class PluginEngine:
    """
    插件加载与 Hook 调度引擎。

    支持两种插件格式：
    - 单文件：plugins/my_plugin.py 或 plugins/my_plugin.so
    - 文件夹（Bundle）：plugins/my_plugin/my_plugin.py 或 plugins/my_plugin/my_plugin.so
      文件夹插件须包含 manifest.json，且 id 字段不能为空。

    模块隔离：
    - 单文件插件模块名为文件 stem（如 my_plugin）
    - 文件夹插件模块名为 plugins.<目录名>，通过 submodule_search_locations 隔离，
      不修改全局 sys.path，插件内部须使用相对导入。

    异常隔离：
    - 单个插件加载或 Hook 执行抛出异常时，只打印日志，不影响其他插件和主流程。
    """

    def __init__(self):
        self._plugins: list[BasePlugin] = []

    def load_plugins(self, plugin_dir: str) -> None:
        """扫描并加载目录下所有插件，跳过以 _ 开头的文件/目录"""
        plugin_path = Path(plugin_dir)
        if not plugin_path.exists():
            logger.warning("插件目录不存在，跳过加载: %s", plugin_dir)
            return
        for path in plugin_path.iterdir():
            if path.name.startswith("_"):
                continue
            if path.is_dir():
                self._load_bundle(path)
            elif path.suffix in (".py", ".so"):
                self._load_one(path, module_name=path.stem)

    def _load_bundle(self, bundle_dir: Path) -> None:
        """加载文件夹插件，校验 manifest.json 后定位同名入口文件"""
        manifest_path = bundle_dir / "manifest.json"
        if not manifest_path.exists():
            logger.warning("插件缺少 manifest.json，跳过: %s", bundle_dir.name)
            return

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("manifest.json 解析失败，跳过 %s: %s", bundle_dir.name, e)
            return

        if not manifest.get("id"):
            logger.warning("manifest.json 缺少 id 字段，跳过: %s", bundle_dir.name)
            return

        # 按优先级查找入口文件：.so 优先（生产），.py 兜底（开发）
        entry: Path | None = None
        for suffix in (".so", ".py"):
            candidate = bundle_dir / f"{bundle_dir.name}{suffix}"
            if candidate.exists():
                entry = candidate
                break

        if entry is None:
            logger.warning("插件入口文件不存在，跳过: %s", bundle_dir.name)
            return

        module_name = f"plugins.{bundle_dir.name}"
        self._load_one(entry, module_name=module_name, search_path=bundle_dir)

    def _load_one(self, path: Path, module_name: str, search_path: Path = None) -> None:
        """加载单个插件文件，自动发现并实例化其中的 BasePlugin 子类"""
        try:
            spec = importlib.util.spec_from_file_location(
                module_name,
                str(path),
                submodule_search_locations=[str(search_path)] if search_path else None,
            )
            if spec is None or spec.loader is None:
                logger.warning("无法创建模块 spec，跳过: %s", path.name)
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error("插件加载失败 %s: %s", path.name, e)
            return

        found = False
        for attr in dir(module):
            obj = getattr(module, attr)
            if (isinstance(obj, type)
                    and issubclass(obj, BasePlugin)
                    and obj is not BasePlugin):
                self._plugins.append(obj())
                logger.info("已加载插件: %s v%s", obj.name, obj.version)
                found = True

        if not found:
            logger.warning("插件文件中未发现 BasePlugin 子类: %s", path.name)

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
