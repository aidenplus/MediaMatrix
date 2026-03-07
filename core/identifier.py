import re
from pathlib import Path
from typing import Optional
from providers.base import MediaQuery

# 中文数字映射
_CN_NUM = {"零":0,"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,
           "十一":11,"十二":12,"十三":13,"十四":14,"十五":15,"十六":16,"十七":17,"十八":18,"十九":19,"二十":20}

def _parse_num(s: str) -> int:
    """将阿拉伯数字或中文数字字符串转为整数"""
    if s.isdigit():
        return int(s)
    return _CN_NUM.get(s, 1)


# 电影命名格式正则，按优先级排列
MOVIE_PATTERNS = [
    re.compile(r"^(.+?)\s*\((\d{4})\)"),                       # 电影名 (2023)
    re.compile(r"^(.+?)[\.\s_](\d{4})(?:[\.\s_]|$)"),          # Movie.Name.2023 / Movie_Name_2023
]

_CN = r"[零一二三四五六七八九十百]+"
_NUM = rf"(?:\d+|{_CN})"

# 剧集命名格式正则，每条正则需有两个捕获组：(季号, 集号)
# 季号或集号无法提取时用 None 表示
TV_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 英文格式
    (re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})"),                              "se"),  # S01E01
    (re.compile(r"(\d{1,2})x(\d{1,2})"),                                      "se"),  # 1x01
    # 混合格式：S01第四集（英文季号 + 中文集号，需在纯季号匹配之前）
    (re.compile(rf"[Ss](\d{{1,2}})[^Ee\d]*第\s*({_NUM})\s*[集话]"),           "se"),
    (re.compile(r"[Ss](\d{1,2})(?![Ee\d])"),                                  "s"),   # S01（无集号）
    # 仅集号：E01 / EP01（无 S 前缀，季号默认1；负向前瞻防止匹配 Se7en 等词内字母）
    (re.compile(r"(?<![a-zA-Z])[Ee][Pp]?(\d{1,3})"),                         "e"),   # E01 / EP01
    # 中文格式：第X季/部 + 第X集/话（支持中文数字，中间允许任意分隔符）
    (re.compile(rf"第\s*({_NUM})\s*[季部][^第]*第\s*({_NUM})\s*[集话]"),      "se"),
    # 只有集号：第X集/话（季号默认1）
    (re.compile(rf"第\s*({_NUM})\s*[集话]"),                                  "e"),
]

MUSIC_EXTENSIONS = {".flac", ".mp3", ".aac", ".wav", ".m4a"}
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov",}


class MediaIdentifier:
    """
    从文件路径解析媒体类型、标题和年份，生成 MediaQuery。
    识别优先级：剧集特征（SxxExx）> 电影年份格式 > 兜底（文件名作为标题）
    音乐文件通过扩展名判断，标签读取为 TODO（当前用文件名代替）。

    video_extensions 和 music_extensions 可由外部传入，默认使用内置集合。
    """

    def __init__(
        self,
        video_extensions: set[str] = None,
        music_extensions: set[str] = None,
    ):
        self._video_extensions = video_extensions or VIDEO_EXTENSIONS
        self._music_extensions = music_extensions or MUSIC_EXTENSIONS

    def identify(self, path: str) -> Optional[MediaQuery]:
        """
        根据文件路径返回 MediaQuery，无法识别的文件类型返回 None。
        """
        p = Path(path)
        suffix = p.suffix.lower()

        if suffix in self._music_extensions:
            return self._identify_music(p)
        if suffix in self._video_extensions:
            return self._identify_video(p)
        return None

    def _identify_video(self, path: Path) -> Optional[MediaQuery]:
        name = path.stem  # 去掉扩展名的文件名

        # 优先检测剧集特征，避免将剧集误识别为电影
        for pattern, mode in TV_PATTERNS:
            m = pattern.search(name)
            if m:
                title = pattern.split(name)[0].replace(".", " ").strip(" -._")
                if mode == "se":
                    season, episode = _parse_num(m.group(1)), _parse_num(m.group(2))
                elif mode == "s":  # 只有季号，集号为 None
                    season, episode = _parse_num(m.group(1)), None
                else:  # 只有集号，季号默认 1
                    season, episode = 1, _parse_num(m.group(1))
                return MediaQuery(title=title, media_type="tv", season=season, episode=episode,
                                  extra={"filename": name})

        # 尝试电影命名格式，提取标题和年份
        for pattern in MOVIE_PATTERNS:
            m = pattern.match(name)
            if m:
                title = m.group(1).replace(".", " ").strip()
                year = int(m.group(2)) if len(m.groups()) > 1 else None
                return MediaQuery(title=title, media_type="movie", year=year,
                                  extra={"filename": name})

        # 兜底：无法解析年份，直接用文件名作为标题
        return MediaQuery(title=name.replace(".", " ").strip(), media_type="movie",
                          extra={"filename": name})

    def _identify_music(self, path: Path) -> MediaQuery:
        # TODO: 使用 mutagen 读取 ID3/FLAC 标签获取 title/artist，当前用文件名代替
        return MediaQuery(title=path.stem, media_type="music")
