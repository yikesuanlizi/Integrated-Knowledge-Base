"""LangGraph Agent 编排：12 节点 pipeline。"""
from __future__ import annotations

import functools
import uuid

from langgraph.graph import END, StateGraph

from app.agent.nodes.build_evidence import build_evidence_node
from app.agent.nodes.classify_intent import classify_intent_node
from app.agent.nodes.correct_answer import correct_answer_node
from app.agent.nodes.expand_graph import expand_graph_node
from app.agent.nodes.extract_query import extract_query_node
from app.agent.nodes.generate_answer import generate_answer_node
from app.agent.nodes.merge_results import merge_results_node
from app.agent.nodes.recall_chunks import recall_chunks_node
from app.agent.nodes.recall_entities import recall_entities_node
from app.agent.nodes.recall_structured_metadata import recall_structured_metadata_node
from app.agent.nodes.recall_wiki import recall_wiki_node
from app.agent.nodes.rerank import rerank_node
from app.agent.nodes.validate_evidence import validate_evidence_node, validate_evidence_router
from app.agent.state import AgentState
from app.agent.trace import current_trace_id, finish_node, start_node


def _planner_router(state: AgentState) -> str:
    return getattr(state, "planner_route", "fact") or "fact"


def _wrap_node(name: str, fn):
    """包装 node 函数，自动记录入口/出口耗时和输入输出摘要。"""
    @functools.wraps(fn)
    def wrapper(state):
        trace_id = getattr(state, "trace_id", "") or ""
        token = current_trace_id.set(trace_id)
        input_summary = str(getattr(state, "question", ""))[:200] if name in ("classify_intent", "extract_query") else ""
        start_node(state, name, input_summary)
        try:
            result = fn(state)
            output_summary = ""
            if hasattr(result, "answer") and name == "generate_answer":
                output_summary = str(result.answer)[:200]
            elif hasattr(result, "intent") and name == "classify_intent":
                output_summary = str(getattr(result.intent, "route", ""))[:200]
            finish_node(state, name, output_summary, status="success")
            return result
        except Exception as e:
            finish_node(state, name, "", status="error", error=str(e)[:500])
            raise
        finally:
            current_trace_id.reset(token)
    return wrapper


def _build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("classify_intent", _wrap_node("classify_intent", classify_intent_node))
    builder.add_node("extract_query", _wrap_node("extract_query", extract_query_node))
    builder.add_node("recall_wiki", _wrap_node("recall_wiki", recall_wiki_node))
    builder.add_node("recall_chunks", _wrap_node("recall_chunks", recall_chunks_node))
    builder.add_node("recall_entities", _wrap_node("recall_entities", recall_entities_node))
    builder.add_node("recall_structured_metadata", _wrap_node("recall_structured_metadata", recall_structured_metadata_node))
    builder.add_node("merge_results", _wrap_node("merge_results", merge_results_node))
    builder.add_node("expand_graph", _wrap_node("expand_graph", expand_graph_node))
    builder.add_node("rerank", _wrap_node("rerank", rerank_node))
    builder.add_node("build_evidence", _wrap_node("build_evidence", build_evidence_node))
    builder.add_node("generate_answer", _wrap_node("generate_answer", generate_answer_node))
    builder.add_node("validate_evidence", _wrap_node("validate_evidence", validate_evidence_node))
    builder.add_node("correct_answer", _wrap_node("correct_answer", correct_answer_node))

    builder.set_entry_point("classify_intent")
    builder.add_edge("classify_intent", "extract_query")

    builder.add_conditional_edges(
        "extract_query",
        _planner_router,
        {
            "concept": "recall_wiki",
            "fact": "recall_chunks",
            "complex": "recall_wiki",
        },
    )
    builder.add_edge("recall_wiki", "merge_results")
    builder.add_edge("recall_chunks", "merge_results")
    builder.add_edge("recall_structured_metadata", "merge_results")
    builder.add_edge("recall_entities", "merge_results")
    builder.add_conditional_edges(
        "recall_wiki",
        _planner_router,
        {
            "concept": "merge_results",
            "fact": "merge_results",
            "complex": "recall_chunks",
        },
    )
    builder.add_edge("recall_chunks", "recall_entities")
    builder.add_edge("recall_entities", "recall_structured_metadata")

    # 后续 pipeline
    builder.add_edge("merge_results", "expand_graph")
    builder.add_edge("expand_graph", "rerank")
    builder.add_edge("rerank", "build_evidence")
    builder.add_edge("build_evidence", "generate_answer")
    builder.add_edge("generate_answer", "validate_evidence")

    builder.add_conditional_edges(
        "validate_evidence",
        validate_evidence_router,
        {
            "correct": "correct_answer",
            "done": END,
        },
    )
    builder.add_edge("correct_answer", "extract_query")

    return builder.compile()


# 启动时构建图，失败时降级为 None
try:
    agent_graph = _build_graph()
except Exception as e:
    agent_graph = None
    import logging
    logging.getLogger(__name__).error(f"Failed to build agent graph: {e}")


def run_agent_sync(question: str, top_k: int = 8) -> AgentState:
    """同步执行入口。"""
    trace_id = str(uuid.uuid4())
    initial_state = AgentState(question=question, trace_id=trace_id)
    initial_state.query_features["top_k"] = top_k
    if agent_graph is None:
        initial_state.answer = "Agent graph 未初始化，请检查依赖。"
        return initial_state
    result = agent_graph.invoke(initial_state)
    if isinstance(result, AgentState):
        return result
    if isinstance(result, dict):
        return AgentState(**result)
    return initial_state


async def run_agent(question: str, top_k: int = 8) -> AgentState:
    """异步执行入口。"""
    return run_agent_sync(question, top_k=top_k)
