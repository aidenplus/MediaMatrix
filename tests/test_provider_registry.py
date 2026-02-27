"""
providers/registry.py 的单元测试
测试 ProviderRegistry 的注册、排序和 priority 覆盖逻辑。
"""
import pytest
from unittest.mock import MagicMock
from providers.registry import ProviderRegistry
from providers.base import BaseProvider, MediaQuery, MediaDetail, SearchResult


def _make_provider(name: str, priority: int, media_types: list[str] = None) -> BaseProvider:
    """构造一个最小可用的 Mock Provider"""
    p = MagicMock(spec=BaseProvider)
    p.name = name
    p.priority = priority
    p.media_types = media_types or ["movie", "tv"]
    return p


class TestProviderRegistryOrdering:

    def test_providers_sorted_by_priority_on_register(self):
        """注册顺序不影响最终排序，应始终按 priority 升序排列"""
        registry = ProviderRegistry()
        registry.register(_make_provider("omdb", priority=3))
        registry.register(_make_provider("tmdb", priority=1))
        registry.register(_make_provider("tvdb", priority=2))

        providers = registry.get_providers_for_type("movie")
        assert [p.name for p in providers] == ["tmdb", "tvdb", "omdb"]

    def test_priority_override_via_main_pattern(self):
        """模拟 main.py 中读取配置并覆盖 priority 的完整流程"""
        registry = ProviderRegistry()

        tmdb = _make_provider("tmdb", priority=1)
        registry.register(tmdb)

        tvdb = _make_provider("tvdb", priority=2)
        registry.register(tvdb)

        # 模拟用户配置 llm priority: 2，与 tvdb 冲突
        llm = _make_provider("llm", priority=99)
        llm_cfg = {"priority": 2}
        if "priority" in llm_cfg:
            llm.priority = llm_cfg["priority"]
        registry.register(llm)

        # priority 相同时，tvdb 先注册排在 llm 前（Python sort 稳定）
        providers = registry.get_providers_for_type("movie")
        names = [p.name for p in providers]
        assert names[0] == "tmdb"
        assert names[1] == "tvdb"   # 同优先级，先注册的在前
        assert names[2] == "llm"

    def test_llm_before_tvdb_when_priority_lower(self):
        """llm priority=2，tvdb priority=3 时，llm 应排在 tvdb 之前"""
        registry = ProviderRegistry()
        registry.register(_make_provider("tmdb", priority=1))

        tvdb = _make_provider("tvdb", priority=2)
        tvdb_cfg = {"priority": 3}
        if "priority" in tvdb_cfg:
            tvdb.priority = tvdb_cfg["priority"]
        registry.register(tvdb)

        llm = _make_provider("llm", priority=99)
        llm_cfg = {"priority": 2}
        if "priority" in llm_cfg:
            llm.priority = llm_cfg["priority"]
        registry.register(llm)

        providers = registry.get_providers_for_type("movie")
        assert [p.name for p in providers] == ["tmdb", "llm", "tvdb"]

    def test_no_priority_override_uses_default(self):
        """未配置 priority 时使用 Provider 类默认值"""
        registry = ProviderRegistry()
        registry.register(_make_provider("tmdb", priority=1))
        registry.register(_make_provider("llm", priority=99))

        providers = registry.get_providers_for_type("movie")
        assert providers[0].name == "tmdb"
        assert providers[1].name == "llm"

    def test_only_matching_media_type_returned(self):
        """get_providers_for_type 只返回支持该 media_type 的 Provider"""
        registry = ProviderRegistry()
        registry.register(_make_provider("tmdb", priority=1, media_types=["movie", "tv"]))
        registry.register(_make_provider("music_provider", priority=2, media_types=["music"]))

        assert len(registry.get_providers_for_type("movie")) == 1
        assert len(registry.get_providers_for_type("music")) == 1
        assert registry.get_providers_for_type("movie")[0].name == "tmdb"
        assert registry.get_providers_for_type("music")[0].name == "music_provider"
