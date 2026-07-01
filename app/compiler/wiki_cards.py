from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from app.models.schemas import Chunk


class WikiCardType(str, Enum):
    DEFINITION = "definition"
    CONCEPT = "concept"
    PROCEDURE = "procedure"
    FAQ = "faq"
    FAULT = "fault"


class WikiCardStatus(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Fact:
    statement: str
    source_ref: str
    confidence: float = 1.0
    page_no: Optional[int] = None


@dataclass(frozen=True)
class WikiCard:
    card_id: str
    card_type: WikiCardType
    title: str
    content: str
    source_ref: str
    confidence: float = 1.0
    status: WikiCardStatus = WikiCardStatus.DRAFT
    facts: List[Fact] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    related_cards: List[str] = field(default_factory=list)
    linked_chunks: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class CompilationResult:
    cards: List[WikiCard]
    build_id: str
    document_count: int
    chunk_count: int
    card_count: int
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def generate_card_id(title: str, card_type: str) -> str:
    content = f"{card_type}:{title}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def compile_wiki_cards(chunks: List[Chunk], build_id: str) -> CompilationResult:
    cards: List[WikiCard] = []
    warnings: List[str] = []
    errors: List[str] = []

    doc_cards = _compile_document_cards(chunks, build_id)
    cards.extend(doc_cards)

    component_cards = _compile_component_cards(chunks, build_id)
    cards.extend(component_cards)

    task_cards = _compile_task_cards(chunks, build_id)
    cards.extend(task_cards)

    domain_cards = _compile_domain_cards(chunks, build_id)
    cards.extend(domain_cards)

    concept_cards = _compile_concept_cards(chunks, build_id)
    cards.extend(concept_cards)

    return CompilationResult(
        cards=cards,
        build_id=build_id,
        document_count=len(set(ch.source_file for ch in chunks if ch.source_file)),
        chunk_count=len(chunks),
        card_count=len(cards),
        warnings=warnings,
        errors=errors,
    )


def _compile_document_cards(chunks: List[Chunk], build_id: str) -> List[WikiCard]:
    cards: List[WikiCard] = []
    documents = {}

    for chunk in chunks:
        if chunk.source_file:
            if chunk.source_file not in documents:
                documents[chunk.source_file] = []
            documents[chunk.source_file].append(chunk)

    for doc_name, doc_chunks in documents.items():
        title = doc_name.replace(".pdf", "").replace(".docx", "").replace(".txt", "").replace(".md", "")
        content = "\n\n".join(ch.content for ch in doc_chunks)
        facts = _extract_facts_from_chunks(doc_chunks)

        card = WikiCard(
            card_id=generate_card_id(title, WikiCardType.DOCUMENT),
            card_type=WikiCardType.DOCUMENT,
            title=title,
            content=content,
            source_ref=doc_name,
            confidence=0.95,
            facts=facts,
            metadata={
                "chunk_count": len(doc_chunks),
                "source_file": doc_name,
            },
        )
        cards.append(card)

    return cards


def _compile_component_cards(chunks: List[Chunk], build_id: str) -> List[WikiCard]:
    cards: List[WikiCard] = []
    component_patterns = [
        r"(?:部件|组件|零件|装置|设备|系统)\s*[：:]\s*(.+)",
        r"(?:[A-Z0-9]{3,}[-_]?[A-Z0-9]+)\s*(?:是|为|称为)\s*(.+)",
        r"(?:[\u4e00-\u9fff]{2,})\s*(?:部件|组件|零件|装置)",
    ]

    import re

    seen_components = set()

    for chunk in chunks:
        for pattern in component_patterns:
            for match in re.finditer(pattern, chunk.content):
                component_name = match.group(1).strip() if len(match.groups()) > 0 else match.group(0).strip()
                if component_name and component_name not in seen_components:
                    seen_components.add(component_name)
                    facts = _extract_facts_about_component(chunk, component_name)

                    card = WikiCard(
                        card_id=generate_card_id(component_name, WikiCardType.COMPONENT),
                        card_type=WikiCardType.COMPONENT,
                        title=component_name,
                        content=chunk.content,
                        source_ref=chunk.source_file or "",
                        confidence=0.85,
                        facts=facts,
                        metadata={
                            "extracted_from_chunk": chunk.chunk_index,
                        },
                    )
                    cards.append(card)

    return cards


def _compile_task_cards(chunks: List[Chunk], build_id: str) -> List[WikiCard]:
    cards: List[WikiCard] = []
    task_patterns = [
        r"(?:步骤|流程|操作|方法|过程)\s*[：:]\s*(.+)",
        r"(?:拆卸|安装|更换|检查|清洁|润滑)\s*(.+)",
        r"(?:第[一二三四五六七八九十\d]+步)\s*(.+)",
    ]

    import re

    seen_tasks = set()

    for chunk in chunks:
        for pattern in task_patterns:
            for match in re.finditer(pattern, chunk.content):
                task_name = match.group(1).strip() if len(match.groups()) > 0 else match.group(0).strip()
                if task_name and task_name not in seen_tasks:
                    seen_tasks.add(task_name)
                    facts = _extract_procedural_facts(chunk)

                    card = WikiCard(
                        card_id=generate_card_id(task_name, WikiCardType.TASK),
                        card_type=WikiCardType.TASK,
                        title=task_name,
                        content=chunk.content,
                        source_ref=chunk.source_file or "",
                        confidence=0.9,
                        facts=facts,
                        metadata={
                            "procedural": True,
                            "extracted_from_chunk": chunk.chunk_index,
                        },
                    )
                    cards.append(card)

    return cards


def _compile_domain_cards(chunks: List[Chunk], build_id: str) -> List[WikiCard]:
    cards: List[WikiCard] = []
    domain_keywords = [
        "燃油系统", "液压系统", "电气系统", "航电系统", "动力装置",
        "飞行控制", "导航系统", "通信系统", "起落架", "座舱",
    ]

    seen_domains = set()

    for chunk in chunks:
        for keyword in domain_keywords:
            if keyword in chunk.content and keyword not in seen_domains:
                seen_domains.add(keyword)

                card = WikiCard(
                    card_id=generate_card_id(keyword, WikiCardType.DOMAIN),
                    card_type=WikiCardType.DOMAIN,
                    title=keyword,
                    content=chunk.content,
                    source_ref=chunk.source_file or "",
                    confidence=0.8,
                    facts=[],
                    metadata={
                        "domain_keyword": keyword,
                    },
                )
                cards.append(card)

    return cards


def _compile_concept_cards(chunks: List[Chunk], build_id: str) -> List[WikiCard]:
    cards: List[WikiCard] = []
    concept_patterns = [
        r"(?:定义|概念|术语|含义)\s*[：:]\s*(.+)",
        r"(?:[\u4e00-\u9fff]{2,8})\s*[：:]\s*(?:是指|定义为|即)",
    ]

    import re

    seen_concepts = set()

    for chunk in chunks:
        for pattern in concept_patterns:
            for match in re.finditer(pattern, chunk.content):
                concept_name = match.group(1).strip() if len(match.groups()) > 0 else ""
                if concept_name and concept_name not in seen_concepts:
                    seen_concepts.add(concept_name)

                    card = WikiCard(
                        card_id=generate_card_id(concept_name, WikiCardType.CONCEPT),
                        card_type=WikiCardType.CONCEPT,
                        title=concept_name,
                        content=chunk.content,
                        source_ref=chunk.source_file or "",
                        confidence=0.75,
                        facts=[],
                        metadata={
                            "concept_definition": True,
                        },
                    )
                    cards.append(card)

    return cards


def _extract_facts_from_chunks(chunks: List[Chunk]) -> List[Fact]:
    facts: List[Fact] = []
    fact_patterns = [
        r"(?:是|为|称为|定义为)\s*(.+)",
        r"(?:包含|包括|由)\s*(.+)\s*(?:组成|构成)",
        r"(?:用于|作用|功能)\s*(.+)",
        r"(?:参数|规格|性能)\s*[：:]\s*(.+)",
    ]

    import re

    for chunk in chunks:
        for pattern in fact_patterns:
            for match in re.finditer(pattern, chunk.content):
                statement = match.group(1).strip()
                if statement:
                    facts.append(Fact(
                        statement=statement,
                        source_ref=chunk.source_file or "",
                        page_no=chunk.metadata.page_numbers[0] if chunk.metadata.page_numbers else None,
                    ))

    return facts


def _extract_facts_about_component(chunk: Chunk, component_name: str) -> List[Fact]:
    facts: List[Fact] = []
    import re

    patterns = [
        rf"{re.escape(component_name)}\s*(?:是|为|称为)\s*(.+)",
        rf"{re.escape(component_name)}\s*(?:用于|作用)\s*(.+)",
        rf"{re.escape(component_name)}\s*(?:安装在|位于)\s*(.+)",
        rf"(?:拆卸|安装)\s*{re.escape(component_name)}\s*(.+)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, chunk.content):
            statement = match.group(1).strip()
            if statement:
                facts.append(Fact(
                    statement=statement,
                    source_ref=chunk.source_file or "",
                    page_no=chunk.metadata.page_numbers[0] if chunk.metadata.page_numbers else None,
                ))

    return facts


def _extract_procedural_facts(chunk: Chunk) -> List[Fact]:
    facts: List[Fact] = []
    import re

    step_pattern = re.compile(r"(?:第[一二三四五六七八九十\d]+步|步骤[\d]+|[\d]+[\.\、])\s*(.+)", re.MULTILINE)

    for match in step_pattern.finditer(chunk.content):
        statement = match.group(1).strip()
        if statement:
            facts.append(Fact(
                statement=statement,
                source_ref=chunk.source_file or "",
                page_no=chunk.metadata.page_numbers[0] if chunk.metadata.page_numbers else None,
            ))

    return facts


def card_to_json(card: WikiCard) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "card_type": card.card_type.value,
        "title": card.title,
        "content": card.content,
        "source_ref": card.source_ref,
        "confidence": card.confidence,
        "status": card.status.value,
        "facts": [
            {
                "statement": fact.statement,
                "source_ref": fact.source_ref,
                "confidence": fact.confidence,
                "page_no": fact.page_no,
            }
            for fact in card.facts
        ],
        "references": card.references,
        "related_cards": card.related_cards,
        "linked_chunks": card.linked_chunks,
        "metadata": card.metadata,
        "created_at": card.created_at,
        "updated_at": card.updated_at,
    }


def json_to_card(data: dict[str, Any]) -> WikiCard:
    return WikiCard(
        card_id=data["card_id"],
        card_type=WikiCardType(data["card_type"]),
        title=data["title"],
        content=data["content"],
        source_ref=data["source_ref"],
        confidence=data.get("confidence", 1.0),
        status=WikiCardStatus(data.get("status", "draft")),
        facts=[
            Fact(
                statement=fact["statement"],
                source_ref=fact["source_ref"],
                confidence=fact.get("confidence", 1.0),
                page_no=fact.get("page_no"),
            )
            for fact in data.get("facts", [])
        ],
        references=data.get("references", []),
        related_cards=data.get("related_cards", []),
        linked_chunks=data.get("linked_chunks", []),
        metadata=data.get("metadata", {}),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def cards_to_json(cards: List[WikiCard]) -> str:
    return json.dumps([card_to_json(card) for card in cards], ensure_ascii=False, indent=2)
