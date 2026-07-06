"""Helpers for query-time retrieval diagnostics.

The trace is an online observation artifact: it explains the retrieval
process for one query. Real recall metrics are computed separately from a
golden set in eval APIs.
"""
from __future__ import annotations

import contextvars
import time
import uuid
from typing import Any

from app.agent.state import AgentState

# contextvar 用于在 LLM 调用层获取当前 trace_id
current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_trace_id", default="")


CHANNEL_LABELS = {
    "wiki": "Wiki 卡片",
    "chunks": "原文切块",
    "entities": "实体全文",
    "structured_metadata": "结构化元数据",
}


def add_stage(state: AgentState, name: str, label: str, **payload: Any) -> None:
    trace = getattr(state, "retrieval_trace", None)
    if not trace:
        return
    stages = list(trace.stages or [])
    stages.append({"name": name, "label": label, **payload})
    trace.stages = stages


def record_channel(
    state: AgentState,
    channel: str,
    results: list[dict],
    *,
    query: str | None = None,
    used: bool = True,
    error: str | None = None,
    decision: dict[str, Any] | None = None,
    limit: int = 8,
) -> None:
    trace = getattr(state, "retrieval_trace", None)
    if not trace:
        return
    channels = dict(trace.channels or {})
    channels[channel] = {
        "label": CHANNEL_LABELS.get(channel, channel),
        "query": query or state.question,
        "used": used,
        "hit_count": len(results or []),
        "top_candidates": [candidate_summary(item, channel) for item in (results or [])[:limit]],
        "error": error,
        "decision": decision,
    }
    trace.channels = channels


def update_candidate_selection(state: AgentState) -> None:
    trace = getattr(state, "retrieval_trace", None)
    if not trace:
        return
    selected_ids = {item.get("id") for item in trace.selected_evidence or []}
    channels = {}
    for key, channel in (trace.channels or {}).items():
        updated = dict(channel)
        candidates = []
        for candidate in channel.get("top_candidates", []):
            item = dict(candidate)
            item["selected"] = item.get("id") in selected_ids
            candidates.append(item)
        updated["top_candidates"] = candidates
        channels[key] = updated
    trace.channels = channels


def candidate_summary(item: dict, fallback_channel: str = "") -> dict:
    source_type = item.get("source_type") or _source_type_from_channel(fallback_channel)
    candidate_id = _candidate_id(item, source_type)
    title = (
        item.get("title")
        or item.get("name")
        or item.get("value")
        or item.get("source_file")
        or item.get("source_ref")
        or candidate_id
    )
    content = item.get("content") or item.get("text") or item.get("description") or ""
    score = _score(item)
    return {
        "id": candidate_id,
        "source_type": source_type,
        "title": str(title or ""),
        "score": score,
        "status": item.get("status", "approved"),
        "freshness": item.get("freshness", "current"),
        "source": item.get("source_file") or item.get("source_ref") or item.get("table_name") or "",
        "selected": bool(item.get("selected", False)),
        "snippet": str(content)[:180],
    }


def selected_evidence_from_pack(evidence_pack: dict) -> list[dict]:
    selected: list[dict] = []
    for item in evidence_pack.get("evidence_items", []):
        source_type = item.get("type", "")
        selected.append(candidate_summary({**item, "source_type": source_type}, source_type))
    return selected


# ─── 节点执行追踪 ───────────────────────────────────────────

_node_timings: dict[str, dict] = {}


def start_node(state: AgentState, node_name: str, input_summary: str = "") -> None:
    """节点入口埋点：记录开始时间和输入摘要。"""
    trace_id = getattr(state, "trace_id", "") or ""
    _node_timings[node_name] = {
        "trace_id": trace_id,
        "node_name": node_name,
        "input_summary": str(input_summary)[:500],
        "started_at": time.perf_counter(),
        "started_ts": time.time(),
    }


def finish_node(state: AgentState, node_name: str, output_summary: str = "", status: str = "success", error: str = "") -> None:
    """节点出口埋点：记录耗时和输出摘要，收集到 state._node_executions 供持久化。"""
    timing = _node_timings.pop(node_name, None)
    if not timing:
        return
    duration_ms = int((time.perf_counter() - timing["started_at"]) * 1000)

    node_execs = getattr(state, "_node_executions", None)
    if node_execs is None:
        node_execs = []
        setattr(state, "_node_executions", node_execs)
    node_execs.append({
        "node_name": node_name,
        "input_summary": timing["input_summary"],
        "output_summary": str(output_summary)[:500],
        "duration_ms": duration_ms,
        "status": status,
        "error": error,
    })


# ─── LLM 调用记录 ───────────────────────────────────────────

_llm_calls_buffer: dict[str, list[dict]] = {}


def record_llm_call(
    trace_id: str,
    scene: str,
    system_prompt: str,
    user_prompt: str,
    completion: str,
    model_name: str,
    duration_ms: int,
    status: str = "success",
    error: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> str:
    """记录一次 LLM 调用，返回 call_id。"""
    call_id = str(uuid.uuid4())
    record = {
        "call_id": call_id,
        "trace_id": trace_id or "",
        "scene": scene,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "completion": completion,
        "model_name": model_name,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "status": status,
        "error": error,
    }
    buffer = _llm_calls_buffer.setdefault(trace_id or "_no_trace", [])
    buffer.append(record)
    return call_id


def get_llm_calls(trace_id: str) -> list[dict]:
    """获取某次查询的所有 LLM 调用记录。"""
    return list(_llm_calls_buffer.get(trace_id, []))


def clear_llm_calls(trace_id: str) -> None:
    """清理某次查询的 LLM 调用缓冲。"""
    _llm_calls_buffer.pop(trace_id, None)


_NODE_LABELS = {
    "classify_intent": "意图分类",
    "extract_query": "查询改写",
    "recall_wiki": "Wiki 召回",
    "recall_chunks": "原文召回",
    "recall_entities": "实体召回",
    "recall_structured_metadata": "结构化召回",
    "merge_results": "合并去重",
    "expand_graph": "图扩展",
    "rerank": "混合重排",
    "build_evidence": "证据组装",
    "generate_answer": "答案生成",
    "validate_evidence": "证据校验",
    "correct_answer": "答案修正",
}


def _candidate_id(item: dict, source_type: str) -> str:
    for key in ("chunk_id", "card_id", "entity_id", "id"):
        if item.get(key):
            return f"{source_type}:{item[key]}"
    if source_type == "structured_metadata":
        parts = [item.get("kind"), item.get("name"), item.get("table_name"), item.get("column_name")]
        return "structured_metadata:" + ":".join(str(part) for part in parts if part)
    content = item.get("content") or item.get("text") or item.get("value") or item.get("description") or ""
    return f"{source_type}:fallback:{str(content)[:64]}"


def _score(item: dict) -> float:
    for key in ("final_score", "combined_score", "merge_score", "score", "bm25_score"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return round(float(value), 6)
    return 0.0


def _source_type_from_channel(channel: str) -> str:
    if channel == "wiki":
        return "wiki_card"
    if channel == "chunks":
        return "chunk"
    if channel == "entities":
        return "entity"
    return channel or "unknown"
