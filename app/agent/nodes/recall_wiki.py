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


def recall_wiki_node(state: AgentState) -> dict:
    return _run_recall_wiki(state)


async def recall_wiki_node_async(state: AgentState) -> dict:
    return await _run_recall_wiki_async(state)


def _run_recall_wiki(state: AgentState) -> dict:
    top_k = state.query_features.get("top_k", 5)
    try:
        status = "approved" if config.STRICT_REVIEW_GATE else None
        results, _ = _search_pg_cards(state.question, top_k, status)
        chunk_results = []
        if not results:
            chunk_results = _fallback_chunk_results(state.question, max(top_k, 8))
        return {"wiki_results": results, "chunk_results": chunk_results}
    except Exception as e:
        logger.warning(f"recall_wiki failed: {e}")
        return {"wiki_results": [], "chunk_results": []}


async def _run_recall_wiki_async(state: AgentState) -> dict:
    top_k = state.query_features.get("top_k", 5)
    try:
        status = "approved" if config.STRICT_REVIEW_GATE else None
        results, _ = await _search_pg_cards_async(state.question, top_k, status)
        chunk_results = []
        if not results:
            chunk_results = await _fallback_chunk_results_async(state.question, max(top_k, 8))
        return {"wiki_results": results, "chunk_results": chunk_results}
    except Exception as e:
        logger.warning(f"recall_wiki (async) failed: {e}")
        return {"wiki_results": [], "chunk_results": []}


def _search_pg_cards(query: str, top_k: int, status: str | None):
    for candidate in _wiki_query_candidates(query):
        results, total = _run_pg_card_search_sync(candidate, top_k, status)
        if results:
            return results, total
    return [], 0


async def _search_pg_cards_async(query: str, top_k: int, status: str | None):
    for candidate in _wiki_query_candidates(query):
        results, total = await list_pg_wiki_cards(1, top_k, status=status, keyword=candidate)
        if results:
            return results, total
    return [], 0


def _run_pg_card_search_sync(query: str, top_k: int, status: str | None):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            lambda: asyncio.run(list_pg_wiki_cards(1, top_k, status=status, keyword=query))
        )
        return future.result()


def _wiki_query_candidates(query: str) -> list[str]:
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

    return candidates


def _fallback_chunk_results(question: str, top_k: int) -> list[dict]:
    embedding = build_query_vector(question)
    repo = MilvusRepository()
    return repo.search(embedding, top_k=top_k, filters=_review_filters())


async def _fallback_chunk_results_async(question: str, top_k: int) -> list[dict]:
    embedding = await embedding_client.aembed_text(question)
    repo = MilvusRepository()
    return repo.search(embedding, top_k=top_k, filters=_review_filters())
