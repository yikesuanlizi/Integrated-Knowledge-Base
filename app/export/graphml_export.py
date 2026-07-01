"""GraphML 格式导出。"""
from typing import List

from app.compiler.wiki_cards import WikiCard


def export_cards_graphml(cards: List[WikiCard]) -> str:
    """将 WikiCard 列表导出为 GraphML XML 格式字符串。

    节点：每张卡片一个 node，属性包括 title、card_type、confidence、status、content_preview（前100字）。
    边：有向边表示 related_cards；虚线边表示 linked_chunks（实际代码中不存在，仍建立空边）。

    Args:
        cards: WikiCard 列表。

    Returns:
        GraphML XML 格式字符串。
    """
    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<graphml xmlns="http://graphml.graphdrawing.org/xmlns" '
                 'xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns '
                 'http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd" '
                 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">')

    # 定义属性键
    lines.append('  <key id="title" for="node" attr.name="title" attr.type="string"/>')
    lines.append('  <key id="card_type" for="node" attr.name="card_type" attr.type="string"/>')
    lines.append('  <key id="confidence" for="node" attr.name="confidence" attr.type="double"/>')
    lines.append('  <key id="status" for="node" attr.name="status" attr.type="string"/>')
    lines.append('  <key id="content_preview" for="node" attr.name="content_preview" attr.type="string"/>')
    lines.append('  <key id="source_ref" for="edge" attr.name="source_ref" attr.type="string"/>')

    # 图
    lines.append('  <graph id="WikiCards" edgedefault="directed">')

    # 节点
    for card in cards:
        card_type_val = card.card_type.value if hasattr(card.card_type, "value") else card.card_type
        status_val = card.status.value if hasattr(card.status, "value") else card.status
        preview = card.content[:100].replace("\n", " ").replace('"', "'")

        lines.append(f'    <node id="{card.card_id}">')
        lines.append(f'      <data key="title">{_escape_xml(card.title)}</data>')
        lines.append(f'      <data key="card_type">{_escape_xml(card_type_val)}</data>')
        lines.append(f'      <data key="confidence">{card.confidence}</data>')
        lines.append(f'      <data key="status">{_escape_xml(status_val)}</data>')
        lines.append(f'      <data key="content_preview">{_escape_xml(preview)}</data>')
        lines.append('    </node>')

    # 边：related_cards（有向边，实线）
    for card in cards:
        for related_id in card.related_cards:
            lines.append(f'    <edge source="{card.card_id}" target="{related_id}">')
            lines.append(f'      <data key="source_ref">related_card</data>')
            lines.append('    </edge>')

    lines.append('  </graph>')
    lines.append('</graphml>')

    return "\n".join(lines)


def _escape_xml(s: str) -> str:
    """转义 XML 特殊字符。"""
    return (s
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))
