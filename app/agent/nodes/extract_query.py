"""2. extract_query - 抽取查询关键词、实体、查询变体。"""
from __future__ import annotations

import asyncio

from app.agent.state import AgentState
from app.agent.trace import add_stage
from app.retrieval.query_features import (
    QueryFeatures,
    extract_query_entities,
    hybrid_rewrite_query,
)


def extract_query_node(state: AgentState) -> AgentState:
    """同步版本：仅本地规则扩展。"""
    features = QueryFeatures(state.question)
    features.extract()
    state.query_features = {
        **state.query_features,
        "query_variants": features.query_variants,
        "synonyms": features.synonyms,
    }
    state.entities = extract_query_entities(state.question)
    if state.retrieval_trace:
        state.retrieval_trace.query_variants = features.query_variants
        add_stage(
            state,
            "extract_query",
            "查询特征抽取",
            variants=len(features.query_variants),
            entities=state.entities,
        )
    return state


async def extract_query_node_async(state: AgentState) -> AgentState:
    """异步版本：含 LLM 改写。"""
    features = QueryFeatures(state.question)
    features.extract()
    llm_variants = await hybrid_rewrite_query(state.question)
    all_variants = list(set(features.build_fusion_queries() + llm_variants))
    state.query_features = {
        **state.query_features,
        "query_variants": all_variants[:8],
        "synonyms": features.synonyms,
    }
    state.entities = extract_query_entities(state.question)
    if state.retrieval_trace:
        state.retrieval_trace.query_variants = all_variants[:8]
        add_stage(
            state,
            "extract_query",
            "查询特征抽取",
            variants=len(all_variants[:8]),
            entities=state.entities,
        )
    return state
