"""11. validate_evidence - 证据充分性验证。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.agent.trace import add_stage
from app.retrieval.context_build import calculate_evidence_sufficiency


def validate_evidence_node(state: AgentState) -> AgentState:
    route = getattr(getattr(state, "intent", None), "route", "") or state.planner_route or "fact"
    min_chunks = state.query_features.get("min_chunks")
    min_cards = state.query_features.get("min_cards")
    require_evidence = state.query_features.get("require_evidence")

    if route == "concept":
        min_chunks = 0 if min_chunks is None else min_chunks
        min_cards = 1 if min_cards is None else min_cards
        require_evidence = True if require_evidence is None else require_evidence
    elif route == "complex":
        min_chunks = 1 if min_chunks is None else min_chunks
        min_cards = 1 if min_cards is None else min_cards
        require_evidence = True if require_evidence is None else require_evidence
    else:
        min_chunks = 2 if min_chunks is None else min_chunks
        min_cards = 0 if min_cards is None else min_cards
        require_evidence = False if require_evidence is None else require_evidence

    evidence_config = {
        "min_chunks": min_chunks,
        "min_cards": min_cards,
        "require_evidence": require_evidence,
        "route": route,
    }
    sufficiency = calculate_evidence_sufficiency(state.evidence_pack, evidence_config)
    state.evidence_sufficiency = sufficiency
    if state.retrieval_trace:
        state.retrieval_trace.evidence_sufficiency = sufficiency
        add_stage(
            state,
            "validate_evidence",
            "证据充分性校验",
            sufficient=sufficiency.get("sufficient", False),
            score=sufficiency.get("score", 0.0),
            blocked_by_review=sufficiency.get("blocked_by_review", False),
        )

    if sufficiency.get("blocked_by_review"):
        state.answer = "当前召回到的候选证据尚未审核通过，严格审核模式下不能用于回答。请先在治理中心完成审核，或补充已审核知识后再查询。"
        state.needs_clarification = True

    # 安全敏感问题，证据不足时直接提示
    if state.intent and state.intent.safety_sensitive and not sufficiency.get("sufficient", False):
        state.answer = "⚠️ 安全相关问题需要更充分的证据支持，请参考官方维修手册或咨询工程师。"
        state.needs_clarification = True
    return state


def validate_evidence_router(state: AgentState) -> str:
    if state.evidence_sufficiency.get("blocked_by_review"):
        return "done"
    if state.iteration >= state.max_iterations:
        return "done"
    if state.evidence_sufficiency.get("sufficient", True):
        return "done"
    return "correct"
