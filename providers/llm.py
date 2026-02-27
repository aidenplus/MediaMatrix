import json
import logging
from typing import Optional

import httpx

from .base import BaseProvider, MediaQuery, MediaDetail, SearchResult

logger = logging.getLogger(__name__)


def _strip_markdown_code_block(text: str) -> str:
    """去除模型返回内容中的 markdown 代码块包裹（```json ... ``` 或 ``` ... ```）"""
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]  # 去掉首行 ```json
        text = text.rsplit("```", 1)[0]  # 去掉尾部 ```
    return text.strip()

_SYSTEM_PROMPT = """
你是一个影视数据库助手。我会给你一个媒体文件名，请你通过已有知识搜索该媒体的元数据信息。

请严格按照以下 JSON 格式返回，不要输出任何其他内容：

{
  "title": "中文标题",
  "original_title": "原始语言标题",
  "year": 2005,
  "media_type": "movie 或 tv",
  "overview": "剧情简介",
  "genres": ["剧情", "历史"],
  "rating": 8.5
}

字段规则：
- title：中文标题优先，无中文则用原始标题
- original_title：原始语言的标题
- year：首播或上映年份，整数，无法确认则填 null
- media_type：只能是 "movie" 或 "tv"
- overview：100 字以内的中文简介
- genres：类型标签，中文，1-3 个
- rating：评分，0-10 的浮点数，无法确认则填 null

如果完全无法找到该媒体的信息，返回：
{"error": "未找到相关信息"}

"""


class LLMProvider(BaseProvider):
    """
    基于 LLM 的兜底数据源，使用 OpenAI 兼容接口。
    仅在所有常规 Provider（TMDB/TVDb/OMDb）均失败后触发。

    支持任何兼容 OpenAI Chat Completions 格式的服务：
    OpenAI、DeepSeek、Qwen、本地 Ollama 等。

    注意：LLM 返回的元数据为模型生成内容，准确性不保证，
    适合作为冷门内容的兜底方案，不建议用于主流媒体。
    """
    name = "llm"
    media_types = ["movie", "tv"]
    priority = 99  # 所有常规 Provider 均失败后的最终兜底

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1"):
        self._model = model
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        # 缓存 search() 中 LLM 返回的完整结果，供 get_detail() 直接取用，避免重复请求
        self._cache: dict[str, MediaDetail] = {}

    def search(self, query: MediaQuery) -> list[SearchResult]:
        """调用 LLM 获取元数据，结果缓存后返回占位 SearchResult"""
        user_msg = f"文件名：{query.title}"
        if query.year:
            user_msg += f"（{query.year}年）"

        try:
            resp = self._client.post("/chat/completions", json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.8,
            })
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            content = _strip_markdown_code_block(content)
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning("LLM 返回内容无法解析为 JSON: %s", e)
            return []
        except Exception as e:
            logger.warning("LLM 请求失败: %s", e)
            return []

        if "error" in data:
            logger.debug("LLM 未找到相关信息: %r", query.title)
            return []

        provider_id = f"{data.get('media_type', query.media_type)}:llm:{query.title}"
        detail = MediaDetail(
            provider_id=provider_id,
            title=data.get("title", query.title),
            original_title=data.get("original_title", query.title),
            year=data.get("year"),
            media_type=data.get("media_type", query.media_type),
            overview=data.get("overview", ""),
            genres=data.get("genres", []),
            poster_url=None,   # LLM 不提供图片
            fanart_url=None,
            logo_url=None,
            rating=data.get("rating"),
            provider=self.name,
        )
        self._cache[provider_id] = detail

        return [SearchResult(
            provider_id=provider_id,
            title=detail.title,
            year=detail.year,
            media_type=detail.media_type,
            provider=self.name,
        )]

    def get_detail(self, provider_id: str) -> MediaDetail:
        """从缓存中取出 search() 已获取的完整元数据"""
        if provider_id not in self._cache:
            raise ValueError(f"LLM Provider 缓存中无此条目: {provider_id}")
        return self._cache[provider_id]

    def close(self) -> None:
        self._client.close()
