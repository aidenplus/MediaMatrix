"""
providers/tmdb.py 的单元测试
测试 TMDBProvider 的搜索结果解析、详情解析和 provider_id 格式。
所有 HTTP 请求均通过 pytest-mock 的 mocker 进行 Mock，不发起真实网络请求。
"""
import pytest
from unittest.mock import MagicMock
from providers.tmdb import TMDBProvider
from providers.base import MediaQuery


@pytest.fixture
def provider():
    """使用假 API Key 初始化 Provider，不会发起真实请求"""
    return TMDBProvider(api_key="fake_key")


def _mock_search_response(media_type: str):
    """构造 TMDB search 接口的模拟响应数据"""
    if media_type == "movie":
        return {
            "results": [
                {"id": 157336, "title": "Interstellar", "release_date": "2014-11-05"},
            ]
        }
    return {
        "results": [
            {"id": 1399, "name": "Game of Thrones", "first_air_date": "2011-04-17"},
        ]
    }


def _mock_detail_response(media_type: str):
    """构造 TMDB detail 接口的模拟响应数据"""
    if media_type == "movie":
        return {
            "id": 157336,
            "title": "星际穿越",
            "original_title": "Interstellar",
            "release_date": "2014-11-05",
            "overview": "A team of explorers...",
            "genres": [{"name": "冒险"}, {"name": "科幻"}],
            "poster_path": "/poster.jpg",
            "backdrop_path": "/backdrop.jpg",
            "vote_average": 8.4,
        }
    return {
        "id": 1399,
        "name": "权力的游戏",
        "original_name": "Game of Thrones",
        "first_air_date": "2011-04-17",
        "overview": "Seven noble families...",
        "genres": [{"name": "剧情"}, {"name": "奇幻"}],
        "poster_path": "/poster_tv.jpg",
        "backdrop_path": "/backdrop_tv.jpg",
        "vote_average": 9.2,
    }


class TestTMDBProviderSearch:
    """search() 方法测试：验证搜索结果解析和 provider_id 格式"""

    def test_search_movie_returns_results(self, provider, mocker):
        """电影搜索应返回正确解析的 SearchResult，provider_id 格式为 'movie:id'"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_search_response("movie"), raise_for_status=lambda: None),
        )
        results = provider.search(MediaQuery(title="Interstellar", media_type="movie", year=2014))
        assert len(results) == 1
        assert results[0].provider_id == "movie:157336"
        assert results[0].title == "Interstellar"
        assert results[0].year == 2014
        assert results[0].provider == "tmdb"

    def test_search_tv_returns_results(self, provider, mocker):
        """剧集搜索应返回正确解析的 SearchResult，provider_id 格式为 'tv:id'"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_search_response("tv"), raise_for_status=lambda: None),
        )
        results = provider.search(MediaQuery(title="Game of Thrones", media_type="tv"))
        assert len(results) == 1
        assert results[0].provider_id == "tv:1399"
        assert results[0].year == 2011

    def test_search_empty_returns_empty_list(self, provider, mocker):
        """TMDB 无结果时应返回空列表，不抛出异常"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: {"results": []}, raise_for_status=lambda: None),
        )
        results = provider.search(MediaQuery(title="不存在的电影", media_type="movie"))
        assert results == []


class TestTMDBProviderGetDetail:
    """get_detail() 方法测试：验证元数据解析和接口路由"""

    def test_get_detail_movie(self, provider, mocker):
        """电影详情应正确解析所有字段，extra 中应包含 tmdb_id"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_detail_response("movie"), raise_for_status=lambda: None),
        )
        mocker.patch.object(provider, "_fetch_logo", return_value=None)
        detail = provider.get_detail("movie:157336")
        assert detail.title == "星际穿越"
        assert detail.original_title == "Interstellar"
        assert detail.year == 2014
        assert detail.media_type == "movie"
        assert detail.rating == 8.4
        assert "冒险" in detail.genres
        assert detail.poster_url == "https://image.tmdb.org/t/p/original/poster.jpg"
        assert detail.extra["tmdb_id"] == "157336"

    def test_get_detail_tv(self, provider, mocker):
        """剧集详情应正确解析 name/original_name 字段"""
        mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_detail_response("tv"), raise_for_status=lambda: None),
        )
        mocker.patch.object(provider, "_fetch_logo", return_value=None)
        detail = provider.get_detail("tv:1399")
        assert detail.title == "权力的游戏"
        assert detail.media_type == "tv"
        assert detail.year == 2011

    def test_provider_id_format_parsed_correctly(self, provider, mocker):
        """provider_id 中的 media_type 应被正确解析并路由到对应 API 端点"""
        mock_get = mocker.patch.object(
            provider._client, "get",
            return_value=MagicMock(json=lambda: _mock_detail_response("movie"), raise_for_status=lambda: None),
        )
        mocker.patch.object(provider, "_fetch_logo", return_value=None)
        provider.get_detail("movie:157336")
        call_url = mock_get.call_args[0][0]
        assert "/movie/157336" in call_url
