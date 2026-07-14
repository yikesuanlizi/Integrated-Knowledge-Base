"""监控服务层：异步持久化查询链路、LLM 调用、节点执行记录。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy import select, func, desc
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.core.log import logger
from app.models.monitoring import LLMCall, NodeExecution, QueryTrace
from app.agent.trace import clear_llm_calls, get_llm_calls


async def save_query_trace(state) -> None:
    """查询完成后异步持久化整条链路（fire-and-forget）。"""
    trace_id = getattr(state, "trace_id", "") or ""
    if not trace_id:
        return

    trace = getattr(state, "retrieval_trace", None)
    node_execs = getattr(state, "_node_executions", []) or []
    llm_calls = get_llm_calls(trace_id)

    # 序列化 trace
    stages_json = []
    channels_json = {}
    selected_evidence_json = []
    evidence_sufficiency = {}
    intent_str = ""
    if trace:
        stages_json = list(trace.stages or [])
        channels_json = dict(trace.channels or {})
        selected_evidence_json = list(trace.selected_evidence or [])
        evidence_sufficiency = dict(trace.evidence_sufficiency or {})
        if trace.intent:
            intent_str = str(getattr(trace.intent, "route", "")) or ""

    answer_summary = str(getattr(state, "answer", ""))[:500]
    node_count = len(node_execs)
    llm_call_count = len(llm_calls)
    status = "success" if not getattr(state, "needs_clarification", False) else "needs_clarification"

    try:
        async with AsyncSessionLocal() as session:
            # upsert query_traces
            stmt = pg_insert(QueryTrace).values(
                trace_id=trace_id,
                question=state.question,
                answer_summary=answer_summary,
                node_count=node_count,
                llm_call_count=llm_call_count,
                status=status,
                intent=intent_str,
                stages_json=stages_json,
                channels_json=channels_json,
                selected_evidence_json=selected_evidence_json,
                evidence_sufficiency=evidence_sufficiency,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["trace_id"],
                set_={
                    "answer_summary": stmt.excluded.answer_summary,
                    "node_count": stmt.excluded.node_count,
                    "llm_call_count": stmt.excluded.llm_call_count,
                    "status": stmt.excluded.status,
                    "stages_json": stmt.excluded.stages_json,
                    "channels_json": stmt.excluded.channels_json,
                    "selected_evidence_json": stmt.excluded.selected_evidence_json,
                    "evidence_sufficiency": stmt.excluded.evidence_sufficiency,
                },
            )
            await session.execute(stmt)

            # batch insert node_executions
            if node_execs:
                for ne in node_execs:
                    session.add(NodeExecution(
                        trace_id=trace_id,
                        node_name=ne["node_name"],
                        input_summary=ne.get("input_summary", ""),
                        output_summary=ne.get("output_summary", ""),
                        duration_ms=ne.get("duration_ms", 0),
                        status=ne.get("status", "success"),
                        error=ne.get("error", ""),
                    ))

            # batch insert llm_calls
            if llm_calls:
                for lc in llm_calls:
                    session.add(LLMCall(
                        call_id=lc["call_id"],
                        trace_id=trace_id,
                        scene=lc.get("scene", "unknown"),
                        system_prompt=lc.get("system_prompt", ""),
                        user_prompt=lc.get("user_prompt", ""),
                        completion=lc.get("completion", ""),
                        model_name=lc.get("model_name", ""),
                        duration_ms=lc.get("duration_ms", 0),
                        input_tokens=lc.get("input_tokens", 0),
                        output_tokens=lc.get("output_tokens", 0),
                        status=lc.get("status", "success"),
                        error=lc.get("error", ""),
                    ))

            await session.commit()
    except Exception as e:
        logger.error(f"save_query_trace failed: {e}", exc_info=True)
    finally:
        clear_llm_calls(trace_id)


def save_query_trace_fire_and_forget(state) -> None:
    """在当前运行的 asyncio 事件循环中调度异步持久化任务。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            logger.warning("save_query_trace_fire_and_forget: no event loop available, skipping persistence")
            return
    loop.create_task(save_query_trace(state))


