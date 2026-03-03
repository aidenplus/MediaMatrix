import json
import logging
from pathlib import Path
from typing import Optional

import httpx

from providers.base import MediaQuery

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".ts"}
MUSIC_EXTENSIONS = {".flac", ".mp3", ".aac", ".wav", ".m4a"}

_SYSTEM_PROMPT = """
你是一个媒体文件名解析器。我会给你一个视频文件的文件名（不含扩展名），请提取以下信息并严格按 JSON 格式返回，不要输出任何其他内容：

{
  "title": "媒体标题",
  "media_type": "movie 或 tv",
  "year": 2023,
  "season": 1,
  "episode": 1
}

字段规则：
- title：纯净的媒体标题，去掉分辨率（1080p/4K/2160p）、编码（x264/HEVC/AV1）、音轨、发行组、画质标签（BluRay/WEB-DL）等技术信息，保留原始语言（中文或英文）
- media_type：只能是 "movie" 或 "tv"；含有集号/季号信息的为 tv，否则为 movie
- year：发行/首播年份，整数；无法确定则填 null
- season：剧集季号，整数；movie 类型或无季号则填 null
- episode：剧集集号，整数；movie 类型或无集号则填 null

示例：
- Interstellar.2014.1080p.BluRay.x264 → {"title": "Interstellar", "media_type": "movie", "year": 2014, "season": null, "episode": null}
- Breaking.Bad.S02E05.720p → {"title": "Breaking Bad", "media_type": "tv", "year": null, "season": 2, "episode": 5}
- 大宋提刑官第二季第三集 → {"title": "大宋提刑官", "media_type": "tv", "year": null, "season": 2, "episode": 3}
- 权力的游戏.S08E06.凛冬将至.1080p → {"title": "权力的游戏", "media_type": "tv", "year": null, "season": 8, "episode": 6}
"""


def _strip_markdown(text: str) -> str:
    """去除 LLM 返回内容中的 markdown 代码块包裹"""
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


class LLMIdentifier:
    """
    基于 LLM 的媒体文件名识别器。

    相比正则版本，能够处理非标准命名、中英混合标题、
    杂乱的技术标签堆叠等正则难以覆盖的场景。

    接口与 MediaIdentifier 完全兼容，可在 settings.yaml 中
    通过 identifier.engine: llm 切换启用。

    LLM 请求失败时，自动降级为以文件名作为标题的兜底结果，
    不会抛出异常中断刮削流程。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        video_extensions: set[str] = None,
        music_extensions: set[str] = None,
    ):
        self._video_extensions = video_extensions or VIDEO_EXTENSIONS
        self._music_extensions = music_extensions or MUSIC_EXTENSIONS
        self._model = model
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )

    def identify(self, path: str) -> Optional[MediaQuery]:
        """
        根据文件路径返回 MediaQuery，无法识别的文件类型返回 None。
        """
        p = Path(path)
        suffix = p.suffix.lower()

        if suffix in self._music_extensions:
            return MediaQuery(title=p.stem, media_type="music", extra={"filename": p.stem})
        if suffix not in self._video_extensions:
            return None

        query = self._identify_by_llm(p.stem)
        query.extra["filename"] = p.stem
        return query

    def _identify_by_llm(self, filename: str) -> MediaQuery:
        """调用 LLM 解析文件名，失败时降级为文件名直接作为标题"""
        try:
            resp = self._client.post("/chat/completions", json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"文件名：{filename}"},
                ],
                "temperature": 0,
            })
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            content = _strip_markdown(content)
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning("LLM Identifier 返回内容无法解析为 JSON: %s", e)
            return MediaQuery(title=filename.replace(".", " ").strip(), media_type="movie")
        except Exception as e:
            logger.warning("LLM Identifier 请求失败，降级为文件名: %s", e)
            return MediaQuery(title=filename.replace(".", " ").strip(), media_type="movie")

        media_type = data.get("media_type", "movie")
        season = data.get("season")
        episode = data.get("episode")
        # 只有集号而无季号时，默认为第一季（与正则版行为一致，媒体服务器通常需要季号）
        if media_type == "tv" and episode is not None and season is None:
            season = 1

        return MediaQuery(
            title=data.get("title") or filename,
            media_type=media_type,
            year=data.get("year"),
            season=season,
            episode=episode,
        )

    def close(self) -> None:
        self._client.close()
