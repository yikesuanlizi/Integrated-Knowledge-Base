"""3. recall_wiki - 从 PG Wiki 卡片中召回相关卡片。"""
from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

from app.agent.state import AgentState
from app.clients.llm_client import embedding_client
from app.conf.app_config import config
from app.core.log import logger
from app.retrieval.milvus_repo import MilvusRepository
from app.retrieval.query_features import build_query_vector
from app.services.wiki_pg_service import list_pg_wiki_cards


def _review_filters() -> dict | None:
    return {"status": "approved"} if config.STRICT_REVIEW_GATE else None


def _extract_applicability_filters(state: AgentState) -> dict:
    filters = {}
    applicability_filters = state.applicability_filters
    if isinstance(applicability_filters, dict):
        aircraft_model = applicability_filters.get("aircraft_model")
        if aircraft_model and isinstance(aircraft_model, str) and aircraft_model.strip():
            filters["aircraft_model"] = aircraft_model.strip()
        
        manual_type = applicability_filters.get("manual_type")
        if manual_type and isinstance(manual_type, str) and manual_type.strip():
            filters["manual_type"] = manual_type.strip()
        
        ata_chapter = applicability_filters.get("ata_chapter")
        if ata_chapter and isinstance(ata_chapter, str) and ata_chapter.strip():
            filters["ata_chapter"] = ata_chapter.strip()
    
    return filters


def recall_wiki_node(state: AgentState, allow_chunk_fallback: bool = True) -> dict:
    return _run_recall_wiki(state, allow_chunk_fallback=allow_chunk_fallback)


async def recall_wiki_node_async(state: AgentState, allow_chunk_fallback: bool = True) -> dict:
    return await _run_recall_wiki_async(state, allow_chunk_fallback=allow_chunk_fallback)


def _run_recall_wiki(state: AgentState, allow_chunk_fallback: bool = True) -> dict:
    top_k = state.query_features.get("top_k", 5)
    try:
        status = "approved" if config.STRICT_REVIEW_GATE else None
        applicability = _extract_applicability_filters(state)
        
        results, total, wiki_filter_fallback = _search_pg_cards(
            state.question, top_k, status, applicability=applicability
        )
        
        chunk_results = []
        chunk_filter_fallback = False
        if not results and allow_chunk_fallback:
            filters = _build_search_filters(state)
            chunk_results, chunk_filter_fallback = _fallback_chunk_results(
                state.question, max(top_k, 8), filters=filters
            )
        
        filters_applied = bool(applicability)
        filter_conditions = {k: v for k, v in applicability.items() if v}
        
        return {
            "wiki_results": results,
            "chunk_results": chunk_results,
            "wiki_metadata": {
                "filters_applied": filters_applied,
                "filter_conditions": filter_conditions,
                "wiki_filter_fallback": wiki_filter_fallback,
                "chunk_filter_fallback": chunk_filter_fallback,
                "total_matched": total,
            }
        }
    except Exception as e:
        logger.warning(f"recall_wiki failed: {e}")
        return {
            "wiki_results": [],
            "chunk_results": [],
            "wiki_metadata": {
                "filters_applied": False,
                "filter_conditions": {},
                "wiki_filter_fallback": False,
                "chunk_filter_fallback": False,
                "total_matched": 0,
            }
        }


async def _run_recall_wiki_async(state: AgentState, allow_chunk_fallback: bool = True) -> dict:
    top_k = state.query_features.get("top_k", 5)
    try:
        status = "approved" if config.STRICT_REVIEW_GATE else None
        applicability = _extract_applicability_filters(state)
        
        results, total, wiki_filter_fallback = await _search_pg_cards_async(
            state.question, top_k, status, applicability=applicability
        )
        
        chunk_results = []
        chunk_filter_fallback = False
        if not results and allow_chunk_fallback:
            filters = _build_search_filters(state)
            chunk_results, chunk_filter_fallback = await _fallback_chunk_results_async(
                state.question, max(top_k, 8), filters=filters
            )
        
        filters_applied = bool(applicability)
        filter_conditions = {k: v for k, v in applicability.items() if v}
        
        return {
            "wiki_results": results,
            "chunk_results": chunk_results,
            "wiki_metadata": {
                "filters_applied": filters_applied,
                "filter_conditions": filter_conditions,
                "wiki_filter_fallback": wiki_filter_fallback,
                "chunk_filter_fallback": chunk_filter_fallback,
                "total_matched": total,
            }
        }
    except Exception as e:
        logger.warning(f"recall_wiki (async) failed: {e}")
        return {
            "wiki_results": [],
            "chunk_results": [],
            "wiki_metadata": {
                "filters_applied": False,
                "filter_conditions": {},
                "wiki_filter_fallback": False,
                "chunk_filter_fallback": False,
                "total_matched": 0,
            }
        }


def _build_search_filters(state: AgentState) -> dict | None:
    base_filters = _review_filters()
    filters = dict(base_filters) if base_filters else {}
    applicability = _extract_applicability_filters(state)
    filters.update(applicability)
    return filters if filters else None


