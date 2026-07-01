"""Marp 幻灯片格式导出。"""
from typing import List

from app.compiler.wiki_cards import WikiCard


def export_cards_marp(cards: List[WikiCard]) -> str:
    """将 WikiCard 列表导出为 Marp Markdown 幻灯片格式。

    每张卡片一页幻灯片：
    - 顶部 Marp 配置（marp: true, theme: default, paginate: true）
    - 幻灯片之间用 --- 分隔
    - 卡片数 > 5 时添加页脚（当前第 N 张 / 共 M 张）

    Args:
        cards: WikiCard 列表。

    Returns:
        Marp Markdown 格式字符串。
    """
    parts: List[str] = []

    # Marp 配置
    parts.append("---")
    parts.append("marp: true")
    parts.append("theme: default")
    parts.append("<!-- paginate: true -->")
    parts.append("---")

    total = len(cards)
    show_footer = total > 5

    for idx, card in enumerate(cards, start=1):
        # 页脚
        if show_footer:
            parts.append(f"<!-- footer: 第 {idx} 张 / 共 {total} 张 -->")

        # 标题幻灯片（单独一页写标题）
        parts.append(f"## {card.title}")

        # 内容
        parts.append(card.content)

        # 幻灯片分隔
        if idx < total:
            parts.append("\n---")

    return "\n".join(parts)
