from __future__ import annotations

from typing import List

from app.models.schemas import Citation


def build_evidence_pack(
    chunks: List[dict],
    wiki_cards: List[dict],
    entities: List[dict],
    structured_metadata: List[dict] | None = None,
    max_chunks: int = 8,
    max_cards: int = 5,
) -> dict:
    evidence_items: List[dict] = []
    structured_metadata = structured_metadata or []

    for i, chunk in enumerate(chunks[:max_chunks]):
        evidence_items.append({
            "type": "chunk",
            "chunk_id": chunk.get("chunk_id", ""),
            "doc_id": chunk.get("doc_id", ""),
            "content": chunk.get("content", ""),
            "source_file": chunk.get("source_file", ""),
            "section_path": chunk.get("section_path"),
            "page_numbers": chunk.get("page_numbers"),
            "block_type": chunk.get("block_type"),
            "status": chunk.get("status", "approved"),
            "freshness": chunk.get("freshness", "current"),
            "score": chunk.get("score", 0.0),
            "bm25_score": chunk.get("bm25_score", 0.0),
            "combined_score": chunk.get("combined_score", 0.0),
        })

    for card in wiki_cards[:max_cards]:
        evidence_items.append({
            "type": "wiki_card",
            "card_id": card.get("card_id", ""),
            "card_type": card.get("card_type"),
            "title": card.get("title", ""),
            "content": card.get("content", ""),
            "source_ref": card.get("source_ref", ""),
            "status": card.get("status"),
            "freshness": card.get("freshness", "current"),
            "score": card.get("score", 0.0),
        })

    for entity in entities[:5]:
        evidence_items.append({
            "type": "entity",
            "entity_type": entity.get("entity_type"),
            "value": entity.get("value", ""),
            "count": entity.get("count", 0),
            "score": entity.get("score", 0.0),
        })

    for item in structured_metadata[:5]:
        evidence_items.append({
            "type": "structured_metadata",
            "kind": item.get("kind", "metadata"),
            "name": item.get("name", ""),
            "table_name": item.get("table_name", ""),
            "column_name": item.get("column_name", ""),
            "description": item.get("description", ""),
            "content": item.get("content", ""),
            "sql": item.get("sql", ""),
            "status": item.get("status", "approved"),
            "freshness": item.get("freshness", "current"),
            "score": item.get("score", 0.0),
        })

    return {
        "evidence_items": evidence_items,
        "chunk_count": len(chunks[:max_chunks]),
        "card_count": len(wiki_cards[:max_cards]),
        "entity_count": len(entities[:5]),
        "structured_metadata_count": len(structured_metadata[:5]),
        "total_items": len(evidence_items),
    }


def build_context_for_llm(evidence_pack: dict, max_tokens: int = 8000) -> str:
    items = evidence_pack.get("evidence_items", [])

    context_parts: List[str] = []
    total_chars = 0

    for item in items:
        if item["type"] == "chunk":
            part = f"""## 文档片段
**来源**: {item.get('source_file', '')}
**章节**: {item.get('section_path', '')}
**页码**: {item.get('page_numbers', '')}
**类型**: {item.get('block_type', '')}
**审核状态**: {item.get('status', 'approved')}
**新鲜度**: {item.get('freshness', 'current')}
**相关性**: {item.get('combined_score', item.get('score', 0)):.3f}

{item.get('content', '')}
"""
        elif item["type"] == "wiki_card":
            part = f"""## Wiki卡片
**标题**: {item.get('title', '')}
**类型**: {item.get('card_type', '')}
**来源**: {item.get('source_ref', '')}
**状态**: {item.get('status', '')}
**新鲜度**: {item.get('freshness', 'current')}
**相关性**: {item.get('score', 0):.3f}

{item.get('content', '')}
"""
        elif item["type"] == "entity":
            part = f"""## 实体
**类型**: {item.get('entity_type', '')}
**值**: {item.get('value', '')}
**出现次数**: {item.get('count', 0)}
"""
        elif item["type"] == "structured_metadata":
            part = f"""## 结构化元数据辅助
**类型**: {item.get('kind', '')}
**名称**: {item.get('name', '')}
**表/字段**: {item.get('table_name', '')}.{item.get('column_name', '')}
**状态**: {item.get('status', 'approved')}
**新鲜度**: {item.get('freshness', 'current')}

{item.get('content') or item.get('description', '')}
"""
        else:
            continue

        if total_chars + len(part) > max_tokens * 4:
            break

        context_parts.append(part)
        total_chars += len(part)

    return "\n\n".join(context_parts)


