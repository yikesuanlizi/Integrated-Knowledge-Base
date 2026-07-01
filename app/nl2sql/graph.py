"""LangGraph topology for the NL2SQL sub-chain.

The FastAPI layer executes the async service directly, while this graph keeps
the node contract explicit for orchestration parity with the document RAG graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, StateGraph


@dataclass
class NL2SQLGraphState:
    question: str = ""
    keywords: list[str] = field(default_factory=list)
    columns: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    values: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    sql: str = ""
    validation_error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)


def _mark(node: str):
    def _inner(state: NL2SQLGraphState) -> NL2SQLGraphState:
        state.trace.append({"node": node})
        return state

    return _inner


def _validation_route(state: NL2SQLGraphState) -> str:
    return "correct" if state.validation_error else "execute"


def build_nl2sql_graph():
    builder = StateGraph(NL2SQLGraphState)
    builder.add_node("extract_keywords", _mark("extract_keywords"))
    builder.add_node("recall_columns", _mark("recall_columns"))
    builder.add_node("recall_metrics", _mark("recall_metrics"))
    builder.add_node("recall_values", _mark("recall_values"))
    builder.add_node("merge_context", _mark("merge_context"))
    builder.add_node("generate_sql", _mark("generate_sql"))
    builder.add_node("validate_sql", _mark("validate_sql"))
    builder.add_node("correct_sql", _mark("correct_sql"))
    builder.add_node("execute_sql", _mark("execute_sql"))
    builder.add_node("explain_result", _mark("explain_result"))

    builder.set_entry_point("extract_keywords")
    # Keep stateful nodes serial unless reducers are added for parallel writes.
    builder.add_edge("extract_keywords", "recall_columns")
    builder.add_edge("recall_columns", "recall_metrics")
    builder.add_edge("recall_metrics", "recall_values")
    builder.add_edge("recall_values", "merge_context")
    builder.add_edge("merge_context", "generate_sql")
    builder.add_edge("generate_sql", "validate_sql")
    builder.add_conditional_edges(
        "validate_sql",
        _validation_route,
        {
            "correct": "correct_sql",
            "execute": "execute_sql",
        },
    )
    builder.add_edge("correct_sql", "validate_sql")
    builder.add_edge("execute_sql", "explain_result")
    builder.add_edge("explain_result", END)
    return builder.compile()


try:
    nl2sql_graph = build_nl2sql_graph()
except Exception:
    nl2sql_graph = None
