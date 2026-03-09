from typing import Optional
import logging
from .base import BaseProvider, MediaQuery, MediaDetail, EpisodeDetail

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Provider 注册中心与调度器。
    负责管理所有已注册的 Provider，并按 media_type + priority 路由抓取请求。

    设计要点：
    - 核心内置 Provider（如 TMDB）在 main.py 启动时注册
    - 插件 Provider（如 MusicBrainz）在插件 on_init hook 中调用 register() 注册
    - scrape() 实现自动 fallback：优先级高的 Provider 失败后自动尝试下一个
    """

    def __init__(self):
        self._providers: list[BaseProvider] = []

    def register(self, provider: BaseProvider) -> None:
        """注册一个 Provider，注册后按 priority 重新排序"""
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority)

    def get_providers_for_type(self, media_type: str) -> list[BaseProvider]:
        """返回支持指定 media_type 的所有 Provider，已按 priority 排序"""
        return [p for p in self._providers if media_type in p.media_types]

    def scrape(self, query: MediaQuery) -> Optional[MediaDetail]:
        """
        按 priority 依次尝试匹配的 Provider，第一个成功即返回结果。
        所有 Provider 均失败时，抛出最后一个异常；无结果时返回 None。
        """
        providers = self.get_providers_for_type(query.media_type)
        last_error = None
        for provider in providers:
            try:
                results = provider.search(query)
                if not results:
                    logger.debug("Provider %s 无结果: %r", provider.name, query.title)
                    continue
                detail = provider.get_detail(results[0].provider_id)
                if detail is None:
                    logger.debug("Provider %s get_detail 无结果，尝试下一个", provider.name)
                    continue
                logger.debug("使用数据源: %s", provider.name)
                return detail
            except Exception as e:
                logger.warning("Provider %s 失败，尝试下一个: %s", provider.name, e)
                last_error = e
                continue
        if last_error:
            raise last_error
        return None

    def scrape_episode(self, provider_id: str, season: int, episode: int) -> Optional[EpisodeDetail]:
        """
        调用成功刮削剧集时所用的 Provider 获取单集详情。
        provider_id 为 scrape() 返回的 MediaDetail.provider_id，用于定位对应 Provider。

        TODO: 实现单集详情获取逻辑
        - 从 provider_id 解析出 Provider 名称
        - 找到对应 Provider 并调用 get_episode_detail()
        - 返回 EpisodeDetail 或 None
        """
        return None
