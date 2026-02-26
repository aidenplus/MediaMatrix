"""
providers/omdb.py 的单元测试
Mock 测试验证数据解析逻辑；集成测试使用真实 API Key 验证接口连通性。
集成测试需要 config/settings.yaml 中配置有效的 omdb.api_key，否则自动跳过。
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from providers.omdb import OMDbProvider
from providers.base import MediaQuery


# ── Mock 数据 ────────────────────────────────────────────────────────────────

def _mock_search_response():
    return {
        "Search": [
            {"Title": "Interstellar", "Year": "2014", "imdbID": "tt0816692", "Type": "movie"},
            {"Title": "Interstellar Wars", "Year": "2016", "imdbID": "tt5083736", "Type": "movie"},
        ],
        "totalResults": "2",
        "Response": "True",
    }


def _mock_detail_response():
    return {
        "Title": "Interstellar",
        "Year": "2014",
        "Genre": "Adventure, Drama, Sci-Fi",
        "Plot": "A farmer and ex-NASA pilot is tasked to find a new planet.",
        "Poster": "https://m.media-amazon.com/images/poster.jpg",
        "imdbRating": "8.7",
        "imdbID": "tt0816692",
        "Type": "movie",
        "Response": "True",
    }


def _mock_not_found_response():
    return {"Response": "False", "Error": "Movie not found!"}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def provider():
    return OMDbProvider(api_key="fake_key")


# ── 单元测试 ──────────────────────────────────────────────────────────────────

class TestOMDbProviderSearch:

    def test_search_returns_results(self, provider, mocker):
        """搜索应返回正确解析的 SearchResult，provider_id 格式为 'movie:imdbID'"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_search_response(), raise_for_status=lambda: None),
        )
        results = provider.search(MediaQuery(title="Interstellar", media_type="movie", year=2014))
        assert len(results) == 2
        assert results[0].provider_id == "movie:tt0816692"
        assert results[0].title == "Interstellar"
        assert results[0].year == 2014
        assert results[0].provider == "omdb"

    def test_search_not_found_returns_empty(self, provider, mocker):
        """无结果时应返回空列表"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_not_found_response(), raise_for_status=lambda: None),
        )
        results = provider.search(MediaQuery(title="不存在的电影", media_type="movie"))
        assert results == []

    def test_search_tv_uses_series_type(self, provider, mocker):
        """剧集搜索应传 type=series"""
        mock_get = mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: {"Response": "False"}, raise_for_status=lambda: None),
        )
        provider.search(MediaQuery(title="Breaking Bad", media_type="tv"))
        call_params = mock_get.call_args[1]["params"]
        assert call_params["type"] == "series"


class TestOMDbProviderGetDetail:

    def test_get_detail_parses_fields(self, provider, mocker):
        """详情应正确解析标题、年份、类型、评分、poster"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_detail_response(), raise_for_status=lambda: None),
        )
        detail = provider.get_detail("movie:tt0816692")
        assert detail.title == "Interstellar"
        assert detail.year == 2014
        assert detail.media_type == "movie"
        assert detail.rating == 8.7
        assert "Adventure" in detail.genres
        assert "Sci-Fi" in detail.genres
        assert detail.poster_url == "https://m.media-amazon.com/images/poster.jpg"
        assert detail.fanart_url is None
        assert detail.logo_url is None
        assert detail.provider == "omdb"
        assert detail.extra["imdb_id"] == "tt0816692"

    def test_get_detail_na_poster_returns_none(self, provider, mocker):
        """Poster 为 N/A 时应返回 None"""
        data = {**_mock_detail_response(), "Poster": "N/A"}
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: data, raise_for_status=lambda: None),
        )
        detail = provider.get_detail("movie:tt0816692")
        assert detail.poster_url is None

    def test_get_detail_na_rating_returns_none(self, provider, mocker):
        """imdbRating 为 N/A 时 rating 应为 None"""
        data = {**_mock_detail_response(), "imdbRating": "N/A"}
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: data, raise_for_status=lambda: None),
        )
        detail = provider.get_detail("movie:tt0816692")
        assert detail.rating is None

    def test_get_detail_not_found_raises(self, provider, mocker):
        """Response=False 时应抛出 ValueError"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_not_found_response(), raise_for_status=lambda: None),
        )
        with pytest.raises(ValueError):
            provider.get_detail("movie:tt9999999")

    def test_parse_year_range(self, provider):
        """剧集年份范围字符串（如 '2013–2014'）应提取起始年份"""
        assert provider._parse_year("2013–2014") == 2013
        assert provider._parse_year("N/A") is None
        assert provider._parse_year(None) is None


# ── 集成测试（需要真实 API Key）──────────────────────────────────────────────

def _load_omdb_key() -> str:
    try:
        import yaml
        settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        with open(settings_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("providers", {}).get("omdb", {}).get("api_key", "")
    except Exception:
        return ""


@pytest.mark.skipif(not _load_omdb_key(), reason="未配置 omdb.api_key，跳过集成测试")
class TestOMDbIntegration:

    @pytest.fixture
    def real_provider(self):
        return OMDbProvider(api_key=_load_omdb_key())

    def test_search_real_movie(self, real_provider):
        """真实搜索：Interstellar 应能返回结果"""
        results = real_provider.search(MediaQuery(title="Interstellar", media_type="movie", year=2014))
        assert len(results) > 0
        assert results[0].provider == "omdb"
        assert results[0].year == 2014

    def test_get_detail_real_movie(self, real_provider):
        """真实详情：应包含完整字段"""
        detail = real_provider.get_detail("movie:tt0816692")
        assert detail.title == "Interstellar"
        assert detail.year == 2014
        assert detail.rating is not None
        assert len(detail.genres) > 0