async def list_queries(page: int = 1, page_size: int = 20) -> dict:
    """分页查询历史。"""
    async with AsyncSessionLocal() as session:
        total = (await session.execute(select(func.count(QueryTrace.trace_id)))).scalar() or 0
        offset = (page - 1) * page_size
        result = await session.execute(
            select(QueryTrace)
            .order_by(desc(QueryTrace.created_at))
            .offset(offset)
            .limit(page_size)
        )
        rows = result.scalars().all()

        trace_ids = [r.trace_id for r in rows]
        duration_map: dict[str, int] = {}
        if trace_ids:
            from sqlalchemy import and_
            dur_result = await session.execute(
                select(
                    NodeExecution.trace_id,
                    func.sum(NodeExecution.duration_ms).label("total_ms"),
                )
                .where(NodeExecution.trace_id.in_(trace_ids))
                .group_by(NodeExecution.trace_id)
            )
            for tid, total_ms in dur_result.all():
                duration_map[tid] = int(total_ms or 0)

        return {
            "items": [
                {
                    "trace_id": r.trace_id,
                    "question": r.question[:100] if r.question else "",
                    "answer_summary": (r.answer_summary or "")[:100],
                    "duration_ms": duration_map.get(r.trace_id, 0),
                    "node_count": r.node_count,
                    "llm_call_count": r.llm_call_count,
                    "status": r.status,
                    "intent": r.intent,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


def _calc_duration_ms(trace_row) -> int:
    """从 stages_json 中累加节点耗时。"""
    if not trace_row.stages_json:
        return 0
    total = 0
    for s in trace_row.stages_json:
        if isinstance(s, dict):
            total += s.get("duration_ms", 0) or 0
    return total


async def get_query_detail(trace_id: str) -> dict | None:
    """单次查询详情：trace + node 执行明细 + LLM 调用列表。"""
    async with AsyncSessionLocal() as session:
        trace_row = (
            await session.execute(select(QueryTrace).where(QueryTrace.trace_id == trace_id))
        ).scalar_one_or_none()
        if not trace_row:
            return None

        node_rows = (
            await session.execute(
                select(NodeExecution)
                .where(NodeExecution.trace_id == trace_id)
                .order_by(NodeExecution.id)
            )
        ).scalars().all()

        llm_rows = (
            await session.execute(
                select(LLMCall)
                .where(LLMCall.trace_id == trace_id)
                .order_by(LLMCall.created_at)
            )
        ).scalars().all()

        return {
            "trace_id": trace_row.trace_id,
            "question": trace_row.question,
            "answer_summary": trace_row.answer_summary,
            "status": trace_row.status,
            "intent": trace_row.intent,
            "stages": trace_row.stages_json or [],
            "channels": trace_row.channels_json or {},
            "selected_evidence": trace_row.selected_evidence_json or [],
            "evidence_sufficiency": trace_row.evidence_sufficiency or {},
            "node_executions": [
                {
                    "node_name": n.node_name,
                    "input_summary": n.input_summary,
                    "output_summary": n.output_summary,
                    "duration_ms": n.duration_ms,
                    "status": n.status,
                    "error": n.error,
                }
                for n in node_rows
            ],
            "llm_calls": [
                {
                    "call_id": lc.call_id,
                    "scene": lc.scene,
                    "model_name": lc.model_name,
                    "duration_ms": lc.duration_ms,
                    "input_tokens": lc.input_tokens,
                    "output_tokens": lc.output_tokens,
                    "status": lc.status,
                    "created_at": lc.created_at.isoformat() if lc.created_at else None,
                }
                for lc in llm_rows
            ],
            "created_at": trace_row.created_at.isoformat() if trace_row.created_at else None,
        }


async def list_llm_calls(page: int = 1, page_size: int = 20, scene: str | None = None) -> dict:
    """LLM 调用列表，支持 scene 过滤。"""
    async with AsyncSessionLocal() as session:
        base = select(LLMCall)
        count_q = select(func.count(LLMCall.call_id))
        if scene:
            base = base.where(LLMCall.scene == scene)
            count_q = count_q.where(LLMCall.scene == scene)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        result = await session.execute(
            base.order_by(desc(LLMCall.created_at)).offset(offset).limit(page_size)
        )
        rows = result.scalars().all()
        return {
            "items": [
                {
                    "call_id": r.call_id,
                    "trace_id": r.trace_id,
                    "scene": r.scene,
                    "model_name": r.model_name,
                    "duration_ms": r.duration_ms,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


async def get_llm_call_detail(call_id: str) -> dict | None:
    """单次 LLM 调用详情：完整 prompt + completion。"""
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(LLMCall).where(LLMCall.call_id == call_id))
        ).scalar_one_or_none()
        if not row:
            return None
        return {
            "call_id": row.call_id,
            "trace_id": row.trace_id,
            "scene": row.scene,
            "system_prompt": row.system_prompt,
            "user_prompt": row.user_prompt,
            "completion": row.completion,
            "model_name": row.model_name,
            "duration_ms": row.duration_ms,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "status": row.status,
            "error": row.error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


async def get_stats(hours: int = 24) -> dict:
    """聚合统计。"""
    from datetime import timedelta
    from sqlalchemy import and_

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    async with AsyncSessionLocal() as session:
        # 查询统计
        total_queries = (
            await session.execute(
                select(func.count(QueryTrace.trace_id)).where(QueryTrace.created_at >= cutoff)
            )
        ).scalar() or 0

        error_queries = (
            await session.execute(
                select(func.count(QueryTrace.trace_id)).where(
                    and_(QueryTrace.created_at >= cutoff, QueryTrace.status != "success")
                )
            )
        ).scalar() or 0

        # LLM 调用统计
        total_llm_calls = (
            await session.execute(
                select(func.count(LLMCall.call_id)).where(LLMCall.created_at >= cutoff)
            )
        ).scalar() or 0

        total_input_tokens = (
            await session.execute(
                select(func.sum(LLMCall.input_tokens)).where(LLMCall.created_at >= cutoff)
            )
        ).scalar() or 0

        total_output_tokens = (
            await session.execute(
                select(func.sum(LLMCall.output_tokens)).where(LLMCall.created_at >= cutoff)
            )
        ).scalar() or 0

        # 节点平均耗时
        node_stats = (
            await session.execute(
                select(
                    NodeExecution.node_name,
                    func.avg(NodeExecution.duration_ms).label("avg_ms"),
                    func.count(NodeExecution.id).label("count"),
                )
                .where(NodeExecution.started_at >= cutoff)
                .group_by(NodeExecution.node_name)
                .order_by(desc("avg_ms"))
            )
        ).all()

        # 平均查询耗时（从 node_executions 累加）
        avg_query_ms = 0
        if total_queries > 0:
            total_duration = (
                await session.execute(
                    select(func.sum(NodeExecution.duration_ms))
                    .where(NodeExecution.started_at >= cutoff)
                )
            ).scalar() or 0
            avg_query_ms = int(total_duration / max(total_queries, 1))

        return {
            "hours": hours,
            "total_queries": total_queries,
            "error_queries": error_queries,
            "error_rate": round(error_queries / max(total_queries, 1) * 100, 1),
            "avg_query_ms": avg_query_ms,
            "total_llm_calls": total_llm_calls,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "node_stats": [
                {"node_name": row[0], "avg_ms": int(row[1] or 0), "count": row[2]}
                for row in node_stats
            ],
        }
