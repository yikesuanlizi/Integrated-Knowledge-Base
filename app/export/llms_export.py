"""LLMs.txt 格式导出（适合喂给 LLM 的纯文本格式）。"""
from typing import List

from app.export.utils import iso_now
from app.compiler.wiki_cards import WikiCard


def export_cards_llms_txt(cards: List[WikiCard]) -> str:
    """将 WikiCard 列表导出为纯文本格式，适合 LLM 上下文。

    格式：
    - 开头标题和时间戳
    - 每张卡片：标题行 + type + source + 空行 + content
    - 卡片之间用 === 分隔

    Args:
        cards: WikiCard 列表。

    Returns:
        纯文本格式字符串。
    """
    parts: List[str] = []
    parts.append("# Knowledge Base Export")
    parts.append(f"Exported at: {iso_now()}")
    parts.append("")

    for card in cards:
        card_type_val = card.card_type.value if hasattr(card.card_type, "value") else card.card_type
        parts.append(card.title)
        parts.append(f"type: {card_type_val}")
        parts.append(f"source: {card.source_ref}")
        parts.append("")
        parts.append(card.content)
        parts.append("\n\n===\n")

    # 去掉最后多余的 ===
    result = "".join(parts)
    if result.endswith("\n\n===\n"):
        result = result[:-6]
    return result
