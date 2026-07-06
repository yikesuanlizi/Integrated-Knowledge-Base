"""Compatibility wrapper for the single Agent graph query path."""
from __future__ import annotations

import asyncio
from typing import Any

from app.agent.graph import run_agent_sync
from app.agent.state import AgentState
from app.core.log import logger
from app.models.schemas import QueryResponse
from app.services.monitor_service import save_query_trace_fire_and_forget


async def run_unified_query(question: str, top_k: int = 8) -> QueryResponse:
    """Execute the single RAG/Wiki Agent graph and adapt its state to the API response."""
    state = await asyncio.to_thread(run_agent_sync, question, top_k)
    # 异步持久化监控数据（fire-and-forget）
    save_query_trace_fire_and_forget(state)
    mode = "mixed" if state.uses_structured_metadata else "evidence_lookup"
    return QueryResponse(
        question=question,
        answer=state.answer,
        needs_clarification=state.needs_clarification,
        clarification_questions=state.clarification_questions,
        citations=state.citations,
        mode=mode,
        retrieval_trace=state.retrieval_trace,
        sql_result=_sql_payload(state),
    )


def _sql_payload(state: AgentState) -> dict[str, Any] | None:
    if not state.sql_result:
        return None
    return {
        "sql": state.sql_result.get("sql", ""),
        "columns": state.sql_result.get("columns", []),
        "rows": state.sql_result.get("rows", []),
        "row_count": state.sql_result.get("row_count", 0),
    }
