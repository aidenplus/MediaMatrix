from typing import Optional
import httpx
from .base import BaseProvider, MediaQuery, SearchResult, MediaDetail

IMAGE_BASE = "https://artworks.thetvdb.com"


class TVDbProvider(BaseProvider):
    """
    TVDb (The TV Database) 数据源适配器，使用 v4 API。
    仅支持剧集（tv），作为 TMDB 的剧集备用数据源。

    API 文档: https://thetvdb.github.io/v4-api/
    认证流程: POST /login 用 apikey 换取 token，后续请求携带 Bearer token。
    限速说明: 官方无明确限制，并发控制由上层 Scraper 的信号量负责。
    """
    name = "tvdb"
    media_types = ["tv"]
    priority = 2  # TMDB 失败后的备用

    # 常见 IETF 语言标签到 TVDb ISO 639-2 代码的映射
    _LANG_MAP = {
        "zh-cn": "zho", "zh-tw": "zho", "zh": "zho",
        "en": "eng", "en-us": "eng", "en-gb": "eng",
        "ja": "jpn", "ko": "kor", "fr": "fra",
        "de": "deu", "es": "spa", "it": "ita",
    }

    def __init__(self, api_key: str, language: str = "zho"):
        self.api_key = api_key
        # 统一转换为 TVDb ISO 639-2 代码
        self.language = self._LANG_MAP.get(language.lower(), language)
        self.base_url = "https://api4.thetvdb.com/v4"
        self._client = httpx.Client(timeout=15)
        self._token: Optional[str] = None

    def _ensure_token(self) -> None:
        """获取并缓存 Bearer token，已有 token 时跳过"""
        if self._token:
            return
        resp = self._client.post(
            f"{self.base_url}/login",
            json={"apikey": self.api_key},
        )
        resp.raise_for_status()
        self._token = resp.json()["data"]["token"]
        self._client.headers.update({"Authorization": f"Bearer {self._token}"})

    def search(self, query: MediaQuery) -> list[SearchResult]:
        """调用 TVDb /search 接口搜索剧集"""
        self._ensure_token()
        params = {"query": query.title, "type": "series"}
        if query.year:
            params["year"] = query.year

        resp = self._client.get(f"{self.base_url}/search", params=params)
        resp.raise_for_status()
        results = resp.json().get("data") or []

        return [
            SearchResult(
                provider_id=f"tv:{item['tvdb_id']}",
                title=item.get("name", ""),
                year=self._parse_year(item.get("first_air_time")),
                media_type="tv",
                provider=self.name,
            )
            for item in results
            if item.get("tvdb_id")
        ]

    def get_detail(self, provider_id: str) -> MediaDetail:
        """根据 provider_id（格式: tv:12345）获取完整剧集元数据"""
        self._ensure_token()
        _, tvdb_id = provider_id.split(":", 1)

        # 基础信息
        resp = self._client.get(
            f"{self.base_url}/series/{tvdb_id}/extended",
            params={"meta": "translations"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        # 优先取中文翻译标题和简介
        title = self._get_translation(data, "nameTranslations", "name") or data.get("name", "")
        overview = self._get_translation(data, "overviewTranslations", "overview") or data.get("overview", "")
        original_title = data.get("name", "")

        genres = [g["name"] for g in (data.get("genres") or [])]
        rating = data.get("score")

        poster_url = self._get_artwork(data, "poster")
        fanart_url = self._get_artwork(data, "background")

        return MediaDetail(
            provider_id=provider_id,
            title=title,
            original_title=original_title,
            year=self._parse_year(data.get("firstAired")),
            media_type="tv",
            overview=overview,
            genres=genres,
            poster_url=poster_url,
            fanart_url=fanart_url,
            logo_url=self._get_artwork(data, "clearlogo"),
            rating=rating,
            provider=self.name,
            extra={"tvdb_id": tvdb_id},
        )

    def _get_translation(self, data: dict, list_key: str, field: str) -> Optional[str]:
        """从指定 translations 列表中取目标语言的字段值，优先配置语言，fallback 到英文"""
        translations = data.get("translations", {})
        for lang in (self.language, "eng"):
            for item in translations.get(list_key) or []:
                if item.get("language") == lang and item.get(field):
                    return item[field]
        return None

    def _get_artwork(self, data: dict, artwork_type: str) -> Optional[str]:
        """从 artworks 列表中取指定类型的第一张图片 URL。
        TVDb artwork type 数字对应：2=poster, 3=background, 5=clearlogo
        """
        type_map = {"poster": 2, "background": 3, "clearlogo": 5}
        target = type_map.get(artwork_type)
        if target is None:
            return None
        for art in data.get("artworks") or []:
            if art.get("type") == target and art.get("image"):
                return art["image"]
        return None

    def _parse_year(self, date_str: Optional[str]) -> Optional[int]:
        """从日期字符串（如 '2005-01-01'）中提取年份"""
        if date_str and len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except ValueError:
                pass
        return None

    def close(self) -> None:
        """释放 HTTP 连接池"""
        self._client.close()
