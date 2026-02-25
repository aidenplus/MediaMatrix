import asyncio
from typing import Optional
from providers.base import MediaQuery, MediaDetail
from providers.registry import ProviderRegistry


class Scraper:
    """
    元数据抓取调度器，负责控制并发并调用 ProviderRegistry 执行实际抓取。

    并发控制：使用 asyncio.Semaphore 限制同时进行的 API 请求数。
    当前 Provider 为同步实现，通过 run_in_executor 包装为异步调用，
    后续 Provider 改为 async 后可直接 await。
    """

    def __init__(self, registry: ProviderRegistry, max_concurrency: int = 3):
        self._registry = registry
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def scrape(self, query: MediaQuery) -> Optional[MediaDetail]:
        """抓取单个媒体的元数据，受信号量限制并发数"""
        async with self._semaphore:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._registry.scrape, query)

    async def scrape_batch(self, queries: list[MediaQuery]) -> list[Optional[MediaDetail]]:
        """批量抓取，并发执行，信号量自动控制最大并发数"""
        tasks = [self.scrape(q) for q in queries]
        return await asyncio.gather(*tasks, return_exceptions=False)
