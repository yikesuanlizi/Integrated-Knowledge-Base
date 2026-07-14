"""5. recall_entities - 从 ES 全文索引召回实体相关 chunks。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.conf.app_config import config
from app.core.log import logger
from app.retrieval.es_repo import ElasticsearchRepository


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


def _has_applicability_conditions(filters: dict | None, base_filters: dict | None) -> bool:
    if filters is None:
        return False
    if base_filters is None:
        return len(filters) > 0
    return len(filters) > len(base_filters)


def recall_entities_node(state: AgentState) -> dict:
    """同步节点：使用同步 ES 客户端。"""
    entities = state.entities or {}
    part_numbers = entities.get("part_numbers", [])
    components = entities.get("components", [])

    try:
        es_repo = ElasticsearchRepository()
        all_chunks: list[dict] = []
        filters = _build_search_filters(state)
        base_filters = _review_filters()
        has_applicability_conditions = _has_applicability_conditions(filters, base_filters)
        filter_fallback = False

        for pn in part_numbers[:5]:
            try:
                results = _run_in_new_loop(es_repo.search_entities(pn, top_k=5, filters=filters))
                all_chunks.extend(results)
            except Exception as e:
                logger.debug(f"ES search for {pn} failed: {e}")

        for comp in components[:5]:
            try:
                results = _run_in_new_loop(es_repo.search(comp, top_k=5, filters=filters))
                all_chunks.extend(results)
            except Exception as e:
                logger.debug(f"ES search for {comp} failed: {e}")

        if len(all_chunks) == 0 and has_applicability_conditions:
            fallback_chunks: list[dict] = []
            for pn in part_numbers[:5]:
                try:
                    results = _run_in_new_loop(es_repo.search_entities(pn, top_k=5, filters=base_filters))
                    fallback_chunks.extend(results)
                except Exception as e:
                    logger.debug(f"ES search fallback for {pn} failed: {e}")
            for comp in components[:5]:
                try:
                    results = _run_in_new_loop(es_repo.search(comp, top_k=5, filters=base_filters))
                    fallback_chunks.extend(results)
                except Exception as e:
                    logger.debug(f"ES search fallback for {comp} failed: {e}")
            if fallback_chunks:
                all_chunks = fallback_chunks
                filter_fallback = True

        return {
            "entity_results": all_chunks[:10],
            "entity_metadata": {
                "filters_applied": has_applicability_conditions,
                "filter_conditions": filters,
                "filter_fallback": filter_fallback,
            }
        }
    except Exception as e:
        logger.warning(f"recall_entities failed: {e}")
        return {
            "entity_results": [],
            "entity_metadata": {
                "filters_applied": False,
                "filter_conditions": None,
                "filter_fallback": False,
                "error": str(e)[:200],
            }
        }


def _run_in_new_loop(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def recall_entities_node_async(state: AgentState) -> dict:
    """异步节点：在 event loop 内直接 await。"""
    entities = state.entities or {}
    part_numbers = entities.get("part_numbers", [])
    components = entities.get("components", [])

    try:
        es_repo = ElasticsearchRepository()
        all_chunks: list[dict] = []
        filters = _build_search_filters(state)
        base_filters = _review_filters()
        has_applicability_conditions = _has_applicability_conditions(filters, base_filters)
        filter_fallback = False

        for pn in part_numbers[:5]:
            try:
                results = await es_repo.search_entities(pn, top_k=5, filters=filters)
                all_chunks.extend(results)
            except Exception as e:
                logger.debug(f"ES search for {pn} failed: {e}")

        for comp in components[:5]:
            try:
                results = await es_repo.search(comp, top_k=5, filters=filters)
                all_chunks.extend(results)
            except Exception as e:
                logger.debug(f"ES search for {comp} failed: {e}")

        if len(all_chunks) == 0 and has_applicability_conditions:
            fallback_chunks: list[dict] = []
            for pn in part_numbers[:5]:
                try:
                    results = await es_repo.search_entities(pn, top_k=5, filters=base_filters)
                    fallback_chunks.extend(results)
                except Exception as e:
                    logger.debug(f"ES search fallback for {pn} failed: {e}")
            for comp in components[:5]:
                try:
                    results = await es_repo.search(comp, top_k=5, filters=base_filters)
                    fallback_chunks.extend(results)
                except Exception as e:
                    logger.debug(f"ES search fallback for {comp} failed: {e}")
            if fallback_chunks:
                all_chunks = fallback_chunks
                filter_fallback = True

        return {
            "entity_results": all_chunks[:10],
            "entity_metadata": {
                "filters_applied": has_applicability_conditions,
                "filter_conditions": filters,
                "filter_fallback": filter_fallback,
            }
        }
    except Exception as e:
        logger.warning(f"recall_entities (async) failed: {e}")
        return {
            "entity_results": [],
            "entity_metadata": {
                "filters_applied": False,
                "filter_conditions": None,
                "filter_fallback": False,
                "error": str(e)[:200],
            }
        }
