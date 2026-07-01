"""Recall structured knowledge-base metadata as one evidence lane."""
from __future__ import annotations

import asyncio
from typing import Any

from app.agent.state import AgentState
from app.compiler.llm_utils import call_llm_json
from app.core.log import logger
from app.nl2sql.service import NL2SQLService


STRUCTURED_METADATA_TERMS = {
    "字段",
    "指标",
    "口径",
    "值域",
    "审核",
    "状态",
    "卡片",
    "Wiki",
    "wiki",
    "结构化",
    "元数据",
    "引用覆盖率",
    "严格审核",
    "证据完整性",
}

PLAIN_MANUAL_TERMS = {
    "拆卸",
    "安装",
    "步骤",
    "功能",
    "故障处置",
    "安全警告",
    "注意事项",
    "工具",
    "耗材",
}

STRUCTURED_DECISION_SYSTEM = """你是 Agentic Knowledge OS 的图内召回决策器。
你只判断当前问题是否需要查询 PostgreSQL 中的知识库结构化元数据。
结构化元数据包括：字段协议、指标口径、值域、审核状态、引用覆盖、知识质量、卡片类型、chunk/card/entity 的结构说明。
它不是业务事实数据库，不能用于独立回答事实问题。

只输出 JSON：
{
  "use_structured_metadata": boolean,
  "reason": "一句话说明"
}
"""


def recall_structured_metadata_node(state: AgentState) -> AgentState:
    decision = _should_recall_structured_metadata(state.question)
    if not decision["use"]:
        state.structured_results = []
        state.uses_structured_metadata = False
        state.metadata_sql_trace = {"decision": decision}
        _record_structured_grounding(state, decision, row_count=0)
        return state

    try:
        limit = min(max(int(state.query_features.get("top_k", 8)) * 4, 12), 50)
        result = _run_query(state.question, limit=limit)
    except Exception as exc:
        logger.debug(f"Structured metadata recall skipped: {exc}")
        state.structured_results = []
        state.uses_structured_metadata = False
        state.metadata_sql_trace = {"error": str(exc), "decision": decision}
        _record_structured_grounding(state, decision, row_count=0, error=str(exc))
        return state

    uses_structured_metadata = result.row_count > 0
    sql_result = {
        "sql": result.sql,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
    }
    metadata_sql_trace = {**(result.trace or {}), "decision": decision}
    structured_results = _rows_to_evidence(result.rows, result.sql)
    state.uses_structured_metadata = uses_structured_metadata
    state.sql_result = sql_result
    state.metadata_sql_trace = metadata_sql_trace
    state.structured_results = structured_results
    _record_structured_grounding(state, decision, row_count=result.row_count)
    return state


def _record_structured_grounding(
    state: AgentState,
    decision: dict[str, Any],
    *,
    row_count: int,
    error: str | None = None,
) -> None:
    if state.retrieval_trace is None:
        return
    grounding = state.retrieval_trace.grounding or {}
    payload: dict[str, Any] = {
        "used": bool(state.uses_structured_metadata),
        "decision": decision,
        "row_count": row_count,
    }
    if error:
        payload["error"] = error
    grounding["structured_metadata"] = payload
    state.retrieval_trace.grounding = grounding


def _should_recall_structured_metadata(question: str) -> dict[str, Any]:
    metadata_hits = [term for term in STRUCTURED_METADATA_TERMS if term in question]
    if metadata_hits:
        return {
            "use": True,
            "source": "rule",
            "reason": f"命中结构化元数据强信号：{', '.join(metadata_hits[:5])}",
        }

    manual_hits = [term for term in PLAIN_MANUAL_TERMS if term in question]
    if manual_hits and not _looks_like_system_boundary_question(question):
        return {
            "use": False,
            "source": "rule",
            "reason": f"明确普通手册/维修知识问题：{', '.join(manual_hits[:5])}",
        }

    return _llm_structured_metadata_decision(question)


def _looks_like_system_boundary_question(question: str) -> bool:
    boundary_terms = ["怎么判断", "如何判断", "能回答", "不能回答", "可用", "不可用", "证据", "依据", "来源"]
    return any(term in question for term in boundary_terms)


def _llm_structured_metadata_decision(question: str) -> dict[str, Any]:
    try:
        result = _run_llm_decision(question)
        if isinstance(result, dict):
            use = bool(result.get("use_structured_metadata", False))
            return {
                "use": use,
                "source": "llm",
                "reason": str(result.get("reason", "")),
            }
    except Exception as exc:
        logger.debug(f"Structured metadata LLM decision skipped: {exc}")
    return {"use": False, "source": "llm_error", "reason": "LLM 判断不可用，默认不启用结构化元数据召回。"}


def _run_llm_decision(question: str):
    try:
        return asyncio.run(
            call_llm_json(
                STRUCTURED_DECISION_SYSTEM,
                f"用户问题：{question}",
                temperature=0.0,
                max_tokens=300,
                max_retries=1,
            )
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                call_llm_json(
                    STRUCTURED_DECISION_SYSTEM,
                    f"用户问题：{question}",
                    temperature=0.0,
                    max_tokens=300,
                    max_retries=1,
                )
            )
        finally:
            loop.close()


def _run_query(question: str, limit: int):
    service = NL2SQLService()
    try:
        return asyncio.run(service.query(question, limit=limit))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(service.query(question, limit=limit))
        finally:
            loop.close()


def _rows_to_evidence(rows: list[dict[str, Any]], sql: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        kind = str(row.get("kind") or "metadata")
        name = str(row.get("name") or "")
        table_name = str(row.get("table_name") or "")
        column_name = str(row.get("column_name") or "")
        description = str(row.get("description") or "")
        target = ".".join(part for part in [table_name, column_name] if part)
        content = "；".join(
            part
            for part in [
                f"类型：{kind}",
                f"名称：{name}" if name else "",
                f"字段：{target}" if target else "",
                f"说明：{description}" if description else "",
            ]
            if part
        )
        evidence.append(
            {
                "id": f"structured_metadata:{kind}:{name or index}",
                "source_type": "structured_metadata",
                "evidence_type": "structured_metadata",
                "kind": kind,
                "name": name,
                "table_name": table_name,
                "column_name": column_name,
                "description": description,
                "content": content,
                "sql": sql,
                "score": float(row.get("score", 0.65) or 0.65),
                "status": "approved",
                "freshness": "current",
            }
        )
    return evidence