def build_citations(evidence_pack: dict) -> List[Citation]:
    citations: List[Citation] = []
    citation_id = 1

    for item in evidence_pack.get("evidence_items", []):
        if item["type"] == "chunk":
            section_path = item.get("section_path") or ""
            source_file = item.get("source_file", "")
            if section_path and source_file:
                source_ref = f"{section_path} | {source_file}"
            else:
                source_ref = section_path or source_file

            citation = Citation(
                citation_id=citation_id,
                chunk_id=item.get("chunk_id", ""),
                doc_id=item.get("doc_id", ""),
                file_name=source_file,
                source_ref=source_ref,
                page_start=item.get("page_numbers", [None])[0] if item.get("page_numbers") else None,
                page_end=item.get("page_numbers", [None])[-1] if item.get("page_numbers") else None,
                section_path=item.get("section_path"),
                block_type=item.get("block_type"),
                score=item.get("combined_score", item.get("score", 0.0)),
                snippet=item.get("content", "")[:200],
            )
            citations.append(citation)
            citation_id += 1
        elif item["type"] == "wiki_card":
            citation = Citation(
                citation_id=citation_id,
                chunk_id="",
                doc_id="",
                file_name="",
                source_ref=item.get("source_ref", ""),
                section_path=item.get("card_type"),
                block_type="wiki_card",
                score=item.get("score", 0.0),
                snippet=item.get("content", "")[:200],
                card_id=item.get("card_id", ""),
            )
            citations.append(citation)
            citation_id += 1

    return citations


def calculate_evidence_sufficiency(
    evidence_pack: dict,
    intent_config: dict,
) -> dict:
    items = evidence_pack.get("evidence_items", [])
    chunk_items = [i for i in items if i["type"] == "chunk"]
    card_items = [i for i in items if i["type"] == "wiki_card"]
    entity_items = [i for i in items if i["type"] == "entity"]
    structured_items = [i for i in items if i["type"] == "structured_metadata"]
    blocked_items = [
        i for i in chunk_items + card_items
        if (i.get("status") or "approved") != "approved"
    ]

    min_chunks = intent_config.get("min_chunks", 2)
    min_cards = intent_config.get("min_cards", 0)
    require_evidence = intent_config.get("require_evidence", False)
    route = str(intent_config.get("route", "") or "").strip()

    if route == "concept":
        chunk_score = 1.0 if min_chunks <= 0 else min(len(chunk_items) / min_chunks, 1.0)
        card_score = min(len(card_items) / max(min_cards, 1), 1.0)
        entity_score = min(len(entity_items) / 3, 1.0)
        average_score = max(card_score, (card_score * 0.8) + (entity_score * 0.2))
        is_sufficient = len(card_items) >= max(min_cards, 1)
    elif route == "complex":
        chunk_score = min(len(chunk_items) / max(min_chunks, 1), 1.0)
        card_score = min(len(card_items) / max(min_cards, 1), 1.0)
        entity_score = min(len(entity_items) / 3, 1.0)
        average_score = (chunk_score + card_score + entity_score) / 3
        is_sufficient = len(chunk_items) >= max(min_chunks, 1) and len(card_items) >= max(min_cards, 1)
    else:
        chunk_score = min(len(chunk_items) / min_chunks, 1.0) if min_chunks > 0 else 1.0
        card_score = min(len(card_items) / min_cards, 1.0) if min_cards > 0 else 1.0
        entity_score = min(len(entity_items) / 3, 1.0)
        average_score = (chunk_score + card_score + entity_score) / 3
        is_sufficient = average_score >= 0.5

    if require_evidence:
        is_sufficient = is_sufficient and (len(chunk_items) + len(card_items)) >= 1
    if blocked_items:
        is_sufficient = False

    return {
        "sufficient": is_sufficient,
        "score": average_score,
        "chunk_count": len(chunk_items),
        "card_count": len(card_items),
        "entity_count": len(entity_items),
        "structured_metadata_count": len(structured_items),
        "min_chunks_required": min_chunks,
        "min_cards_required": min_cards,
        "require_evidence": require_evidence,
        "route": route or "fact",
        "blocked_by_review": bool(blocked_items),
        "blocked_evidence_count": len(blocked_items),
    }


def merge_evidence_sources(
    chunks: List[dict],
    cards: List[dict],
    entities: List[dict],
) -> List[dict]:
    all_items: List[dict] = []

    for chunk in chunks:
        all_items.append({**chunk, "source_type": "chunk"})

    for card in cards:
        all_items.append({**card, "source_type": "wiki_card"})

    for entity in entities:
        all_items.append({**entity, "source_type": "entity"})

    all_items.sort(key=lambda x: x.get("combined_score", x.get("score", 0.0)), reverse=True)

    return all_items
