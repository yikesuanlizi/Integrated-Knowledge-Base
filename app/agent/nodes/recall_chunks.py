"""4. recall_chunks - 从原始 chunk 向量库召回相关片段。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.clients.llm_client import embedding_client
from app.conf.app_config import config
from app.core.log import logger
from app.retrieval.milvus_repo import MilvusRepository
from app.retrieval.query_features import build_query_vector


def _review_filters() -> dict | None:
    return {"status": "approved"} if config.STRICT_REVIEW_GATE else None


def _build_search_filters(state: AgentState) -> dict | None:
    base_filters = _review_filters()
    filters = dict(base_filters) if base_filters else {}
    
    applicability_filters = state.applicability_filters
    if isinstance(applicability_filters, dict):
        aircraft_model = applicability_filters.get("aircraft_model")
        if aircraft_model and isinstance(aircraft_model, str) and aircraft_model.strip():
            filters["aircraft_model"] = aircraft_model
        
        manual_type = applicability_filters.get("manual_type")
        if manual_type and isinstance(manual_type, str) and manual_type.strip():
            filters["manual_type"] = manual_type
        
        ata_chapter = applicability_filters.get("ata_chapter")
        if ata_chapter and isinstance(ata_chapter, str) and ata_chapter.strip():
            filters["ata_chapter"] = ata_chapter
    
    return filters if filters else None


def recall_chunks_node(state: AgentState) -> dict:
    return _run(state)


async def recall_chunks_node_async(state: AgentState) -> dict:
    return await _run_async(state)


def _has_applicability_conditions(filters: dict | None, base_filters: dict | None) -> bool:
    if filters is None:
        return False
    if base_filters is None:
        return len(filters) > 0
    return len(filters) > len(base_filters)


def _run(state: AgentState) -> dict:
    top_k = state.query_features.get("top_k", 8)
    try:
        embedding = build_query_vector(state.question)
        repo = MilvusRepository()
        
        filters = _build_search_filters(state)
        base_filters = _review_filters()
        has_applicability_conditions = _has_applicability_conditions(filters, base_filters)
        
        results = repo.search(embedding, top_k=top_k, filters=filters)
        filter_fallback = False
        
        if len(results) == 0 and has_applicability_conditions:
            results = repo.search(embedding, top_k=top_k, filters=base_filters)
            filter_fallback = True
        
        return {
            "chunk_results": results,
            "filters_applied": has_applicability_conditions,
            "filter_conditions": filters,
            "filter_fallback": filter_fallback
        }
    except Exception as e:
        logger.warning(f"recall_chunks failed: {e}")
        return {"chunk_results": []}


async def _run_async(state: AgentState) -> dict:
    top_k = state.query_features.get("top_k", 8)
    try:
        embedding = await embedding_client.aembed_text(state.question)
        repo = MilvusRepository()
        
        filters = _build_search_filters(state)
        base_filters = _review_filters()
        has_applicability_conditions = _has_applicability_conditions(filters, base_filters)
        
        results = repo.search(embedding, top_k=top_k, filters=filters)
        filter_fallback = False
        
        if len(results) == 0 and has_applicability_conditions:
            results = repo.search(embedding, top_k=top_k, filters=base_filters)
            filter_fallback = True
        
        return {
            "chunk_results": results,
            "filters_applied": has_applicability_conditions,
            "filter_conditions": filters,
            "filter_fallback": filter_fallback
        }
    except Exception as e:
        logger.warning(f"recall_chunks (async) failed: {e}")
        return {"chunk_results": []}
