"""9. build_evidence - 构造证据包与引用。"""
from __future__ import annotations

from typing import Dict, List

from app.agent.state import AgentState
from app.agent.trace import add_stage, selected_evidence_from_pack, update_candidate_selection
from app.retrieval.context_build import build_citations, build_evidence_pack


def _annotate_chunk(chunk: dict) -> dict:
    item = dict(chunk)
    item["evidence_type"] = "chunk"
    item["hop_depth"] = chunk.get("hop_depth", 0)
    item["quality"] = chunk.get(
        "quality_score",
        chunk.get("source_quality", 0.5),
    )

    if not item.get("chunk_id"):
        item["chunk_id"] = chunk.get("chunk_id", "")
    if not item.get("doc_id"):
        item["doc_id"] = chunk.get("doc_id", "")

    if item.get("page_numbers"):
        pass
    else:
        source_file = item.get("source_file")
        if source_file:
            item["source_ref"] = source_file
    return item


def _annotate_card(card: dict) -> dict:
    item = dict(card)
    item["evidence_type"] = "wiki_card"
    item["hop_depth"] = card.get("hop_depth", 0)
    item["quality"] = card.get(
        "quality_score",
        card.get("source_quality", 0.5),
    )
    return item


def _annotate_entity(entity: dict) -> dict:
    item = dict(entity)
    item["evidence_type"] = "entity"
    item["hop_depth"] = 0
    item["quality"] = entity.get("source_quality", 0.5)
    return item


def _annotate_structured_metadata(item: dict) -> dict:
    annotated = dict(item)
    annotated["evidence_type"] = "structured_metadata"
    annotated["hop_depth"] = 0
    annotated["quality"] = item.get("quality_score", item.get("score", 0.65))
    annotated["status"] = item.get("status", "approved")
    annotated["freshness"] = item.get("freshness", "current")
    return annotated


def build_evidence_node(state: AgentState) -> AgentState:
    reranked = state.reranked_results or []

    chunks: List[Dict] = [r for r in reranked if r.get("source_type") == "chunk"]
    cards: List[Dict] = [r for r in reranked if r.get("source_type") == "wiki_card"]
    entities: List[Dict] = [r for r in reranked if r.get("source_type") == "entity"]
    structured: List[Dict] = [r for r in reranked if r.get("source_type") == "structured_metadata"]

    top_k = state.query_features.get("top_k", 8) if state.query_features else 8
    max_chunks = top_k
    max_cards = max(3, top_k // 2)
    max_entities = max(1, top_k // 3)
    max_structured = max(1, top_k // 2)

    annotated_chunks = [_annotate_chunk(c) for c in chunks[:max_chunks]]
    annotated_cards = [_annotate_card(c) for c in cards[:max_cards]]
    annotated_entities = [_annotate_entity(e) for e in entities[:max_entities]]
    annotated_structured = [_annotate_structured_metadata(item) for item in structured[:max_structured]]

    evidence_pack = build_evidence_pack(
        annotated_chunks,
        annotated_cards,
        annotated_entities,
        annotated_structured,
        max_chunks=max_chunks,
        max_cards=max_cards,
    )
    state.evidence_pack = evidence_pack
    if annotated_structured and not state.sql_result:
        first_sql = annotated_structured[0].get("sql", "")
        state.sql_result = {
            "sql": first_sql,
            "columns": ["kind", "name", "table_name", "column_name", "description"],
            "rows": [
                {
                    "kind": item.get("kind", ""),
                    "name": item.get("name", ""),
                    "table_name": item.get("table_name", ""),
                    "column_name": item.get("column_name", ""),
                    "description": item.get("description", ""),
                }
                for item in annotated_structured
            ],
            "row_count": len(annotated_structured),
        }

    citations = build_citations(evidence_pack)
    for citation in citations:
        if hasattr(citation, "page_start") and citation.page_start == []:
            citation.page_start = None
        if hasattr(citation, "page_end") and citation.page_end == []:
            citation.page_end = None

    state.citations = [c.model_dump() for c in citations]

    if state.retrieval_trace is not None:
        state.retrieval_trace.citations_used = [c.citation_id for c in citations]
        state.retrieval_trace.evidence_sufficiency = evidence_pack
        state.retrieval_trace.selected_evidence = selected_evidence_from_pack(evidence_pack)
        state.retrieval_trace.grounding["build_evidence"] = {
            "chunks": len(annotated_chunks),
            "cards": len(annotated_cards),
            "entities": len(annotated_entities),
            "structured_metadata": len(annotated_structured),
        }
        update_candidate_selection(state)
        add_stage(
            state,
            "build_evidence",
            "证据包构建",
            evidence_total=evidence_pack.get("total_items", 0),
            citations=len(citations),
            chunks=len(annotated_chunks),
            cards=len(annotated_cards),
            entities=len(annotated_entities),
            structured_metadata=len(annotated_structured),
        )

    return state
