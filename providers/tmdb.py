from typing import Optional
import httpx
from .base import BaseProvider, MediaQuery, SearchResult, MediaDetail

# TMDB 图片 CDN 基础地址，"original" 表示原始分辨率
IMAGE_BASE = "https://image.tmdb.org/t/p/original"


class TMDBProvider(BaseProvider):
    """
    TMDB (The Movie Database) 数据源适配器。
    支持电影和剧集的搜索与元数据抓取，语言默认 zh-CN。

    API 文档: https://developer.themoviedb.org/docs
    限速说明: 官方限制约 40 req/10s，并发控制由上层 Scraper 的信号量负责。
    """
    name = "tmdb"
    media_types = ["movie", "tv"]
    priority = 1  # 最高优先级

    def __init__(self, api_key: str, language: str = "zh-CN"):
        self.api_key = api_key
        self.language = language
        self.base_url = "https://api.themoviedb.org/3"
        # 将 api_key 和 language 作为默认参数注入所有请求
        self._client = httpx.Client(
            timeout=15,
            params={"api_key": api_key, "language": language},
        )

    def search(self, query: MediaQuery) -> list[SearchResult]:
        """
        调用 TMDB /search/movie 或 /search/tv 接口搜索媒体。
        返回的 provider_id 格式为 "movie:12345" 或 "tv:12345"，
        内嵌 media_type 以便 get_detail() 无需额外参数即可路由。
        """
        endpoint = "/search/movie" if query.media_type == "movie" else "/search/tv"
        params = {"query": query.title}
        # 带年份可以提高搜索精度，减少误匹配
        if query.year:
            key = "year" if query.media_type == "movie" else "first_air_date_year"
            params[key] = query.year

        resp = self._client.get(f"{self.base_url}{endpoint}", params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])

        return [
            SearchResult(
                provider_id=f"{query.media_type}:{item['id']}",
                title=item.get("title") or item.get("name", ""),
                year=self._parse_year(item.get("release_date") or item.get("first_air_date")),
                media_type=query.media_type,
                provider=self.name,
            )
            for item in results
        ]

    def get_detail(self, provider_id: str) -> MediaDetail:
        """
        根据 provider_id（格式: "movie:12345" 或 "tv:12345"）获取完整元数据。
        额外调用 /images 接口获取透明 Logo。
        当 TMDB 主接口未返回本地化标题时，从 /translations 接口补取中文译名。
        """
        media_type, tmdb_id = provider_id.split(":", 1)
        endpoint = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
        resp = self._client.get(f"{self.base_url}{endpoint}")
        resp.raise_for_status()
        data = resp.json()

        logo_url = self._fetch_logo(tmdb_id, media_type)

        # 电影用 title/original_title，剧集用 name/original_name
        title = data.get("title") or data.get("name", "")
        original_title = data.get("original_title") or data.get("original_name", "")
        date_str = data.get("release_date") or data.get("first_air_date")

        # TMDB 的 zh-CN 本地化数据对部分影片存在缺失（title 字段与原名相同），
        # 此时从 /translations 接口按 CN→SG→HK→TW 顺序补取中文译名
        if title == original_title:
            title = self._fetch_zh_title(tmdb_id, media_type) or title

        return MediaDetail(
            provider_id=provider_id,
            title=title,
            original_title=original_title,
            year=self._parse_year(date_str),
            media_type=media_type,
            overview=data.get("overview", ""),
            genres=[g["name"] for g in data.get("genres", [])],
            poster_url=self._img(data.get("poster_path")),
            fanart_url=self._img(data.get("backdrop_path")),
            logo_url=logo_url,
            rating=data.get("vote_average"),
            provider=self.name,
            extra={"tmdb_id": tmdb_id},
        )

    def _fetch_zh_title(self, tmdb_id: str, media_type: str) -> Optional[str]:
        """
        从 /translations 接口获取中文标题。
        按 CN→SG→HK→TW 顺序取第一个非空译名：
        - CN（中国大陆）数据常有缺失，SG（新加坡）通常有完整简体中文
        - HK/TW 为繁体中文备用
        """
        endpoint = f"/movie/{tmdb_id}/translations" if media_type == "movie" else f"/tv/{tmdb_id}/translations"
        try:
            resp = self._client.get(f"{self.base_url}{endpoint}")
            resp.raise_for_status()
            translations = {
                t["iso_3166_1"]: t["data"].get("title") or t["data"].get("name", "")
                for t in resp.json().get("translations", [])
                if t.get("iso_639_1") == "zh"
            }
            for region in ("CN", "SG", "HK", "TW"):
                if translations.get(region):
                    return translations[region]
        except Exception:
            pass
        return None

    def _fetch_logo(self, tmdb_id: str, media_type: str) -> Optional[str]:
        """
        调用 TMDB /images 接口获取透明 Logo（PNG 格式）。
        优先返回中文或英文 Logo，失败时静默返回 None，不影响主流程。
        """
        endpoint = f"/movie/{tmdb_id}/images" if media_type == "movie" else f"/tv/{tmdb_id}/images"
        try:
            resp = self._client.get(
                f"{self.base_url}{endpoint}",
                params={"include_image_language": "zh,en,null"},
            )
            resp.raise_for_status()
            logos = resp.json().get("logos", [])
            if logos:
                return self._img(logos[0]["file_path"])
        except Exception:
            pass
        return None

    def _img(self, path: Optional[str]) -> Optional[str]:
        """将 TMDB 图片相对路径拼接为完整 URL"""
        return f"{IMAGE_BASE}{path}" if path else None

    def _parse_year(self, date_str: Optional[str]) -> Optional[int]:
        """从 TMDB 日期字符串（如 '2014-11-05'）中提取年份"""
        if date_str and len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except ValueError:
                pass
        return None

    def close(self):
        """释放 HTTP 连接池，应在应用关闭时调用"""
        self._client.close()
