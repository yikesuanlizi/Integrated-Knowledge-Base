"""3. recall_dispatch - 召回调度节点：按意图路由选择通道，并行/串行执行，统一汇合结果。"""
from __future__ import annotations

import copy
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

from app.agent.nodes.recall_chunks import recall_chunks_node
from app.agent.nodes.recall_entities import recall_entities_node
from app.agent.nodes.recall_structured_metadata import recall_structured_metadata_node
from app.agent.nodes.recall_wiki import recall_wiki_node
from app.agent.state import AgentState
from app.agent.trace import add_stage, current_trace_id
from app.conf.app_config import config
from app.core.log import logger


ROUTE_CHANNELS: dict[str, list[str]] = {
    "concept": ["wiki"],
    "fact": ["chunks", "entities", "structured_metadata"],
    "complex": ["wiki", "chunks", "entities", "structured_metadata"],
}

ALLOWED_CHANNELS = {"wiki", "chunks", "entities", "structured_metadata"}

CHANNEL_FALLBACK: dict[str, dict[str, bool]] = {
    "wiki": {"concept": True, "fact": False, "complex": False},
}


def normalize_planned_channels(planned_channels: list[str] | None) -> list[str]:
    if not planned_channels or not isinstance(planned_channels, list):
        return []
    valid = []
    seen = set()
    for ch in planned_channels:
        if isinstance(ch, str):
            ch_lower = ch.strip().lower()
            if ch_lower in ALLOWED_CHANNELS and ch_lower not in seen:
                valid.append(ch_lower)
                seen.add(ch_lower)
    return valid


@dataclass
class ChannelResult:
    name: str
    status: str = "success"
    latency_ms: int = 0
    hit_count: int = 0
    error: str = ""
    reason: str = ""
    output: dict | AgentState | None = None


def _clone_state(state: AgentState) -> AgentState:
    cloned = AgentState(
        question=state.question,
        original_question=state.original_question,
        raw_question=state.raw_question,
        conversation_id=state.conversation_id,
        history=copy.deepcopy(state.history) if state.history else [],
        resolved_question=state.resolved_question,
        reference_entities=list(state.reference_entities),
        conversation_context=copy.deepcopy(state.conversation_context) if state.conversation_context else {},
        trace_id=state.trace_id,
        intent=state.intent,
        query_features=dict(state.query_features) if state.query_features else {},
        planner_route=state.planner_route,
        keywords=list(state.keywords),
        entities=copy.deepcopy(state.entities) if state.entities else {},
        applicability_filters=copy.deepcopy(state.applicability_filters) if state.applicability_filters else {},
        retrieval_plan=copy.deepcopy(state.retrieval_plan) if state.retrieval_plan else {},
        planner_feedback=copy.deepcopy(state.planner_feedback) if state.planner_feedback else {},
        iteration=state.iteration,
        max_iterations=state.max_iterations,
        answer_requirements=dict(state.answer_requirements) if state.answer_requirements else {},
        applicability_conflict=state.applicability_conflict,
        missing_requirements=list(state.missing_requirements),
    )
    return cloned


def _run_channel(name: str, state: AgentState, trace_id: str = "") -> ChannelResult:
    start = time.perf_counter()
    result = ChannelResult(name=name)
    token = None
    if trace_id:
        token = current_trace_id.set(trace_id)
    try:
        route = state.planner_route or "fact"
        if name == "wiki":
            allow_fb = CHANNEL_FALLBACK.get("wiki", {}).get(route, False)
            output = recall_wiki_node(state, allow_chunk_fallback=allow_fb)
        elif name == "chunks":
            output = recall_chunks_node(state)
        elif name == "entities":
            output = recall_entities_node(state)
        elif name == "structured_metadata":
            output = recall_structured_metadata_node(state)
        else:
            result.status = "skipped"
            result.reason = f"unknown channel: {name}"
            result.latency_ms = int((time.perf_counter() - start) * 1000)
            return result

        result.output = output
        result.latency_ms = int((time.perf_counter() - start) * 1000)

        if name == "structured_metadata":
            result.hit_count = len(getattr(output, "structured_results", []))
            if not getattr(output, "uses_structured_metadata", False) and result.hit_count == 0:
                decision = {}
                trace = getattr(output, "metadata_sql_trace", {}) or {}
                if isinstance(trace, dict):
                    decision = trace.get("decision") or {}
                result.reason = decision.get("reason", "")
                if decision.get("use") is False:
                    result.status = "skipped"
        elif name == "wiki":
            result.hit_count = len(output.get("wiki_results", []))
        elif name == "chunks":
            result.hit_count = len(output.get("chunk_results", []))
        elif name == "entities":
            result.hit_count = len(output.get("entity_results", []))

    except Exception as e:
        result.status = "failed"
        result.error = str(e)[:500]
        result.latency_ms = int((time.perf_counter() - start) * 1000)
        logger.warning(f"recall_dispatch channel {name} failed: {e}")
    finally:
        if token is not None:
            current_trace_id.reset(token)

    return result


