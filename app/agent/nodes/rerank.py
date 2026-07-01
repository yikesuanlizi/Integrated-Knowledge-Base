"""8. rerank - 分层混合重排（chunk / wiki_card / entity 分组 bias 后合并）。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.agent.trace import add_stage
from app.retrieval.ranking import hybrid_rerank, keyword_overlap_score, source_quality_score


def rerank_node(state: AgentState) -> AgentState:
    """分层重排：按 source_type 拆成 chunk / wiki_card / entity / structured_metadata 四组，
    chunk 与 wiki_card 各自跑 hybrid_rerank，entity 用 keyword_overlap_score 打分；
    得到各自 combined_score 后分别乘以 chunk_bias / wiki_bias / entity_bias，
    再按质量阈值过滤，并统一按最终分数排序取 top_k 条。"""
    query = state.question

    top_k = int(state.query_features.get("top_k", 8))
    rerank_weight = float(state.query_features.get("rerank_weight", 0.5))
    chunk_bias = float(state.query_features.get("chunk_bias", 1.0))
    wiki_bias = float(state.query_features.get("wiki_bias", 1.05))
    entity_bias = float(state.query_features.get("entity_bias", 0.8))
    structured_bias = float(state.query_features.get("structured_metadata_bias", 0.75))
    min_quality_threshold = float(state.query_features.get("min_quality_threshold", 0.0))

    documents = state.expanded_results if state.expanded_results else state.merged_results
    if not documents:
        documents = state.chunk_results if state.chunk_results is not None else []
    documents = list(documents or [])

    chunk_docs = []
    wiki_docs = []
    entity_docs = []
    structured_docs = []
    for doc in documents:
        st = doc.get("source_type", "")
        if st == "wiki_card":
            wiki_docs.append(doc)
        elif st == "entity":
            entity_docs.append(doc)
        elif st == "structured_metadata":
            structured_docs.append(doc)
        else:
            chunk_docs.append(doc)

    inner_top_k = max(top_k, len(documents))
    semantic_w = max(0.0, 1.0 - rerank_weight)
    bm25_w = rerank_weight

    chunk_scored = hybrid_rerank(
        query, chunk_docs,
        semantic_weight=semantic_w, bm25_weight=bm25_w, top_k=inner_top_k,
    ) if chunk_docs else []

    wiki_scored = hybrid_rerank(
        query, wiki_docs,
        semantic_weight=semantic_w, bm25_weight=bm25_w, top_k=inner_top_k,
    ) if wiki_docs else []

    entity_scored = []
    for doc in entity_docs:
        content = doc.get("content", "") or doc.get("text", "") or doc.get("value", "")
        kw_score = float(keyword_overlap_score(query, content))
        enriched = doc.copy()
        enriched["combined_score"] = kw_score
        enriched["keyword_overlap"] = kw_score
        enriched["semantic_score"] = 0.0
        enriched["bm25_score"] = 0.0
        enriched["quality_score"] = float(source_quality_score(doc))
        entity_scored.append(enriched)

    structured_scored = []
    for doc in structured_docs:
        content = doc.get("content", "") or doc.get("text", "") or doc.get("description", "")
        kw_score = float(keyword_overlap_score(query, content))
        enriched = doc.copy()
        enriched["combined_score"] = max(kw_score, float(doc.get("score", 0.0) or 0.0))
        enriched["keyword_overlap"] = kw_score
        enriched["semantic_score"] = 0.0
        enriched["bm25_score"] = 0.0
        enriched["quality_score"] = float(source_quality_score(doc))
        structured_scored.append(enriched)

    merged = []
    for doc in chunk_scored:
        d = doc.copy()
        d["final_score"] = float(d.get("combined_score", 0.0)) * chunk_bias
        merged.append(d)
    for doc in wiki_scored:
        d = doc.copy()
        d["final_score"] = float(d.get("combined_score", 0.0)) * wiki_bias
        merged.append(d)
    for doc in entity_scored:
        d = doc.copy()
        d["final_score"] = float(d.get("combined_score", 0.0)) * entity_bias
        merged.append(d)
    for doc in structured_scored:
        d = doc.copy()
        d["final_score"] = float(d.get("combined_score", 0.0)) * structured_bias
        merged.append(d)

    if min_quality_threshold > 0:
        merged = [
            d for d in merged
            if float(d.get("quality_score", 0.0) or 0.0) >= min_quality_threshold
        ]

    merged.sort(key=lambda d: float(d.get("final_score", 0.0)), reverse=True)
    state.reranked_results = merged[:top_k]

    if state.retrieval_trace is not None:
        state.retrieval_trace.reranked_count = len(state.reranked_results)
        state.retrieval_trace.grounding["rerank"] = {
            "input": len(documents),
            "chunks": len(chunk_docs),
            "cards": len(wiki_docs),
            "entities": len(entity_docs),
            "structured_metadata": len(structured_docs),
            "params": {
                "top_k": top_k,
                "rerank_weight": rerank_weight,
                "chunk_bias": chunk_bias,
                "wiki_bias": wiki_bias,
                "entity_bias": entity_bias,
                "structured_metadata_bias": structured_bias,
                "min_quality_threshold": min_quality_threshold,
            },
        }
        add_stage(
            state,
            "rerank",
            "混合重排序",
            input_total=len(documents),
            output_total=len(state.reranked_results),
            chunks=len(chunk_docs),
            cards=len(wiki_docs),
            entities=len(entity_docs),
            structured_metadata=len(structured_docs),
        )

    return state
