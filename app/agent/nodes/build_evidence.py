"""9. build_evidence - 构造证据包与引用。"""
from __future__ import annotations

import re
from typing import Dict, List, Set

from app.agent.nodes.extract_query import ANSWER_REQUIREMENTS_KEYWORDS
from app.agent.state import AgentState
from app.agent.trace import add_stage, selected_evidence_from_pack, update_candidate_selection
from app.retrieval.context_build import build_citations, build_evidence_pack


WARNING_BLOCK_TYPES = {"warning", "caution", "note", "danger"}
PROCEDURE_BLOCK_TYPES = {"list", "ordered_list", "step", "procedure"}
STEP_PATTERN = re.compile(r"\d+[.、]\s*\S")
PARAMETER_KEYWORDS = {"力矩", "扭矩", "压力", "温度", "参数", "值", "规格", "限制"}
TOOLING_KEYWORDS = {"工具", "设备", "耗材", "材料", "准备"}


def _get_item_id(item: dict, evidence_type: str) -> str:
    if evidence_type == "chunk":
        return item.get("chunk_id", "")
    elif evidence_type == "wiki_card":
        return item.get("card_id", "")
    elif evidence_type == "entity":
        return item.get("entity_id", item.get("value", ""))
    elif evidence_type == "structured_metadata":
        return item.get("name", item.get("id", ""))
    return ""


def _get_item_text(item: dict, evidence_type: str) -> str:
    parts = []
    if evidence_type == "wiki_card":
        parts.append(item.get("title", ""))
        parts.append(item.get("text", ""))
        parts.append(item.get("content", ""))
    parts.append(item.get("content", ""))
    parts.append(item.get("raw_content", ""))
    parts.append(item.get("search_content", ""))
    return " ".join(str(p) for p in parts if p)


def _get_block_type(item: dict) -> str:
    block_type = item.get("block_type", "")
    if not block_type:
        metadata = item.get("metadata", {})
        if isinstance(metadata, dict):
            block_type = metadata.get("block_type", "")
    return str(block_type).lower() if block_type else ""


def _collect_applicability(item: dict, stats: dict) -> None:
    metadata = item.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    for field_name, set_key in [
        ("aircraft_model", "aircraft_models"),
        ("manual_type", "manual_types"),
        ("ata_chapter", "ata_chapters"),
        ("manual_revision", "revisions"),
    ]:
        value = item.get(field_name) or metadata.get(field_name)
        if value:
            stats[set_key].add(str(value))


def _mark_evidence_roles(item: dict, evidence_type: str) -> List[str]:
    roles: Set[str] = set()
    text = _get_item_text(item, evidence_type)
    block_type = _get_block_type(item)

    if block_type in WARNING_BLOCK_TYPES:
        roles.add("warning")

    is_procedure = block_type in PROCEDURE_BLOCK_TYPES
    if not is_procedure and text:
        text_lower = text.lower()
        has_step_pattern = bool(STEP_PATTERN.search(text))
        has_procedure_kw = any(kw.lower() in text_lower for kw in ANSWER_REQUIREMENTS_KEYWORDS["procedure"])
        if has_step_pattern and has_procedure_kw:
            is_procedure = True
    if is_procedure:
        roles.add("procedure")

    if block_type == "table":
        roles.add("parameter")
    else:
        text_lower = text.lower()
        for kw in PARAMETER_KEYWORDS:
            if kw in text or kw.lower() in text_lower:
                roles.add("parameter")
                break
        for kw in ANSWER_REQUIREMENTS_KEYWORDS["parameter"]:
            if kw.lower() in text_lower:
                roles.add("parameter")
                break

    text_lower = text.lower()
    for kw in TOOLING_KEYWORDS:
        if kw in text or kw.lower() in text_lower:
            roles.add("tooling")
            break
    for kw in ANSWER_REQUIREMENTS_KEYWORDS["tooling"]:
        if kw.lower() in text_lower:
            roles.add("tooling")
            break

    return sorted(roles)


def _generate_applicability_summary(stats: dict) -> str:
    parts = []
    models = stats.get("aircraft_models", [])
    if models:
        parts.append("、".join(models))

    manual_parts = []
    manual_types = stats.get("manual_types", [])
    if manual_types:
        manual_parts.append(manual_types[0])
    chapters = stats.get("ata_chapters", [])
    if chapters:
        manual_parts.append("、".join(f"{ch}章" for ch in chapters))
    if manual_parts:
        parts.append(" ".join(manual_parts))

    if not parts:
        return ""
    return "适用范围：" + "，".join(parts)


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

    evidence_roles: Dict[str, List[str]] = {}
    applicability_stats = {
        "aircraft_models": set(),
        "manual_types": set(),
        "ata_chapters": set(),
        "revisions": set(),
    }

    evidence_items = [
        (annotated_chunks, "chunk"),
        (annotated_cards, "wiki_card"),
        (annotated_entities, "entity"),
        (annotated_structured, "structured_metadata"),
    ]
    for items, ev_type in evidence_items:
        for item in items:
            try:
                item_id = _get_item_id(item, ev_type)
                if item_id:
                    roles = _mark_evidence_roles(item, ev_type)
                    if roles:
                        evidence_roles[item_id] = roles
                _collect_applicability(item, applicability_stats)
            except Exception:
                continue

    state.evidence_roles = evidence_roles
    state.applicability_stats = {
        "aircraft_models": sorted(applicability_stats["aircraft_models"]),
        "manual_types": sorted(applicability_stats["manual_types"]),
        "ata_chapters": sorted(applicability_stats["ata_chapters"]),
        "revisions": sorted(applicability_stats["revisions"]),
    }
    state.applicability_summary = _generate_applicability_summary(state.applicability_stats)

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
        state.retrieval_trace.evidence_roles = state.evidence_roles
        state.retrieval_trace.applicability_stats = state.applicability_stats
        state.retrieval_trace.applicability_summary = state.applicability_summary
        state.retrieval_trace.grounding["build_evidence"] = {
            "chunks": len(annotated_chunks),
            "cards": len(annotated_cards),
            "entities": len(annotated_entities),
            "structured_metadata": len(annotated_structured),
        }
        update_candidate_selection(state)
        role_counts: Dict[str, int] = {}
        for roles in evidence_roles.values():
            for role in roles:
                role_counts[role] = role_counts.get(role, 0) + 1
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
            evidence_roles_count=role_counts,
            applicability_summary=state.applicability_summary,
        )

    return state
