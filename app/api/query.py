"""问答 API：LangGraph Agent 入口。"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.nodes.build_evidence import build_evidence_node
from app.agent.nodes.classify_intent import classify_intent_node
from app.agent.nodes.context_builder import context_builder_node
from app.agent.nodes.correct_answer import correct_answer_node
from app.agent.nodes.expand_graph import expand_graph_node
from app.agent.nodes.extract_query import extract_query_node
from app.agent.nodes.generate_answer import (
    _fallback_answer,
    _finalize_answer_text,
    build_answer_messages,
)
from app.agent.nodes.merge_results import merge_results_node
from app.agent.nodes.plan_retrieval import plan_retrieval_node
from app.agent.nodes.recall_dispatch import recall_dispatch_node
from app.agent.nodes.rerank import rerank_node
from app.agent.nodes.validate_evidence import validate_evidence_node, validate_evidence_router
from app.agent.state import AgentState
from app.agent.trace import current_trace_id, finish_node, start_node
from app.clients.llm_client import llm_client
from app.core.log import logger
from app.models.schemas import QueryRequest
from app.services.monitor_service import save_query_trace_fire_and_forget

router = APIRouter(tags=["query"])


_RECALL_NODES: list[tuple[str, str, Any]] = [
    ("context_builder", "上下文构造", context_builder_node),
    ("classify_intent", "意图分类", classify_intent_node),
    ("extract_query", "查询特征抽取", extract_query_node),
    ("plan_retrieval", "检索规划", plan_retrieval_node),
    ("recall_dispatch", "多路召回", recall_dispatch_node),
    ("merge_results", "合并去重", merge_results_node),
    ("expand_graph", "Wiki图扩展", expand_graph_node),
    ("rerank", "混合重排序", rerank_node),
    ("build_evidence", "证据包构建", build_evidence_node),
]

_CORRECTION_NODES: list[tuple[str, str, Any]] = [
    ("correct_answer", "查询反思改写", correct_answer_node),
    ("extract_query", "查询特征抽取", extract_query_node),
    ("plan_retrieval", "检索规划（重规划）", plan_retrieval_node),
    ("recall_dispatch", "多路召回（重检索）", recall_dispatch_node),
    ("merge_results", "合并去重", merge_results_node),
    ("expand_graph", "Wiki图扩展", expand_graph_node),
    ("rerank", "混合重排序", rerank_node),
    ("build_evidence", "证据包构建", build_evidence_node),
]


@router.post("/")
async def query_knowledge(request: QueryRequest):
    """执行一次 Agent 问答（非流式）。"""
    try:
        from app.agent.orchestrator import run_unified_query
        return await run_unified_query(
            request.question,
            top_k=request.top_k,
            conversation_id=request.conversation_id,
            history=[turn.model_dump() for turn in request.history],
        )
    except Exception as e:
        logger.error(f"Unified query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _run_node_sync(state: AgentState, name: str, label: str, fn) -> AgentState:
    tid = getattr(state, "trace_id", "") or ""
    tok = current_trace_id.set(tid)
    start_node(state, name, "")
    try:
        result = fn(state)
        finish_node(state, name, "", status="success")
        return result
    except Exception as e:
        finish_node(state, name, "", status="error", error=str(e)[:500])
        raise
    finally:
        current_trace_id.reset(tok)


@router.post("/stream")
async def query_stream(request: QueryRequest):
    """SSE 流式问答：先执行完整 Agentic RAG 检索+校验+纠错循环（节点进度实时推送），再流式输出答案 token。"""

    async def generate():
        trace_id = str(uuid.uuid4())
        state = AgentState(
            question=request.question,
            raw_question=request.question,
            original_question=request.question,
            conversation_id=request.conversation_id or "",
            history=[turn.model_dump() for turn in request.history],
            trace_id=trace_id,
        )
        state.query_features["top_k"] = request.top_k

        tok = current_trace_id.set(trace_id)
        try:
            for node_name, label, fn in _RECALL_NODES:
                yield _sse("node", {"node": node_name, "label": label})
                try:
                    state = await asyncio.to_thread(_run_node_sync, state, node_name, label, fn)
                except Exception as e:
                    logger.error(f"Node {node_name} failed: {e}", exc_info=True)
                    yield _sse("error", {"error": f"{label}失败: {e}"})
                    return

                if node_name == "context_builder":
                    intent = state.intent
                    intent_data = intent.model_dump() if hasattr(intent, "model_dump") else {"route": getattr(intent, "route", "")}
                    yield _sse("intent", intent_data)
                    from app.retrieval.intent import get_intent_config
                    config_data = get_intent_config(intent)
                    yield _sse("config", config_data)

            validate_label = "证据充分性校验"
            yield _sse("node", {"node": "validate_evidence", "label": validate_label})
            try:
                state = await asyncio.to_thread(_run_node_sync, state, "validate_evidence", validate_label, validate_evidence_node)
            except Exception as e:
                logger.error(f"Node validate_evidence failed: {e}", exc_info=True)
                yield _sse("error", {"error": f"{validate_label}失败: {e}"})
                return

            while validate_evidence_router(state) == "correct":
                for node_name, label, fn in _CORRECTION_NODES:
                    yield _sse("node", {"node": node_name, "label": label})
                    try:
                        state = await asyncio.to_thread(_run_node_sync, state, node_name, label, fn)
                    except Exception as e:
                        logger.error(f"Node {node_name} failed during correction: {e}", exc_info=True)
                        yield _sse("error", {"error": f"{label}失败: {e}"})
                        return

                yield _sse("node", {"node": "validate_evidence", "label": validate_label})
                try:
                    state = await asyncio.to_thread(_run_node_sync, state, "validate_evidence", validate_label, validate_evidence_node)
                except Exception as e:
                    logger.error(f"Node validate_evidence failed during correction: {e}", exc_info=True)
                    yield _sse("error", {"error": f"{validate_label}失败: {e}"})
                    return

            trace_data = state.retrieval_trace.model_dump() if state.retrieval_trace else None
            mode = "mixed" if state.uses_structured_metadata else "evidence_lookup"
            yield _sse("trace", {"trace": trace_data, "mode": mode, "phase": "evidence_ready"})

            answer_text = ""
            messages, early_answer = build_answer_messages(state)

            if early_answer is not None:
                answer_text = early_answer
                yield _sse("node", {"node": "generate_answer", "label": "生成答案"})
                yield _sse("answer", {"token": answer_text})
            elif state.evidence_sufficiency.get("blocked_by_review"):
                answer_text = state.answer or "当前召回到的候选证据尚未审核通过，严格审核模式下不能用于回答。"
                yield _sse("node", {"node": "generate_answer", "label": "生成答案"})
                yield _sse("answer", {"token": answer_text})
            elif state.intent and getattr(state.intent, "safety_sensitive", False) and not state.evidence_sufficiency.get("sufficient", False):
                answer_text = state.answer or "⚠️ 安全相关问题需要更充分的证据支持，请参考官方维修手册或咨询工程师。"
                yield _sse("node", {"node": "generate_answer", "label": "生成答案"})
                yield _sse("answer", {"token": answer_text})
            else:
                yield _sse("node", {"node": "generate_answer", "label": "生成答案"})
                collected: list[str] = []
                try:
                    stream = llm_client.generate_stream(
                        messages=messages,
                        temperature=0.2,
                        max_tokens=2500,
                    )
                    async for chunk in stream:
                        collected.append(chunk)
                        yield _sse("answer", {"token": chunk})
                    answer_text = "".join(collected)
                except Exception as e:
                    logger.error(f"Stream LLM failed: {e}", exc_info=True)
                    answer_text = _fallback_answer(state)
                    yield _sse("answer", {"token": answer_text})

                answer_text = _finalize_answer_text(answer_text)

            state.answer = answer_text

            def _to_dict(x: Any) -> Any:
                if hasattr(x, "model_dump"):
                    return x.model_dump()
                return x

            citations_data = [_to_dict(c) for c in (state.citations or [])]
            trace_data = state.retrieval_trace.model_dump() if state.retrieval_trace else None
            sql_result = None
            if state.sql_result:
                sql_result = {
                    "sql": state.sql_result.get("sql", ""),
                    "columns": state.sql_result.get("columns", []),
                    "rows": state.sql_result.get("rows", []),
                    "row_count": state.sql_result.get("row_count", 0),
                }

            yield _sse(
                "done",
                {
                    "citations": citations_data,
                    "trace": trace_data,
                    "mode": mode,
                    "sql_result": sql_result,
                    "answer": answer_text,
                    "missing_requirements": state.missing_requirements,
                    "applicability_conflict": state.applicability_conflict,
                    "applicability_summary": state.applicability_summary,
                    "iterations": state.iteration,
                },
            )

            save_query_trace_fire_and_forget(state)

        except Exception as e:
            logger.error(f"Stream query failed: {e}", exc_info=True)
            yield _sse("error", {"error": str(e)})
        finally:
            current_trace_id.reset(tok)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/intent")
async def classify_query_intent(request: QueryRequest):
    """仅做意图分类（轻量）。"""
    from app.retrieval.intent import classify_intent, get_intent_config
    intent = classify_intent(request.question)
    config = get_intent_config(intent)
    return {
        "question": request.question,
        "intent": intent.model_dump(),
        "config": config,
    }


@router.post("/rewrite")
async def rewrite_query(request: QueryRequest):
    """LLM 改写查询。"""
    from app.retrieval.query_features import hybrid_rewrite_query
    try:
        variants = await hybrid_rewrite_query(request.question)
    except Exception as e:
        logger.warning(f"LLM rewrite failed: {e}")
        from app.retrieval.query_features import generate_query_variants
        variants = generate_query_variants(request.question)

    return {
        "question": request.question,
        "variants": variants,
    }
