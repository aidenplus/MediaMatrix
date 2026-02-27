"""
LLMProvider 手动测试脚本
用法：python tests/test_llm_provider_manual.py

需要在 config/settings.yaml 中配置 providers.llm.api_key 才能运行。
"""
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.llm import LLMProvider
from providers.base import MediaQuery

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"

TEST_CASES = [
    # 冷门国产剧（TMDB 较难匹配）
    MediaQuery(title="大宋提刑官", media_type="tv", year=2005),
    # 冷门国产电影
    MediaQuery(title="Hello树先生", media_type="movie", year=2011),
    # 英文片，验证 original_title 字段
    MediaQuery(title="Inception", media_type="movie", year=2010),
    # 命名不规范，无年份
    MediaQuery(title="甄嬛传", media_type="tv"),
    # 完全虚构的内容，验证 error 兜底
    MediaQuery(title="这部电影根本不存在XYZABC123", media_type="movie"),
]


def main():
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    llm_cfg = cfg.get("providers", {}).get("llm", {})
    api_key = llm_cfg.get("api_key", "")

    if not api_key:
        print("错误：settings.yaml 中 providers.llm.api_key 为空，请先填入 API Key")
        sys.exit(1)

    provider = LLMProvider(
        api_key=api_key,
        model=llm_cfg.get("model", "gpt-4o-mini"),
        base_url=llm_cfg.get("base_url", "https://api.openai.com/v1"),
    )

    print(f"模型: {llm_cfg.get('model')}  接口: {llm_cfg.get('base_url')}\n")
    print("=" * 60)

    for query in TEST_CASES:
        label = f"{query.title}" + (f" ({query.year})" if query.year else "")
        print(f"\n▶ {label}")

        results = provider.search(query)
        print(results)
        if not results:
            print("  → 未找到结果")
            continue

        detail = provider.get_detail(results[0].provider_id)
        print(f"  标题:     {detail.title}")
        print(f"  原标题:   {detail.original_title}")
        print(f"  年份:     {detail.year}")
        print(f"  类型:     {detail.media_type}")
        print(f"  分类:     {', '.join(detail.genres)}")
        print(f"  评分:     {detail.rating}")
        print(f"  简介:     {detail.overview}")

    print("\n" + "=" * 60)
    provider.close()


if __name__ == "__main__":
    main()