def _search_pg_cards(
    query: str,
    top_k: int,
    status: str | None,
    applicability: dict | None = None,
):
    applicability = applicability or {}
    wiki_filter_fallback = False
    
    for candidate in _wiki_query_candidates(query, applicability):
        results, total = _run_pg_card_search_sync(
            candidate, top_k, status,
            aircraft_model=applicability.get("aircraft_model"),
            manual_type=applicability.get("manual_type"),
            ata_chapter=applicability.get("ata_chapter"),
        )
        if results:
            return results, total, wiki_filter_fallback
    
    if applicability:
        wiki_filter_fallback = True
        for candidate in _wiki_query_candidates(query, None):
            results, total = _run_pg_card_search_sync(candidate, top_k, status)
            if results:
                return results, total, wiki_filter_fallback
    
    return [], 0, wiki_filter_fallback


async def _search_pg_cards_async(
    query: str,
    top_k: int,
    status: str | None,
    applicability: dict | None = None,
):
    applicability = applicability or {}
    wiki_filter_fallback = False
    
    for candidate in _wiki_query_candidates(query, applicability):
        results, total = await list_pg_wiki_cards(
            1, top_k, status=status, keyword=candidate,
            aircraft_model=applicability.get("aircraft_model"),
            manual_type=applicability.get("manual_type"),
            ata_chapter=applicability.get("ata_chapter"),
        )
        if results:
            return results, total, wiki_filter_fallback
    
    if applicability:
        wiki_filter_fallback = True
        for candidate in _wiki_query_candidates(query, None):
            results, total = await list_pg_wiki_cards(1, top_k, status=status, keyword=candidate)
            if results:
                return results, total, wiki_filter_fallback
    
    return [], 0, wiki_filter_fallback


def _run_pg_card_search_sync(
    query: str,
    top_k: int,
    status: str | None,
    aircraft_model: str | None = None,
    manual_type: str | None = None,
    ata_chapter: str | None = None,
):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            list_pg_wiki_cards(
                1, top_k, status=status, keyword=query,
                aircraft_model=aircraft_model,
                manual_type=manual_type,
                ata_chapter=ata_chapter,
            )
        )
    finally:
        loop.close()


def _wiki_query_candidates(query: str, applicability: dict | None = None) -> list[str]:
    raw = (query or "").strip()
    if not raw:
        return []

    normalized = re.sub(r"[?？!！。；;，,、:：]+", " ", raw)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    stripped = normalized

    suffix_patterns = [
        r"(是什么意思|是什么含义|含义是什么|定义是什么|是什么|指的是什么|指什么|含义|定义)$",
    ]
    for pattern in suffix_patterns:
        stripped = re.sub(pattern, "", stripped).strip()

    candidates: list[str] = []
    for item in (raw, normalized, stripped):
        value = (item or "").strip()
        if value and value not in candidates:
            candidates.append(value)

    parts = [part.strip() for part in re.split(r"\s+", stripped) if len(part.strip()) >= 2]
    if len(parts) > 1:
        compact = "".join(parts)
        if compact and compact not in candidates:
            candidates.append(compact)

    if applicability:
        prefix_parts = []
        if applicability.get("aircraft_model"):
            prefix_parts.append(applicability["aircraft_model"])
        if applicability.get("manual_type"):
            prefix_parts.append(applicability["manual_type"])
        if applicability.get("ata_chapter"):
            prefix_parts.append(applicability["ata_chapter"])
        
        if prefix_parts:
            prefix = "".join(prefix_parts)
            prefixed_candidates = []
            for c in candidates:
                prefixed = prefix + c
                if prefixed not in candidates and prefixed not in prefixed_candidates:
                    prefixed_candidates.append(prefixed)
            candidates = prefixed_candidates + candidates

    return candidates


def _has_applicability_conditions(filters: dict | None, base_filters: dict | None) -> bool:
    if filters is None:
        return False
    if base_filters is None:
        return len(filters) > 0
    return len(filters) > len(base_filters)


def _fallback_chunk_results(question: str, top_k: int, filters: dict | None = None) -> tuple[list[dict], bool]:
    embedding = build_query_vector(question)
    repo = MilvusRepository()
    
    base_filters = _review_filters()
    has_applicability_conditions = _has_applicability_conditions(filters, base_filters)
    
    results = repo.search(embedding, top_k=top_k, filters=filters)
    
    if len(results) == 0 and has_applicability_conditions:
        results = repo.search(embedding, top_k=top_k, filters=base_filters)
        return results, True
    
    return results, False


async def _fallback_chunk_results_async(question: str, top_k: int, filters: dict | None = None) -> tuple[list[dict], bool]:
    embedding = await embedding_client.aembed_text(question)
    repo = MilvusRepository()
    
    base_filters = _review_filters()
    has_applicability_conditions = _has_applicability_conditions(filters, base_filters)
    
    results = repo.search(embedding, top_k=top_k, filters=filters)
    
    if len(results) == 0 and has_applicability_conditions:
        results = repo.search(embedding, top_k=top_k, filters=base_filters)
        return results, True
    
    return results, False
