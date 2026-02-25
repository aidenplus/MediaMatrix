"""
core/plugin_engine.py 的单元测试
测试插件加载、Hook 触发和异常隔离机制。
使用内联定义的测试插件类，避免依赖外部文件。
"""
import pytest
import tempfile
import os
from core.plugin_engine import BasePlugin, PluginEngine


class GoodPlugin(BasePlugin):
    """行为正常的测试插件，记录所有被调用的 Hook"""
    name = "good_plugin"
    version = "1.0.0"
    called_hooks = []

    def on_init(self, config: dict):
        self.called_hooks.append("on_init")

    def after_scraped(self, media_item: dict):
        self.called_hooks.append("after_scraped")

    def on_error(self, error: Exception, media_item: dict):
        self.called_hooks.append("on_error")


class BrokenPlugin(BasePlugin):
    """on_init 会抛出异常的测试插件，用于验证异常隔离"""
    name = "broken_plugin"

    def on_init(self, config: dict):
        raise RuntimeError("plugin exploded")

    def after_scraped(self, media_item: dict):
        pass

    def on_error(self, error: Exception, media_item: dict):
        pass


class TestPluginEngine:

    def test_trigger_calls_correct_hook(self):
        """trigger('on_init') 应调用插件的 on_init 方法"""
        engine = PluginEngine()
        plugin = GoodPlugin()
        engine._plugins.append(plugin)

        engine.trigger("on_init", config={})
        assert "on_init" in plugin.called_hooks

    def test_trigger_after_scraped(self):
        """trigger('after_scraped') 应调用插件的 after_scraped 方法"""
        engine = PluginEngine()
        plugin = GoodPlugin()
        engine._plugins.append(plugin)

        engine.trigger("after_scraped", media_item={"title": "test"})
        assert "after_scraped" in plugin.called_hooks

    def test_broken_plugin_does_not_crash_engine(self):
        """单个插件抛出异常时，引擎不应崩溃"""
        engine = PluginEngine()
        engine._plugins.append(BrokenPlugin())
        engine.trigger("on_init", config={})  # 不应抛出异常

    def test_broken_plugin_does_not_affect_other_plugins(self):
        """异常插件不应阻止后续插件的 Hook 被调用"""
        engine = PluginEngine()
        engine._plugins.append(BrokenPlugin())
        good = GoodPlugin()
        engine._plugins.append(good)

        engine.trigger("on_init", config={})
        assert "on_init" in good.called_hooks

    def test_load_plugins_from_directory(self):
        """从目录动态加载 .py 插件，应自动发现并实例化 BasePlugin 子类"""
        plugin_code = """
from core.plugin_engine import BasePlugin

class DynamicPlugin(BasePlugin):
    name = "dynamic"
    def on_init(self, config): pass
    def after_scraped(self, media_item): pass
    def on_error(self, error, media_item): pass
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = os.path.join(tmpdir, "dynamic_plugin.py")
            with open(plugin_file, "w") as f:
                f.write(plugin_code)

            engine = PluginEngine()
            engine.load_plugins(tmpdir)
            assert len(engine._plugins) == 1
            assert engine._plugins[0].name == "dynamic"

    def test_empty_plugin_dir_loads_nothing(self):
        """空目录不应加载任何插件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = PluginEngine()
            engine.load_plugins(tmpdir)
            assert len(engine._plugins) == 0
