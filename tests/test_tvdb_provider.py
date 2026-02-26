"""
providers/tvdb.py 的单元测试
Mock 测试验证数据解析逻辑；集成测试使用真实 API Key 验证接口连通性。
集成测试需要 config/settings.yaml 中配置有效的 tvdb.api_key，否则自动跳过。
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from providers.tvdb import TVDbProvider
from providers.base import MediaQuery

# ── Mock 数据 ────────────────────────────────────────────────────────────────

def _mock_login_response():
    return {"data": {"token": "fake_token"}}


def _mock_search_response():
    return {
        "data": [
            {"tvdb_id": "76107", "name": "大宋提刑官", "first_air_time": "2005-01-01"},
            {"tvdb_id": "99999", "name": "大宋提刑官 II", "first_air_time": "2006-01-01"},
        ]
    }


def _mock_detail_response():
    return {
        "data": {
            "id": 76107,
            "name": "大宋提刑官",
            "firstAired": "2005-01-10",
            "overview": "English overview",
            "score": 8.5,
            "genres": [{"name": "剧情"}, {"name": "历史"}],
            "artworks": [
                {"type": 2, "image": "https://artworks.thetvdb.com/poster.jpg"},      # poster
                {"type": 3, "image": "https://artworks.thetvdb.com/background.jpg"},  # background
                {"type": 5, "image": "https://artworks.thetvdb.com/logo.png"},        # clearlogo
            ],
            "translations": {
                "nameTranslations": [
                    {"language": "zho", "name": "大宋提刑官"},
                    {"language": "eng", "name": "Judge of Song Dynasty"},
                ],
                "overviewTranslations": [
                    {"language": "zho", "overview": "宋慈断案的故事"},
                    {"language": "eng", "overview": "English overview"},
                ],
            },
        }
    }


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def provider():
    """使用假 API Key 初始化，不发起真实请求"""
    p = TVDbProvider(api_key="fake_key")
    p._token = "fake_token"  # 跳过 login 流程
    return p


# ── 单元测试 ──────────────────────────────────────────────────────────────────

class TestTVDbProviderSearch:

    def test_search_returns_results(self, provider, mocker):
        """搜索应返回正确解析的 SearchResult，provider_id 格式为 'tv:id'"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_search_response(), raise_for_status=lambda: None),
        )
        results = provider.search(MediaQuery(title="大宋提刑官", media_type="tv"))
        assert len(results) == 2
        assert results[0].provider_id == "tv:76107"
        assert results[0].title == "大宋提刑官"
        assert results[0].year == 2005
        assert results[0].provider == "tvdb"

    def test_search_empty_returns_empty_list(self, provider, mocker):
        """无结果时应返回空列表"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: {"data": []}, raise_for_status=lambda: None),
        )
        results = provider.search(MediaQuery(title="不存在的剧集", media_type="tv"))
        assert results == []

    def test_search_null_data_returns_empty_list(self, provider, mocker):
        """data 为 null 时应返回空列表，不抛出异常"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: {"data": None}, raise_for_status=lambda: None),
        )
        results = provider.search(MediaQuery(title="test", media_type="tv"))
        assert results == []


class TestTVDbProviderGetDetail:

    def test_get_detail_parses_fields(self, provider, mocker):
        """详情应正确解析标题、年份、类型、评分等字段"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_detail_response(), raise_for_status=lambda: None),
        )
        detail = provider.get_detail("tv:76107")
        assert detail.title == "大宋提刑官"
        assert detail.original_title == "大宋提刑官"
        assert detail.year == 2005
        assert detail.media_type == "tv"
        assert detail.rating == 8.5
        assert "剧情" in detail.genres
        assert detail.provider == "tvdb"
        assert detail.extra["tvdb_id"] == "76107"

    def test_get_detail_prefers_chinese_translation(self, provider, mocker):
        """有中文翻译时应优先使用中文 overview"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_detail_response(), raise_for_status=lambda: None),
        )
        detail = provider.get_detail("tv:76107")
        assert detail.overview == "宋慈断案的故事"

    def test_get_detail_poster_url(self, provider, mocker):
        """应能从 artworks 中提取 poster URL"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_detail_response(), raise_for_status=lambda: None),
        )
        detail = provider.get_detail("tv:76107")
        assert detail.poster_url is not None


class TestTVDbLogin:

    def test_token_cached_after_first_call(self, mocker):
        """token 获取后应缓存，不重复调用 login 接口"""
        p = TVDbProvider(api_key="fake_key")
        mock_post = mocker.patch.object(
            p._client, "post",
            return_value=MagicMock(json=lambda: _mock_login_response(), raise_for_status=lambda: None),
        )
        mocker.patch.object(
            p._client, "get",
            return_value=MagicMock(json=lambda: _mock_search_response(), raise_for_status=lambda: None),
        )
        p.search(MediaQuery(title="test", media_type="tv"))
        p.search(MediaQuery(title="test", media_type="tv"))
        assert mock_post.call_count == 1  # login 只调用一次


# ── 集成测试（需要真实 API Key）──────────────────────────────────────────────

def _load_tvdb_key() -> str:
    """从 settings.yaml 读取 tvdb api_key，不存在或为空返回空字符串"""
    try:
        import yaml
        settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        with open(settings_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("providers", {}).get("tvdb", {}).get("api_key", "")
    except Exception:
        return ""


@pytest.mark.skipif(not _load_tvdb_key(), reason="未配置 tvdb.api_key，跳过集成测试")
class TestTVDbIntegration:

    @pytest.fixture
    def real_provider(self):
        key = _load_tvdb_key()
        import yaml
        settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        with open(settings_path) as f:
            cfg = yaml.safe_load(f)
        lang = cfg.get("providers", {}).get("tvdb", {}).get("language", "zho")
        return TVDbProvider(api_key=key, language=lang)

    def test_search_real_tv(self, real_provider):
        """真实搜索：大宋提刑官应能返回结果"""
        results = real_provider.search(MediaQuery(title="大宋提刑官", media_type="tv"))
        assert len(results) > 0
        assert results[0].provider == "tvdb"
        assert results[0].year is not None

    def test_get_detail_real_tv(self, real_provider):
        """真实详情：搜索后取第一条结果的详情，应包含完整字段"""
        results = real_provider.search(MediaQuery(title="大宋提刑官", media_type="tv"))
        assert results, "搜索无结果，无法继续测试详情"
        detail = real_provider.get_detail(results[0].provider_id)
        assert detail.title
        assert detail.year is not None
        assert detail.media_type == "tv"
        assert detail.provider == "tvdb"
