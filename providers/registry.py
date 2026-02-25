from typing import Optional
from .base import BaseProvider, MediaQuery, MediaDetail


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
                    continue
                # 取搜索结果第一条（相关度最高）获取详情
                return provider.get_detail(results[0].provider_id)
            except Exception as e:
                last_error = e
                continue
        if last_error:
            raise last_error
        return None
