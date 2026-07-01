"""JSON 和 JSON-LD 格式导出。"""
import json
from typing import List

from app.export.utils import card_to_dict, iso_now
from app.compiler.wiki_cards import WikiCard


def export_cards_json(cards: List[WikiCard], pretty: bool = True) -> str:
    """将 WikiCard 列表导出为 JSON 格式字符串。

    Args:
        cards: WikiCard 列表。
        pretty: 是否格式化输出（indent=2）。

    Returns:
        JSON 格式字符串，顶层包含 cards 数组、total 计数和 exported_at 时间戳。
    """
    cards_data = [card_to_dict(card) for card in cards]
    total = len(cards_data)

    output = {
        "cards": cards_data,
        "total": total,
        "exported_at": iso_now(),
    }

    indent = 2 if pretty else None
    return json.dumps(output, ensure_ascii=False, indent=indent)


def export_cards_jsonld(cards: List[WikiCard]) -> str:
    """将 WikiCard 列表导出为 JSON-LD 格式字符串。

    每个卡片映射为 Schema.org Article 类型：
    - facts 的 statement 拼接为 description
    - references 映射为 citation
    - linked_chunks 映射为 isBasedOn（实际代码中无此字段，设为空列表）

    Args:
        cards: WikiCard 列表。

    Returns:
        JSON-LD 格式字符串。
    """
    graph: List[dict] = []

    for card in cards:
        # 拼接 facts 为 description
        descriptions = [f.statement for f in card.facts]
        description = "; ".join(descriptions) if descriptions else ""

        # 映射 references 为 citation
        citations = [{"@type": "CreativeWork", "text": ref} for ref in card.references]

        card_ld = {
            "@type": "Article",
            "@id": card.card_id,
            "headline": card.title,
            "text": card.content,
            "description": description,
            "citation": citations,
            "isBasedOn": [],  # linked_chunks 在实际 WikiCard 中不存在，设为空
            "dateCreated": card.created_at,
            "dateModified": card.updated_at,
        }

        graph.append(card_ld)

    output = {
        "@context": "https://schema.org",
        "@graph": graph,
    }

    return json.dumps(output, ensure_ascii=False, indent=2)
