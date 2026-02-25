import re
from pathlib import Path
from typing import Optional
from providers.base import MediaQuery

# 电影命名格式正则，按优先级排列
MOVIE_PATTERNS = [
    re.compile(r"^(.+?)\s*\((\d{4})\)"),                       # 电影名 (2023)
    re.compile(r"^(.+?)[\.\s_](\d{4})(?:[\.\s_]|$)"),          # Movie.Name.2023 / Movie_Name_2023
]

# 剧集命名格式正则，匹配到即判定为 tv 类型
TV_PATTERNS = [
    re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})"),  # S01E01 / s01e01
    re.compile(r"(\d{1,2})x(\d{1,2})"),          # 1x01
]

MUSIC_EXTENSIONS = {".flac", ".mp3", ".aac", ".wav", ".m4a"}
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".ts"}


class MediaIdentifier:
    """
    从文件路径解析媒体类型、标题和年份，生成 MediaQuery。
    识别优先级：剧集特征（SxxExx）> 电影年份格式 > 兜底（文件名作为标题）
    音乐文件通过扩展名判断，标签读取为 TODO（当前用文件名代替）。
    """

    def identify(self, path: str) -> Optional[MediaQuery]:
        """
        根据文件路径返回 MediaQuery，无法识别的文件类型返回 None。
        """
        p = Path(path)
        suffix = p.suffix.lower()

        if suffix in MUSIC_EXTENSIONS:
            return self._identify_music(p)
        if suffix in VIDEO_EXTENSIONS:
            return self._identify_video(p)
        return None

    def _identify_video(self, path: Path) -> Optional[MediaQuery]:
        name = path.stem  # 去掉扩展名的文件名

        # 优先检测剧集特征，避免将剧集误识别为电影
        for pattern in TV_PATTERNS:
            if pattern.search(name):
                # 取集数标记之前的部分作为剧集标题
                title = pattern.split(name)[0].replace(".", " ").strip()
                return MediaQuery(title=title, media_type="tv")

        # 尝试电影命名格式，提取标题和年份
        for pattern in MOVIE_PATTERNS:
            m = pattern.match(name)
            if m:
                title = m.group(1).replace(".", " ").strip()
                year = int(m.group(2)) if len(m.groups()) > 1 else None
                return MediaQuery(title=title, media_type="movie", year=year)

        # 兜底：无法解析年份，直接用文件名作为标题
        return MediaQuery(title=name.replace(".", " ").strip(), media_type="movie")

    def _identify_music(self, path: Path) -> MediaQuery:
        # TODO: 使用 mutagen 读取 ID3/FLAC 标签获取 title/artist，当前用文件名代替
        return MediaQuery(title=path.stem, media_type="music")
