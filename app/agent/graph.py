"""LangGraph Agent 编排：12 节点 Agentic RAG Pipeline（包含 Context Builder 上下文构造、Retrieval Planner 动态规划，recall_dispatch 内部调度 4 个召回通道）。"""
from __future__ import annotations

import functools
import uuid
from typing import Any

from langgraph.graph import END, StateGraph

from app.agent.nodes.build_evidence import build_evidence_node
from app.agent.nodes.classify_intent import classify_intent_node
from app.agent.nodes.context_builder import context_builder_node
from app.agent.nodes.correct_answer import correct_answer_node
from app.agent.nodes.expand_graph import expand_graph_node
from app.agent.nodes.extract_query import extract_query_node
from app.agent.nodes.generate_answer import generate_answer_node
from app.agent.nodes.merge_results import merge_results_node
from app.agent.nodes.plan_retrieval import plan_retrieval_node
from app.agent.nodes.recall_dispatch import recall_dispatch_node
from app.agent.nodes.rerank import rerank_node
from app.agent.nodes.validate_evidence import validate_evidence_node, validate_evidence_router
from app.agent.state import AgentState
from app.agent.trace import current_trace_id, finish_node, start_node


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
            if isinstance(result, dict):
                if name == "generate_answer" and "answer" in result:
                    output_summary = str(result["answer"])[:200]
                elif name == "classify_intent" and "intent" in result:
                    output_summary = str(getattr(result["intent"], "route", ""))[:200]
                elif name == "context_builder":
                    ctx = result.get("conversation_context", {}) or {}
                    output_summary = f"resolved={ctx.get('resolved_question', '')}, used_history={ctx.get('used_history', False)}"[:200]
                elif name == "plan_retrieval":
                    plan = result.get("retrieval_plan", {})
                    chs = plan.get("selected_channels", [])
                    fb = " (fallback)" if plan.get("fallback_used") else ""
                    output_summary = f"channels={chs}, strategy={plan.get('strategy', '')}{fb}"[:200]
                elif name == "recall_dispatch":
                    rt = result.get("retrieval_trace")
                    if rt:
                        grounding = getattr(rt, "grounding", {}) or {}
                        dispatch_info = grounding.get("recall_dispatch", {})
                        ch = dispatch_info.get("channels", {})
                        parts = []
                        for cn, ci in ch.items():
                            parts.append(f"{cn}:{ci.get('hit_count', 0)}/{ci.get('status', '?')}")
                        output_summary = ", ".join(parts)[:200]
                if "_node_executions" not in result:
                    node_execs = getattr(state, "_node_executions", [])
                    if node_execs:
                        result["_node_executions"] = list(node_execs)
            elif hasattr(result, "answer") and name == "generate_answer":
                output_summary = str(result.answer)[:200]
            elif hasattr(result, "intent") and name == "classify_intent":
                output_summary = str(getattr(result.intent, "route", ""))[:200]
            elif name == "context_builder":
                ctx = getattr(result, "conversation_context", {}) or {}
                output_summary = f"resolved={ctx.get('resolved_question', '')}, used_history={ctx.get('used_history', False)}"[:200]
            elif name == "plan_retrieval":
                plan = getattr(result, "retrieval_plan", {}) or {}
                chs = plan.get("selected_channels", [])
                fb = " (fallback)" if plan.get("fallback_used") else ""
                output_summary = f"channels={chs}, strategy={plan.get('strategy', '')}{fb}"[:200]
            elif name == "recall_dispatch":
                grounding = getattr(getattr(result, "retrieval_trace", None), "grounding", {}) or {}
                dispatch_info = grounding.get("recall_dispatch", {})
                ch = dispatch_info.get("channels", {})
                parts = []
                for cn, ci in ch.items():
                    parts.append(f"{cn}:{ci.get('hit_count', 0)}/{ci.get('status', '?')}")
                output_summary = ", ".join(parts)[:200]
            finish_node(state, name, output_summary, status="success")
            if isinstance(result, dict):
                node_execs = getattr(state, "_node_executions", [])
                if node_execs:
                    result["_node_executions"] = list(node_execs)
            return result
        except Exception as e:
            finish_node(state, name, "", status="error", error=str(e)[:500])
            raise
        finally:
            current_trace_id.reset(token)
    return wrapper


def _build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("context_builder", _wrap_node("context_builder", context_builder_node))
    builder.add_node("classify_intent", _wrap_node("classify_intent", classify_intent_node))
    builder.add_node("extract_query", _wrap_node("extract_query", extract_query_node))
    builder.add_node("plan_retrieval", _wrap_node("plan_retrieval", plan_retrieval_node))
    builder.add_node("recall_dispatch", _wrap_node("recall_dispatch", recall_dispatch_node))
    builder.add_node("merge_results", _wrap_node("merge_results", merge_results_node))
    builder.add_node("expand_graph", _wrap_node("expand_graph", expand_graph_node))
    builder.add_node("rerank", _wrap_node("rerank", rerank_node))
    builder.add_node("build_evidence", _wrap_node("build_evidence", build_evidence_node))
    builder.add_node("generate_answer", _wrap_node("generate_answer", generate_answer_node))
    builder.add_node("validate_evidence", _wrap_node("validate_evidence", validate_evidence_node))
    builder.add_node("correct_answer", _wrap_node("correct_answer", correct_answer_node))

    builder.set_entry_point("context_builder")
    builder.add_edge("context_builder", "classify_intent")
    builder.add_edge("classify_intent", "extract_query")
    builder.add_edge("extract_query", "plan_retrieval")
    builder.add_edge("plan_retrieval", "recall_dispatch")
    builder.add_edge("recall_dispatch", "merge_results")

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


try:
    agent_graph = _build_graph()
except Exception as e:
    agent_graph = None
    import logging
    logging.getLogger(__name__).error(f"Failed to build agent graph: {e}")


def run_agent_sync(
    question: str,
    top_k: int = 8,
    conversation_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> AgentState:
    """同步执行入口。"""
    trace_id = str(uuid.uuid4())
    initial_state = AgentState(
        question=question,
        original_question=question,
        raw_question=question,
        conversation_id=conversation_id or "",
        history=history or [],
        trace_id=trace_id,
    )
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


async def run_agent(
    question: str,
    top_k: int = 8,
    conversation_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> AgentState:
    """异步执行入口。"""
    return run_agent_sync(question, top_k=top_k, conversation_id=conversation_id, history=history)
