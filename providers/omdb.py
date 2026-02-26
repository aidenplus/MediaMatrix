from typing import Optional
import httpx
from .base import BaseProvider, MediaQuery, SearchResult, MediaDetail


class OMDbProvider(BaseProvider):
    """
    OMDb (Open Movie Database) 数据源适配器，基于 IMDB 数据。
    支持电影和剧集，作为 TMDB 的备用数据源。
    注意：OMDb 只提供英文元数据，无中文翻译。

    API 文档: https://www.omdbapi.com/
    限速说明: 免费 tier 每天 1000 次请求。
    """
    name = "omdb"
    media_types = ["movie", "tv"]
    priority = 3  # TMDB(1) 和 TVDb(2) 均失败后的最终备用

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.omdbapi.com/"
        self._client = httpx.Client(
            timeout=15,
            params={"apikey": api_key},
        )

    def search(self, query: MediaQuery) -> list[SearchResult]:
        """调用 OMDb ?s= 接口搜索媒体"""
        type_map = {"movie": "movie", "tv": "series"}
        params = {
            "s": query.title,
            "type": type_map.get(query.media_type, "movie"),
        }
        if query.year:
            params["y"] = query.year

        resp = self._client.get(self.base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("Response") != "True":
            return []

        return [
            SearchResult(
                provider_id=f"{query.media_type}:{item['imdbID']}",
                title=item.get("Title", ""),
                year=self._parse_year(item.get("Year")),
                media_type=query.media_type,
                provider=self.name,
            )
            for item in data.get("Search", [])
        ]

    def get_detail(self, provider_id: str) -> MediaDetail:
        """根据 provider_id（格式: movie:tt0816692）获取完整元数据"""
        media_type, imdb_id = provider_id.split(":", 1)

        resp = self._client.get(self.base_url, params={"i": imdb_id})
        resp.raise_for_status()
        data = resp.json()

        if data.get("Response") != "True":
            raise ValueError(f"OMDb 未找到: {imdb_id}")

        # 评分取 imdbRating
        rating = None
        try:
            rating = float(data.get("imdbRating", "N/A"))
        except (ValueError, TypeError):
            pass

        # 类型是逗号分隔字符串
        genres = [g.strip() for g in data.get("Genre", "").split(",") if g.strip() and g.strip() != "N/A"]

        # poster 为 N/A 时置 None，否则替换为高分辨率版本
        poster = data.get("Poster")
        poster_url = self._hd_poster(poster) if poster and poster != "N/A" else None

        return MediaDetail(
            provider_id=provider_id,
            title=data.get("Title", ""),
            original_title=data.get("Title", ""),
            year=self._parse_year(data.get("Year")),
            media_type=media_type,
            overview=data.get("Plot", ""),
            genres=genres,
            poster_url=poster_url,
            fanart_url=None,   # OMDb 不提供 fanart
            logo_url=None,     # OMDb 不提供 logo
            rating=rating,
            provider=self.name,
            extra={"imdb_id": imdb_id},
        )

    def _hd_poster(self, url: str) -> str:
        """将亚马逊 CDN poster URL 替换为高分辨率版本（SX1000）"""
        import re
        return re.sub(r"_V1_.*\.jpg", "_V1_SX1000.jpg", url)

    def _parse_year(self, year_str: Optional[str]) -> Optional[int]:
        """从年份字符串（如 '2014' 或 '2013–2014'）中提取起始年份"""
        if not year_str or year_str == "N/A":
            return None
        try:
            return int(year_str[:4])
        except (ValueError, TypeError):
            return None

    def close(self) -> None:
        """释放 HTTP 连接池"""
        self._client.close()
