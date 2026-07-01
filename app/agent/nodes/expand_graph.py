"""7. expand_graph - 沿 Wiki 卡片 wikilink 图扩展 N-hop。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.agent.trace import add_stage
from app.retrieval.graph_expand import expand_from_recalled


def expand_graph_node(state: AgentState) -> AgentState:
    hops = state.query_features.get("graph_expand_hops", 1)
    max_expand = state.query_features.get("max_expand", 20)
    keyword_threshold = state.query_features.get("keyword_threshold", 0.1)
    wiki_cards = state.wiki_results
    all_cards = wiki_cards.copy()
    query_text = getattr(state, "question", "") or ""

    expanded = expand_from_recalled(
        wiki_cards,
        all_cards,
        query=query_text,
        hops=hops,
        max_expand=max_expand,
        min_keyword_threshold=keyword_threshold,
    )

    expanded_sorted = sorted(
        expanded,
        key=lambda c: float(c.get("final_score", 0.0)),
        reverse=True,
    )[:30]

    seen_ids: set = set()
    out: list[dict] = []
    for card in expanded_sorted:
        cid = card.get("card_id")
        if cid and cid in seen_ids:
            continue
        if cid:
            seen_ids.add(cid)
        out.append(card)
    state.expanded_results = out
    if state.retrieval_trace is not None:
        state.retrieval_trace.context_expanded = len(out) > len(wiki_cards)
        grounding = getattr(state.retrieval_trace, "grounding", None)
        if grounding is None:
            grounding = {}
            try:
                state.retrieval_trace.grounding = grounding
            except Exception:
                grounding = None
        if isinstance(grounding, dict):
            grounding["expand"] = {
                "seed_count": len(wiki_cards),
                "expanded_count": len(out),
                "hops": hops,
                "params": {
                    "max_expand": max_expand,
                    "min_keyword_threshold": keyword_threshold,
                },
            }
            add_stage(
                state,
                "expand_graph",
                "Wiki 图扩展",
                seed_count=len(wiki_cards),
                expanded_count=len(out),
                hops=hops,
            )
    return state
