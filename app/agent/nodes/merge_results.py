"""6. merge_results - 合并三路召回结果并去重，再走一次混合重排 + 写 trace。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.agent.trace import add_stage, record_channel
from app.retrieval.ranking import hybrid_rerank, merge_and_deduplicate


def _tag_with_source(results: list[dict], source_type: str) -> list[dict]:
    """给一批结果打上 source_type 标签，避免改动原字典。"""
    tagged = []
    for item in results:
        item_copy = dict(item) if isinstance(item, dict) else {}
        item_copy["source_type"] = source_type
        tagged.append(item_copy)
    return tagged


def merge_results_node(state: AgentState) -> AgentState:
    chunk_tagged = _tag_with_source(state.chunk_results, "chunk")
    wiki_tagged = _tag_with_source(state.wiki_results, "wiki_card")
    entity_tagged = _tag_with_source(state.entity_results, "entity")
    structured_tagged = _tag_with_source(state.structured_results, "structured_metadata")

    all_results = chunk_tagged + wiki_tagged + entity_tagged + structured_tagged

    merged = merge_and_deduplicate(all_results)

    query_features = state.query_features or {}
    top_k = int(query_features.get("top_k", 10))
    rerank_weight = float(query_features.get("rerank_weight", 0.5))

    reranked = hybrid_rerank(
        query=state.question or "",
        documents=merged,
        semantic_weight=1 - rerank_weight,
        bm25_weight=rerank_weight,
        top_k=max(top_k, 30),
    )

    state.merged_results = reranked[:30]

    if state.retrieval_trace is not None:
        state.retrieval_trace.wiki_hits = [
            {"card_id": r.get("card_id"), "title": r.get("title"), "score": r.get("score")}
            for r in state.wiki_results
        ]
        record_channel(state, "wiki", state.wiki_results, query=state.question)
        record_channel(state, "chunks", state.chunk_results, query=state.question)
        record_channel(state, "entities", state.entity_results, query=state.question)
        structured_decision = {}
        if isinstance(state.metadata_sql_trace, dict):
            structured_decision = state.metadata_sql_trace.get("decision") or {}
        record_channel(
            state,
            "structured_metadata",
            state.structured_results,
            query=state.question,
            used=bool(state.uses_structured_metadata),
            decision=structured_decision,
        )
        add_stage(state, "recall_wiki", "Wiki 卡片召回", hit_count=len(state.wiki_results))
        add_stage(state, "recall_chunks", "原文切块召回", hit_count=len(state.chunk_results))
        add_stage(state, "recall_entities", "实体全文召回", hit_count=len(state.entity_results))
        add_stage(
            state,
            "recall_structured_metadata",
            "结构化元数据召回",
            hit_count=len(state.structured_results),
            decision=structured_decision,
        )
        grounding = state.retrieval_trace.grounding if state.retrieval_trace.grounding else {}
        by_source = {
            "chunk": len(chunk_tagged),
            "wiki_card": len(wiki_tagged),
            "entity": len(entity_tagged),
            "structured_metadata": len(structured_tagged),
        }
        grounding["merge"] = {
            "total": len(state.merged_results),
            "by_source": by_source,
            "input_total": len(all_results),
        }
        state.retrieval_trace.grounding = grounding
        state.retrieval_trace.merged_count = len(state.merged_results)
        add_stage(
            state,
            "merge",
            "合并去重",
            input_total=len(all_results),
            output_total=len(state.merged_results),
            by_source=by_source,
        )

    return state
