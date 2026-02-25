"""
core/nfo_writer.py 的单元测试
测试 NFOWriter 生成符合 Kodi 标准的 NFO XML 文件。
使用 tempfile 创建临时目录，测试结束后自动清理，无文件系统副作用。
"""
import pytest
import tempfile
import os
from xml.etree import ElementTree as ET
from core.nfo_writer import NFOWriter
from providers.base import MediaDetail


@pytest.fixture
def writer():
    return NFOWriter()


@pytest.fixture
def movie_detail():
    """标准电影元数据 fixture"""
    return MediaDetail(
        provider_id="movie:157336",
        title="星际穿越",
        original_title="Interstellar",
        year=2014,
        media_type="movie",
        overview="A team of explorers travel through a wormhole.",
        genres=["冒险", "科幻", "剧情"],
        poster_url="https://example.com/poster.jpg",
        fanart_url="https://example.com/fanart.jpg",
        logo_url=None,
        rating=8.4,
        provider="tmdb",
    )


@pytest.fixture
def tv_detail():
    """标准剧集元数据 fixture"""
    return MediaDetail(
        provider_id="tv:1399",
        title="权力的游戏",
        original_title="Game of Thrones",
        year=2011,
        media_type="tv",
        overview="Seven noble families fight for control.",
        genres=["剧情", "奇幻"],
        poster_url=None,
        fanart_url=None,
        logo_url=None,
        rating=9.2,
        provider="tmdb",
    )


class TestMovieNFO:
    """电影 NFO 生成测试"""

    def test_creates_nfo_file(self, writer, movie_detail):
        """应在指定目录生成 movie.nfo 文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = writer.write_movie_nfo(movie_detail, tmpdir)
            assert os.path.exists(path)
            assert path.endswith("movie.nfo")

    def test_nfo_root_tag_is_movie(self, writer, movie_detail):
        """电影 NFO 根标签必须是 <movie>（Kodi/Plex 规范）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = writer.write_movie_nfo(movie_detail, tmpdir)
            tree = ET.parse(path)
            assert tree.getroot().tag == "movie"

    def test_nfo_contains_correct_fields(self, writer, movie_detail):
        """NFO 中各字段值应与 MediaDetail 一致"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = writer.write_movie_nfo(movie_detail, tmpdir)
            root = ET.parse(path).getroot()
            assert root.findtext("title") == "星际穿越"
            assert root.findtext("originaltitle") == "Interstellar"
            assert root.findtext("year") == "2014"
            assert root.findtext("rating") == "8.4"
            assert root.findtext("plot") == "A team of explorers travel through a wormhole."

    def test_nfo_contains_all_genres(self, writer, movie_detail):
        """多个 genre 应各自生成独立的 <genre> 标签，顺序保持一致"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = writer.write_movie_nfo(movie_detail, tmpdir)
            root = ET.parse(path).getroot()
            genres = [el.text for el in root.findall("genre")]
            assert genres == ["冒险", "科幻", "剧情"]


class TestTVNFO:
    """剧集 NFO 生成测试"""

    def test_creates_tvshow_nfo(self, writer, tv_detail):
        """剧集 NFO 根标签必须是 <tvshow>，文件名为 tvshow.nfo"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = writer.write_tv_nfo(tv_detail, tmpdir)
            assert path.endswith("tvshow.nfo")
            root = ET.parse(path).getroot()
            assert root.tag == "tvshow"
            assert root.findtext("title") == "权力的游戏"


class TestEpisodeNFO:
    """单集 NFO 生成测试"""

    def test_creates_episode_nfo_with_correct_filename(self, writer, tv_detail):
        """单集 NFO 文件名应为 S{season:02d}E{episode:02d}.nfo 格式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = writer.write_episode_nfo(tv_detail, tmpdir, season=1, episode=9)
            assert path.endswith("S01E09.nfo")

    def test_episode_nfo_contains_season_episode(self, writer, tv_detail):
        """单集 NFO 应包含正确的 <season> 和 <episode> 标签"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = writer.write_episode_nfo(tv_detail, tmpdir, season=3, episode=9)
            root = ET.parse(path).getroot()
            assert root.tag == "episodedetails"
            assert root.findtext("season") == "3"
            assert root.findtext("episode") == "9"
