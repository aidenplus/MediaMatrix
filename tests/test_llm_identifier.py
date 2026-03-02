"""
core/llm_identifier.py 的集成测试
使用和 test_identifier.py 相同的测试用例，验证 LLMIdentifier 的识别质量。
需要真实 LLM API 调用，凭证从 config/settings.yaml 读取。
"""
import pytest
import yaml
from pathlib import Path
from core.llm_identifier import LLMIdentifier

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"


@pytest.fixture(scope="module")
def identifier():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    id_cfg = config.get("identifier", {})
    llm_cfg = config.get("providers", {}).get("llm", {})

    api_key = id_cfg.get("api_key") or llm_cfg.get("api_key", "")
    base_url = id_cfg.get("base_url") or llm_cfg.get("base_url", "https://api.openai.com/v1")
    model = id_cfg.get("model") or llm_cfg.get("model", "gpt-4o-mini")

    if not api_key:
        pytest.skip("未配置 LLM API Key，跳过 LLM Identifier 集成测试")

    inst = LLMIdentifier(api_key=api_key, base_url=base_url, model=model)
    yield inst
    inst.close()


class TestMovieIdentification:
    """电影文件名识别测试"""

    def test_standard_format_with_year(self, identifier):
        q = identifier.identify("/media/Movies/Interstellar (2014)/Interstellar.2014.mkv")
        assert q.media_type == "movie"
        assert q.year == 2014

    def test_dot_separated_with_year(self, identifier):
        q = identifier.identify("/media/Avatar.The.Way.Of.Water.2022.mkv")
        assert q.media_type == "movie"
        assert q.year == 2022

    def test_complex_filename(self, identifier):
        q = identifier.identify(
            "/Volumes/影音库/电影/Avatar.The.Way.Of.Water.2022.PROPER.Bluray.2160p.AV1.mkv"
        )
        assert q is not None
        assert q.media_type == "movie"
        assert q.year == 2022


class TestTVIdentification:
    """剧集文件名识别测试"""

    def test_standard_s01e01(self, identifier):
        q = identifier.identify("/media/TV/Breaking.Bad.S01E01.mkv")
        assert q.media_type == "tv"
        assert q.season == 1
        assert q.episode == 1

    def test_lowercase_s01e01(self, identifier):
        q = identifier.identify("/media/TV/game.of.thrones.s03e09.mkv")
        assert q.media_type == "tv"
        assert q.season == 3
        assert q.episode == 9

    def test_1x01_format(self, identifier):
        q = identifier.identify("/media/TV/Show.1x01.mkv")
        assert q.media_type == "tv"
        assert q.season == 1
        assert q.episode == 1

    def test_chinese_season_and_episode(self, identifier):
        q = identifier.identify("/media/大宋提刑官第二季第五集.mp4")
        assert q.media_type == "tv"
        assert q.title == "大宋提刑官"
        assert q.season == 2
        assert q.episode == 5

    def test_chinese_part_and_episode(self, identifier):
        q = identifier.identify("/media/大宋提刑官第一部-第三集.mp4")
        assert q.media_type == "tv"
        assert q.title == "大宋提刑官"
        assert q.season == 1
        assert q.episode == 3

    def test_chinese_episode_only(self, identifier):
        q = identifier.identify("/media/大宋提刑官第12集.mp4")
        assert q.media_type == "tv"
        assert q.title == "大宋提刑官"
        assert q.season == 1
        assert q.episode == 12

    def test_chinese_episode_word_number(self, identifier):
        q = identifier.identify("/media/大宋提刑官第三集.mp4")
        assert q.media_type == "tv"
        assert q.season == 1
        assert q.episode == 3

    def test_mixed_writes_for_season_and_episode(self, identifier):
        q = identifier.identify("/media/大宋提刑官S01第四集.MP4")
        assert q.media_type == "tv"
        assert q.season == 1
        assert q.episode == 4

    def test_e_only_format(self, identifier):
        q = identifier.identify("/media/电视剧/大宋提刑官/大宋提刑官E01.MP4")
        assert q.media_type == "tv"
        assert q.title == "大宋提刑官"
        assert q.season == 1
        assert q.episode == 1

    def test_ep_format(self, identifier):
        q = identifier.identify("/media/TV/SomeShow.EP12.mkv")
        assert q.media_type == "tv"
        assert q.season == 1
        assert q.episode == 12

    def test_e_format_does_not_match_inline_letter(self, identifier):
        """Se7en 不应被识别为剧集"""
        q = identifier.identify("/media/Movies/Se7en.mkv")
        assert q.media_type == "movie"


class TestMusicIdentification:
    """音乐文件识别测试（通过扩展名判断，不调用 LLM）"""

    def test_flac_file(self, identifier):
        q = identifier.identify("/media/Music/Artist/Album/01.Track.flac")
        assert q.media_type == "music"

    def test_mp3_file(self, identifier):
        q = identifier.identify("/media/Music/song.mp3")
        assert q.media_type == "music"


class TestUnsupportedFiles:
    """不支持的文件类型应返回 None（不调用 LLM）"""

    def test_subtitle_file_returns_none(self, identifier):
        q = identifier.identify("/media/Movies/movie.srt")
        assert q is None

    def test_image_file_returns_none(self, identifier):
        q = identifier.identify("/media/Movies/poster.jpg")
        assert q is None
