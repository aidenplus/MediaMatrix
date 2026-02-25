from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent
from providers.base import MediaDetail


class NFOWriter:
    """
    生成符合 Kodi 标准的 NFO 文件（XML 格式）。
    Plex 和 Infuse 均支持读取此格式的本地元数据。

    文件命名规范：
    - 电影: movie.nfo（与视频文件同目录）
    - 剧集: tvshow.nfo（剧集根目录）
    - 单集: S01E01.nfo（与视频文件同目录）
    """

    def write_movie_nfo(self, detail: MediaDetail, output_dir: str) -> str:
        """生成电影 NFO，根标签为 <movie>"""
        root = Element("movie")
        self._fill_common(root, detail)
        return self._save(root, Path(output_dir) / "movie.nfo")

    def write_tv_nfo(self, detail: MediaDetail, output_dir: str) -> str:
        """生成剧集 NFO，根标签为 <tvshow>"""
        root = Element("tvshow")
        self._fill_common(root, detail)
        return self._save(root, Path(output_dir) / "tvshow.nfo")

    def write_episode_nfo(self, detail: MediaDetail, output_dir: str,
                          season: int, episode: int) -> str:
        """生成单集 NFO，根标签为 <episodedetails>，文件名格式 S01E01.nfo"""
        root = Element("episodedetails")
        self._fill_common(root, detail)
        SubElement(root, "season").text = str(season)
        SubElement(root, "episode").text = str(episode)
        filename = f"S{season:02d}E{episode:02d}.nfo"
        return self._save(root, Path(output_dir) / filename)

    def _fill_common(self, root: Element, detail: MediaDetail) -> None:
        """填充电影/剧集/单集共用的元数据字段"""
        SubElement(root, "title").text = detail.title
        SubElement(root, "originaltitle").text = detail.original_title
        SubElement(root, "year").text = str(detail.year) if detail.year else ""
        SubElement(root, "plot").text = detail.overview
        SubElement(root, "rating").text = str(detail.rating) if detail.rating else ""
        for genre in detail.genres:
            SubElement(root, "genre").text = genre

    def _save(self, root: Element, path: Path) -> str:
        """格式化缩进并写入文件，返回文件绝对路径"""
        indent(root, space="  ")
        tree = ElementTree(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(str(path), encoding="utf-8", xml_declaration=True)
        return str(path)
