"""Markdown 格式导出。"""
from typing import List

from app.compiler.wiki_cards import WikiCard, WikiCardStatus


def export_cards_markdown(cards: List[WikiCard], include_metadata: bool = True) -> str:
    """将 WikiCard 列表导出为 Markdown 格式字符串。

    每张卡片输出：
    - h2 标题（## {title}）
    - YAML 风格元信息注释
    - facts 列表（可选）
    - references 列表
    - related_cards wikilink 格式
    - 内容正文
    - 卡片之间用水平线分隔

    Args:
        cards: WikiCard 列表。
        include_metadata: 是否包含 facts 等元信息。

    Returns:
        Markdown 格式字符串。
    """
    parts: List[str] = []

    for card in cards:
        # 标题
        parts.append(f"## {card.title}")

        # 元信息注释行
        conf_pct = int(card.confidence * 100)
        status_val = card.status.value if hasattr(card.status, "value") else card.status
        card_type_val = card.card_type.value if hasattr(card.card_type, "value") else card.card_type
        parts.append(f"[//]: # ({card_type_val} | confidence={conf_pct}% | status={status_val})")

        # facts 列表
        if include_metadata and card.facts:
            parts.append("### 事实")
            for fact in card.facts:
                page_info = f" (页码: {fact.page_no})" if fact.page_no else ""
                parts.append(f"- {fact.statement}{page_info}")

        # references 列表
        if card.references:
            parts.append("### 参考")
            for ref in card.references:
                parts.append(f"- {ref}")

        # related_cards（wikilink 格式）
        if card.related_cards:
            card_links = " ".join(f"[[{rc}]]" for rc in card.related_cards)
            parts.append(f"### 相关：{card_links}")

        # 内容正文
        parts.append(card.content)

        # 卡片分隔
        parts.append("\n---\n")

    # 去掉最后多余的水平和空行
    result = "\n\n".join(part.strip() for part in parts if str(part).strip())
    if result.endswith("\n---\n"):
        result = result[:-5]
    return result
