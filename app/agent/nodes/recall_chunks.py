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


def recall_chunks_node(state: AgentState) -> dict:
    return _run(state)


async def recall_chunks_node_async(state: AgentState) -> dict:
    return await _run_async(state)


def _run(state: AgentState) -> dict:
    top_k = state.query_features.get("top_k", 8)
    try:
        embedding = build_query_vector(state.question)
        repo = MilvusRepository()
        results = repo.search(embedding, top_k=top_k, filters=_review_filters())
        return {"chunk_results": results}
    except Exception as e:
        logger.warning(f"recall_chunks failed: {e}")
        return {"chunk_results": []}


async def _run_async(state: AgentState) -> dict:
    top_k = state.query_features.get("top_k", 8)
    try:
        embedding = await embedding_client.aembed_text(state.question)
        repo = MilvusRepository()
        results = repo.search(embedding, top_k=top_k, filters=_review_filters())
        return {"chunk_results": results}
    except Exception as e:
        logger.warning(f"recall_chunks (async) failed: {e}")
        return {"chunk_results": []}
