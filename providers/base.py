from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MediaQuery:
    """
    描述一次媒体搜索请求。
    由 MediaIdentifier 从文件名解析生成，传递给 ProviderRegistry 进行抓取。
    """
    title: str           # 识别出的媒体标题
    media_type: str      # 媒体类型: "movie" | "tv" | "music"
    year: Optional[int] = None   # 发行年份，可能为 None（识别失败时）
    season: Optional[int] = None  # 季号，仅 tv 类型有效
    episode: Optional[int] = None # 集号，仅 tv 类型有效
    extra: dict = field(default_factory=dict)  # 扩展字段，供特定 Provider 使用


@dataclass
class SearchResult:
    """
    Provider.search() 返回的单条搜索候选结果。
    provider_id 格式为 "media_type:id"，例如 "movie:157336"，
    内嵌 media_type 是为了让 get_detail() 只需一个参数即可路由到正确接口。
    """
    provider_id: str     # 格式: "movie:157336" 或 "tv:1399"
    title: str
    year: Optional[int]
    media_type: str
    provider: str        # Provider 名称，如 "tmdb"


@dataclass
class MediaDetail:
    """
    Provider.get_detail() 返回的完整元数据，用于生成 NFO 文件和下载图片。
    """
    provider_id: str
    title: str
    original_title: str
    year: Optional[int]
    media_type: str
    overview: str
    genres: list[str]
    poster_url: Optional[str]   # 海报图片 URL
    fanart_url: Optional[str]   # 背景剧照 URL
    logo_url: Optional[str]     # 透明 Logo URL（来自 /images 接口）
    rating: Optional[float]
    provider: str
    extra: dict = field(default_factory=dict)  # 扩展字段，如 {"tmdb_id": "157336"}


class BaseProvider(ABC):
    """
    所有数据源 Provider 的抽象基类。
    新增数据源（如豆瓣、IMDB）只需继承此类并实现 search/get_detail，
    然后通过 ProviderRegistry.register() 注册即可，无需修改核心代码。
    """
    name: str = ""           # Provider 唯一标识，如 "tmdb"
    media_types: list[str] = []  # 支持的媒体类型列表
    priority: int = 10       # 优先级，数字越小越优先；同类型多个 Provider 时按此排序

    @abstractmethod
    def search(self, query: MediaQuery) -> list[SearchResult]:
        """搜索媒体，返回候选列表（按相关度排序）"""
        ...

    @abstractmethod
    def get_detail(self, provider_id: str) -> MediaDetail:
        """根据 provider_id（格式: media_type:id）获取完整元数据"""
        ...