def _extract_channel_metadata(name: str, output: dict | AgentState | None) -> dict:
    metadata: dict[str, Any] = {
        "filters_applied": False,
        "filter_conditions": None,
        "filter_fallback": False,
    }
    if output is None:
        return metadata
    if isinstance(output, AgentState):
        return metadata
    if not isinstance(output, dict):
        return metadata

    if name == "wiki":
        wiki_meta = output.get("wiki_metadata", {})
        if isinstance(wiki_meta, dict):
            metadata["filters_applied"] = wiki_meta.get("filters_applied", False)
            metadata["filter_conditions"] = wiki_meta.get("filter_conditions")
            metadata["filter_fallback"] = wiki_meta.get("wiki_filter_fallback", False) or wiki_meta.get("chunk_filter_fallback", False)
            metadata["wiki_filter_fallback"] = wiki_meta.get("wiki_filter_fallback", False)
            metadata["chunk_filter_fallback"] = wiki_meta.get("chunk_filter_fallback", False)
            metadata["total_matched"] = wiki_meta.get("total_matched", 0)
    elif name == "chunks":
        metadata["filters_applied"] = output.get("filters_applied", False)
        metadata["filter_conditions"] = output.get("filter_conditions")
        metadata["filter_fallback"] = output.get("filter_fallback", False)
    elif name == "entities":
        entity_meta = output.get("entity_metadata", {})
        if isinstance(entity_meta, dict):
            metadata["filters_applied"] = entity_meta.get("filters_applied", False)
            metadata["filter_conditions"] = entity_meta.get("filter_conditions")
            metadata["filter_fallback"] = entity_meta.get("filter_fallback", False)
            if entity_meta.get("error"):
                metadata["error"] = entity_meta["error"]

    return metadata


def _merge_results_into_state(state: AgentState, results: dict[str, ChannelResult]) -> dict[str, dict]:
    state.wiki_results = []
    state.chunk_results = []
    state.entity_results = []
    state.structured_results = []
    state.sql_result = {}
    state.metadata_sql_trace = {}
    state.uses_structured_metadata = False

    wiki_fallback_chunks: list[dict] = []
    channels_metadata: dict[str, dict] = {}

    wiki_res = results.get("wiki")
    if wiki_res and wiki_res.status == "success" and isinstance(wiki_res.output, dict):
        state.wiki_results = wiki_res.output.get("wiki_results", [])
        wiki_fallback_chunks = wiki_res.output.get("chunk_results", [])
        channels_metadata["wiki"] = _extract_channel_metadata("wiki", wiki_res.output)

    chunk_res = results.get("chunks")
    if chunk_res and chunk_res.status == "success" and isinstance(chunk_res.output, dict):
        state.chunk_results = chunk_res.output.get("chunk_results", [])
        channels_metadata["chunks"] = _extract_channel_metadata("chunks", chunk_res.output)

    entity_res = results.get("entities")
    if entity_res and entity_res.status == "success" and isinstance(entity_res.output, dict):
        state.entity_results = entity_res.output.get("entity_results", [])
        channels_metadata["entities"] = _extract_channel_metadata("entities", entity_res.output)

    structured_res = results.get("structured_metadata")
    if structured_res and structured_res.status in ("success", "skipped") and isinstance(structured_res.output, AgentState):
        s = structured_res.output
        state.structured_results = s.structured_results
        state.sql_result = s.sql_result
        state.metadata_sql_trace = s.metadata_sql_trace
        state.uses_structured_metadata = s.uses_structured_metadata
        channels_metadata["structured_metadata"] = _extract_channel_metadata("structured_metadata", s)
        if s.retrieval_trace and isinstance(s.retrieval_trace.grounding, dict):
            sm_grounding = s.retrieval_trace.grounding.get("structured_metadata")
            if sm_grounding and state.retrieval_trace:
                main_grounding = state.retrieval_trace.grounding if state.retrieval_trace.grounding else {}
                main_grounding["structured_metadata"] = sm_grounding
                state.retrieval_trace.grounding = main_grounding

    if wiki_fallback_chunks and not state.chunk_results:
        state.chunk_results = wiki_fallback_chunks

    return channels_metadata


