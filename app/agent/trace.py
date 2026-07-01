"""Helpers for query-time retrieval diagnostics.

The trace is an online observation artifact: it explains the retrieval
process for one query. Real recall metrics are computed separately from a
golden set in eval APIs.
"""
from __future__ import annotations

from typing import Any

from app.agent.state import AgentState


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
