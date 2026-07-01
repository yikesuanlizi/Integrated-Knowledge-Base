from __future__ import annotations

from pathlib import Path
from typing import List

from app.compiler.wiki_cards import WikiCard, WikiCardType


FRONTMATTER_TEMPLATE = """---
title: "{title}"
card_type: "{card_type}"
card_id: "{card_id}"
source_ref: "{source_ref}"
confidence: {confidence}
status: "{status}"
---

"""


def compile_wiki_markdown(cards: List[WikiCard], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for card in cards:
        md_content = card_to_markdown(card)
        file_path = output_dir / f"{card.title}.md"
        file_path.write_text(md_content, encoding="utf-8")


def card_to_markdown(card: WikiCard) -> str:
    lines: List[str] = []

    lines.append(FRONTMATTER_TEMPLATE.format(
        title=card.title,
        card_type=card.card_type.value,
        card_id=card.card_id,
        source_ref=card.source_ref,
        confidence=card.confidence,
        status=card.status.value,
    ))

    lines.append(f"# {card.title}")
    lines.append("")

    if card.card_type == WikiCardType.TASK:
        lines.append("## 任务描述")
        lines.append(card.content)
        lines.append("")

        if card.facts:
            lines.append("## 步骤")
            for i, fact in enumerate(card.facts, 1):
                lines.append(f"{i}. {fact.statement}")
                if fact.source_ref:
                    lines.append(f"   *来源: {fact.source_ref}*")
            lines.append("")

    elif card.card_type == WikiCardType.COMPONENT:
        lines.append("## 概述")
        lines.append(card.content)
        lines.append("")

        if card.facts:
            lines.append("## 属性与特征")
            for fact in card.facts:
                lines.append(f"- {fact.statement}")
                if fact.source_ref:
                    lines.append(f"  *来源: {fact.source_ref}*")
            lines.append("")

    elif card.card_type == WikiCardType.DOMAIN:
        lines.append("## 领域描述")
        lines.append(card.content)
        lines.append("")

        if card.facts:
            lines.append("## 关键概念")
            for fact in card.facts:
                lines.append(f"- {fact.statement}")
            lines.append("")

    elif card.card_type == WikiCardType.CONCEPT:
        lines.append("## 定义")
        lines.append(card.content)
        lines.append("")

    else:
        lines.append(card.content)
        lines.append("")

    if card.references:
        lines.append("## 参考资料")
        for ref in card.references:
            lines.append(f"- {ref}")
        lines.append("")

    if card.related_cards:
        lines.append("## 相关卡片")
        for related_id in card.related_cards:
            lines.append(f"- [[{related_id}]]")
        lines.append("")

    if card.metadata:
        lines.append("## 元数据")
        for key, value in card.metadata.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    return "\n".join(lines)


def markdown_to_card(md_content: str) -> WikiCard:
    from app.compiler.wiki_cards import WikiCardStatus

    lines = md_content.split("\n")

    frontmatter_start = 0
    frontmatter_end = 0

    if lines and lines[0] == "---":
        frontmatter_start = 1
        for i, line in enumerate(lines[1:], start=1):
            if line == "---":
                frontmatter_end = i
                break

    frontmatter = {}
    for line in lines[frontmatter_start:frontmatter_end]:
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip().strip('"')

    title = frontmatter.get("title", "")
    card_type = frontmatter.get("card_type", "document")
    card_id = frontmatter.get("card_id", "")
    source_ref = frontmatter.get("source_ref", "")
    confidence = float(frontmatter.get("confidence", 1.0))
    status = frontmatter.get("status", "draft")

    content_start = frontmatter_end + 1
    content_lines = []
    for line in lines[content_start:]:
        if line.startswith("#") or line.startswith("##"):
            continue
        content_lines.append(line)

    content = "\n".join(content_lines).strip()

    return WikiCard(
        card_id=card_id,
        card_type=WikiCardType(card_type),
        title=title,
        content=content,
        source_ref=source_ref,
        confidence=confidence,
        status=WikiCardStatus(status),
        facts=[],
        references=[],
        related_cards=[],
        metadata={},
    )


def find_wiki_files(wiki_dir: Path) -> List[Path]:
    return sorted(wiki_dir.glob("*.md"))


def load_wiki_card(file_path: Path) -> WikiCard:
    md_content = file_path.read_text(encoding="utf-8")
    return markdown_to_card(md_content)


def load_all_wiki_cards(wiki_dir: Path) -> List[WikiCard]:
    cards: List[WikiCard] = []
    for file_path in find_wiki_files(wiki_dir):
        try:
            card = load_wiki_card(file_path)
            cards.append(card)
        except Exception:
            continue
    return cards
