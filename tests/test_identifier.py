"""
core/identifier.py 的单元测试
测试 MediaIdentifier 从文件路径解析媒体类型、标题和年份的能力。
所有测试均为纯逻辑测试，无外部依赖。
"""
import pytest
from core.identifier import MediaIdentifier


@pytest.fixture
def identifier():
    return MediaIdentifier()


class TestMovieIdentification:
    """电影文件名识别测试"""

    def test_standard_format_with_year(self, identifier):
        """识别 '电影名 (年份)' 格式，年份应被正确提取"""
        q = identifier.identify("/media/Movies/Interstellar (2014)/Interstellar.2014.mkv")
        assert q.media_type == "movie"
        assert q.year == 2014

    def test_dot_separated_with_year(self, identifier):
        """识别 'Movie.Name.2023' 点分隔格式，年份应被正确提取"""
        q = identifier.identify("/media/Avatar.The.Way.Of.Water.2022.mkv")
        assert q.media_type == "movie"
        assert q.year == 2022

    def test_complex_filename(self, identifier):
        """识别带有画质、编码等附加信息的复杂文件名，年份仍应被正确提取"""
        q = identifier.identify(
            "/Volumes/影音库/电影/Avatar.The.Way.Of.Water.2022.PROPER.Bluray.2160p.AV1.mkv"
        )
        assert q is not None
        assert q.media_type == "movie"
        assert q.year == 2022


class TestTVIdentification:
    """剧集文件名识别测试"""

    def test_standard_s01e01(self, identifier):
        """识别标准 S01E01 大写格式"""
        q = identifier.identify("/media/TV/Breaking.Bad.S01E01.mkv")
        assert q.media_type == "tv"

    def test_lowercase_s01e01(self, identifier):
        """识别 s01e01 小写格式"""
        q = identifier.identify("/media/TV/game.of.thrones.s03e09.mkv")
        assert q.media_type == "tv"

    def test_1x01_format(self, identifier):
        """识别 1x01 替代格式"""
        q = identifier.identify("/media/TV/Show.1x01.mkv")
        assert q.media_type == "tv"


class TestMusicIdentification:
    """音乐文件识别测试（通过扩展名判断）"""

    def test_flac_file(self, identifier):
        """FLAC 文件应识别为 music 类型"""
        q = identifier.identify("/media/Music/Artist/Album/01.Track.flac")
        assert q.media_type == "music"

    def test_mp3_file(self, identifier):
        """MP3 文件应识别为 music 类型"""
        q = identifier.identify("/media/Music/song.mp3")
        assert q.media_type == "music"


class TestUnsupportedFiles:
    """不支持的文件类型应返回 None"""

    def test_subtitle_file_returns_none(self, identifier):
        """.srt 字幕文件不在支持列表中，应返回 None"""
        q = identifier.identify("/media/Movies/movie.srt")
        assert q is None

    def test_image_file_returns_none(self, identifier):
        """.jpg 图片文件不在支持列表中，应返回 None"""
        q = identifier.identify("/media/Movies/poster.jpg")
        assert q is None
