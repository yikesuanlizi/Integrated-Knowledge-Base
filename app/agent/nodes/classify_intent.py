"""1. classify_intent - 用户意图分类，决定后续检索策略。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.agent.trace import add_stage
from app.retrieval.intent import classify_intent, get_intent_config


def classify_intent_node(state: AgentState) -> AgentState:
    if not state.original_question:
        state.original_question = state.question
    intent = classify_intent(state.question)
    state.intent = intent
    intent_config = get_intent_config(intent)
    state.query_features = intent_config
    state.planner_route = intent.route
    state.keywords = intent.keywords
    state.entities = intent.entities

    # 记录 trace
    if state.retrieval_trace:
        state.retrieval_trace.intent = intent
        state.retrieval_trace.strategy = intent.route
        add_stage(
            state,
            "classify",
            "意图分类",
            intent=intent.primary,
            confidence=intent.confidence,
            route=intent.route,
        )

    return state
