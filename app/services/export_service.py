"""导出服务：封装 export API 的业务逻辑。"""
from __future__ import annotations

from typing import List

from app.compiler.wiki_cards import WikiCard
from app.export import (
    export_cards_graphml,
    export_cards_json,
    export_cards_jsonld,
    export_cards_llms_txt,
    export_cards_marp,
    export_cards_markdown,
)


class ExportService:
    """导出服务，支持多种格式导出 WikiCards。"""

    def export_markdown(self, cards: List[WikiCard]) -> str:
        """导出为 Markdown 格式。

        Args:
            cards: WikiCard 列表。

        Returns:
            Markdown 字符串。
        """
        return export_cards_markdown(cards)

    def export_json(self, cards: List[WikiCard]) -> str:
        """导出为 JSON 格式。

        Args:
            cards: WikiCard 列表。

        Returns:
            JSON 字符串。
        """
        return export_cards_json(cards)

    def export_jsonld(self, cards: List[WikiCard]) -> str:
        """导出为 JSON-LD 格式。

        Args:
            cards: WikiCard 列表。

        Returns:
            JSON-LD 字符串。
        """
        return export_cards_jsonld(cards)

    def export_graphml(self, cards: List[WikiCard]) -> str:
        """导出为 GraphML 格式。

        Args:
            cards: WikiCard 列表。

        Returns:
            GraphML 字符串。
        """
        return export_cards_graphml(cards)

    def export_llms_txt(self, cards: List[WikiCard]) -> str:
        """导出为 llms.txt 格式。

        Args:
            cards: WikiCard 列表。

        Returns:
            llms.txt 字符串。
        """
        return export_cards_llms_txt(cards)

    def export_marp(self, cards: List[WikiCard]) -> str:
        """导出为 Marp 幻灯片格式。

        Args:
            cards: WikiCard 列表。

        Returns:
            Marp Markdown 字符串。
        """
        return export_cards_marp(cards)
