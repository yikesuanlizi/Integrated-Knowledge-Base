"""5. recall_entities - 从 ES 全文索引召回实体相关 chunks。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.conf.app_config import config
from app.core.log import logger
from app.retrieval.es_repo import ElasticsearchRepository


def _review_filters() -> dict | None:
    return {"status": "approved"} if config.STRICT_REVIEW_GATE else None


def recall_entities_node(state: AgentState) -> dict:
    """同步节点：使用同步 ES 客户端。"""
    entities = state.entities or {}
    part_numbers = entities.get("part_numbers", [])
    components = entities.get("components", [])

    # 同步版本：从 ES 拉
    try:
        es_repo = ElasticsearchRepository()
        all_chunks: list[dict] = []
        filters = _review_filters()

        for pn in part_numbers[:5]:
            try:
                # 同步查询：使用 asyncio.run 桥接
                import asyncio
                results = asyncio.run(es_repo.search_entities(pn, top_k=5, filters=filters))
                all_chunks.extend(results)
            except Exception as e:
                logger.debug(f"ES search for {pn} failed: {e}")

        for comp in components[:5]:
            try:
                import asyncio
                results = asyncio.run(es_repo.search(comp, top_k=5, filters=filters))
                all_chunks.extend(results)
            except Exception as e:
                logger.debug(f"ES search for {comp} failed: {e}")

        return {"entity_results": all_chunks[:10]}
    except Exception as e:
        logger.warning(f"recall_entities failed: {e}")
        return {"entity_results": []}


async def recall_entities_node_async(state: AgentState) -> dict:
    """异步节点：在 event loop 内直接 await。"""
    entities = state.entities or {}
    part_numbers = entities.get("part_numbers", [])
    components = entities.get("components", [])

    try:
        es_repo = ElasticsearchRepository()
        all_chunks: list[dict] = []
        filters = _review_filters()

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

        return {"entity_results": all_chunks[:10]}
    except Exception as e:
        logger.warning(f"recall_entities (async) failed: {e}")
        return {"entity_results": []}