def _record_dispatch_trace(
    state: AgentState,
    route: str,
    execution_mode: str,
    results: dict[str, ChannelResult],
    channels_metadata: dict[str, dict],
    fallback_used: bool = False,
) -> None:
    if state.retrieval_trace is None:
        return
    grounding = state.retrieval_trace.grounding if state.retrieval_trace.grounding else {}
    channels_info: dict[str, Any] = {}
    for name, ch in results.items():
        ch_meta = channels_metadata.get(name, {})
        channel_info: dict[str, Any] = {
            "enabled": True,
            "status": ch.status,
            "latency_ms": ch.latency_ms,
            "hit_count": ch.hit_count,
        }
        if ch.error:
            channel_info["error"] = ch.error
        if ch.reason:
            channel_info["reason"] = ch.reason
        if ch_meta:
            channel_info.update(ch_meta)
        channels_info[name] = channel_info

        stage_labels = {
            "wiki": "Wiki召回",
            "chunks": "原文召回",
            "entities": "实体召回",
            "structured_metadata": "结构化召回",
        }
        if name in stage_labels:
            stage_payload: dict[str, Any] = {
                "hit_count": ch.hit_count,
                "latency_ms": ch.latency_ms,
                "status": ch.status,
            }
            stage_payload.update(ch_meta)
            if ch.error:
                stage_payload["error"] = ch.error
            add_stage(
                state,
                f"recall_{name}" if name != "structured_metadata" else "recall_structured_metadata",
                stage_labels[name],
                **stage_payload,
            )

    plan = getattr(state, "retrieval_plan", {}) or {}

    grounding["recall_dispatch"] = {
        "route": route,
        "execution_mode": execution_mode,
        "channels": channels_info,
        "fallback_used": fallback_used,
        "planned_channels": plan.get("selected_channels", []),
        "planner_strategy": plan.get("strategy", ""),
        "responded_to_missing": plan.get("responded_to_missing", []),
        "responded_to_applicability_conflict": plan.get("responded_to_applicability_conflict", False),
        "filter_applicability": plan.get("filter_applicability", False),
        "missing_requirements": plan.get("missing_requirements", []),
    }
    state.retrieval_trace.grounding = grounding


def recall_dispatch_node(state: AgentState) -> AgentState:
    route = state.planner_route or "fact"
    plan = getattr(state, "retrieval_plan", {}) or {}
    planned_channels = plan.get("selected_channels")

    channels = normalize_planned_channels(planned_channels)

    fallback_used = False
    if not channels:
        channels = ROUTE_CHANNELS.get(route, ROUTE_CHANNELS["fact"])
        fallback_used = True
    else:
        fallback_used = bool(plan.get("fallback_used", False))

    execution_mode = getattr(config, "RECALL_EXECUTION_MODE", "parallel")
    timeouts = getattr(config, "RECALL_CHANNEL_TIMEOUTS", {})
    max_workers = getattr(config, "RECALL_PARALLEL_MAX_WORKERS", 4)
    trace_id = getattr(state, "trace_id", "") or ""

    results: dict[str, ChannelResult] = {}
    all_futures: dict[str, Any] = {}

    if execution_mode == "parallel" and len(channels) > 1:
        pool = ThreadPoolExecutor(max_workers=min(max_workers, len(channels)))
        try:
            for ch_name in channels:
                ch_state = _clone_state(state)
                timeout = float(timeouts.get(ch_name, 5.0))
                future = pool.submit(_run_channel, ch_name, ch_state, trace_id)
                all_futures[ch_name] = (future, timeout)

            for ch_name, (future, timeout) in all_futures.items():
                try:
                    results[ch_name] = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    future.cancel()
                    results[ch_name] = ChannelResult(
                        name=ch_name,
                        status="timeout",
                        error=f"exceeded {timeout}s timeout",
                        latency_ms=int(timeout * 1000),
                    )
                    logger.warning(f"recall_dispatch channel {ch_name} timed out after {timeout}s")
                except Exception as e:
                    future.cancel()
                    results[ch_name] = ChannelResult(
                        name=ch_name,
                        status="failed",
                        error=str(e)[:500],
                    )
                    logger.warning(f"recall_dispatch channel {ch_name} future error: {e}")
        finally:
            for future, _ in all_futures.values():
                future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
    else:
        for ch_name in channels:
            ch_state = _clone_state(state)
            timeout = float(timeouts.get(ch_name, 5.0))
            pool = ThreadPoolExecutor(max_workers=1)
            future = None
            try:
                future = pool.submit(_run_channel, ch_name, ch_state, trace_id)
                all_futures[ch_name] = (future, timeout)
                try:
                    results[ch_name] = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    results[ch_name] = ChannelResult(
                        name=ch_name,
                        status="timeout",
                        error=f"exceeded {timeout}s timeout",
                        latency_ms=int(timeout * 1000),
                    )
                    logger.warning(f"recall_dispatch channel {ch_name} timed out after {timeout}s")
                except Exception as e:
                    results[ch_name] = ChannelResult(
                        name=ch_name,
                        status="failed",
                        error=str(e)[:500],
                    )
                    logger.warning(f"recall_dispatch channel {ch_name} future error: {e}")
            finally:
                if future is not None:
                    future.cancel()
                pool.shutdown(wait=False, cancel_futures=True)

    channels_metadata = _merge_results_into_state(state, results)
    _record_dispatch_trace(state, route, execution_mode, results, channels_metadata, fallback_used)

    return state
