"""context_builder - 会话上下文构造层。

历史只用于指代消解和查询重写，不作为事实证据进入答案生成。
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.agent.state import AgentState
from app.agent.trace import add_stage
from app.clients.llm_client import llm_client
from app.core.log import logger


REFERENCE_PATTERNS = ("它", "这个", "那个", "上述", "刚才", "前面", "其", "该")


def _normalize_history(history: list[dict[str, Any]] | None, limit: int = 6) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in (history or [])[-limit:]:
        role = str(item.get("role", "") or "").strip().lower()
        content = str(item.get("content", "") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content[:800]})
    return normalized


def _needs_history_resolution(question: str, history: list[dict[str, str]]) -> bool:
    if not history:
        return False
    return any(pattern in question for pattern in REFERENCE_PATTERNS)


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _build_prompt(state: AgentState, history: list[dict[str, str]]) -> tuple[str, str]:
    system = """你是工业维修知识库的 Context Builder。
你的任务不是回答问题，而是根据最近对话历史对当前问题做指代消解和查询重写。

硬性规则：
1. 历史对话只能用于理解"它/这个/上述/刚才"等指代。
2. 历史对话不能作为事实证据。
3. 改写后的问题必须仍然要求系统重新检索维修资料。
4. 不要编造维修步骤、参数、章节号或事实。
5. 返回严格 JSON，不要输出解释性正文。"""

    user = f"""当前用户问题：
{state.raw_question or state.question}

最近对话历史：
{json.dumps(history, ensure_ascii=False, indent=2)}

请返回 JSON：
{{
  "resolved_question": "消解指代后的完整问题",
  "reference_entities": ["从历史中解析出的实体"],
  "topic": "当前会话主题",
  "used_history": true,
  "rewrite_reason": "为什么这样改写"
}}"""
    return system, user


def _fallback_context(state: AgentState, history: list[dict[str, str]], reason: str) -> dict[str, Any]:
    question = state.raw_question or state.question
    return {
        "resolved_question": question,
        "reference_entities": [],
        "topic": "",
        "used_history": False,
        "rewrite_reason": reason,
        "fallback_used": True,
    }


def _sanitize_context(raw: dict[str, Any] | None, state: AgentState, history: list[dict[str, str]]) -> dict[str, Any]:
    if not raw or not isinstance(raw, dict):
        return _fallback_context(state, history, "LLM returned invalid context JSON")

    resolved = raw.get("resolved_question")
    if not isinstance(resolved, str) or not resolved.strip():
        return _fallback_context(state, history, "resolved_question is empty")

    entities = raw.get("reference_entities")
    if not isinstance(entities, list):
        entities = []
    safe_entities = [str(entity).strip() for entity in entities if str(entity).strip()][:8]

    return {
        "resolved_question": resolved.strip(),
        "reference_entities": safe_entities,
        "topic": str(raw.get("topic", "") or "").strip(),
        "used_history": bool(raw.get("used_history", bool(history))),
        "rewrite_reason": str(raw.get("rewrite_reason", "") or "").strip(),
        "fallback_used": False,
    }


def context_builder_node(state: AgentState) -> AgentState:
    if not state.raw_question:
        state.raw_question = state.question
    if not state.original_question:
        state.original_question = state.raw_question

    history = _normalize_history(state.history)
    state.history = history

    try:
        if _needs_history_resolution(state.raw_question, history):
            system, user = _build_prompt(state, history)
            response = llm_client.generate_sync(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
                max_tokens=600,
                scene="context_builder",
            )
            context = _sanitize_context(_extract_json(response), state, history)
        else:
            context = _fallback_context(state, history, "No reference resolution needed")
            context["fallback_used"] = False
    except Exception as exc:
        logger.warning(f"Context builder failed: {exc}")
        context = _fallback_context(state, history, str(exc)[:200])

    state.resolved_question = context["resolved_question"]
    state.reference_entities = context["reference_entities"]
    state.question = state.resolved_question
    state.conversation_context = {
        "conversation_id": state.conversation_id,
        "raw_question": state.raw_question,
        "resolved_question": state.resolved_question,
        "reference_entities": state.reference_entities,
        "topic": context.get("topic", ""),
        "used_history": context.get("used_history", False),
        "rewrite_reason": context.get("rewrite_reason", ""),
        "fallback_used": context.get("fallback_used", False),
        "history_turn_count": len(history),
        "history_used_for": "query_rewrite_only",
        "history_as_evidence": False,
    }

    if state.retrieval_trace:
        state.retrieval_trace.conversation_context = dict(state.conversation_context)
        state.retrieval_trace.context_expanded = bool(context.get("used_history", False))
        grounding = state.retrieval_trace.grounding if state.retrieval_trace.grounding else {}
        grounding["context_builder"] = dict(state.conversation_context)
        state.retrieval_trace.grounding = grounding
        add_stage(
            state,
            "context_builder",
            "上下文构造",
            used_history=state.conversation_context["used_history"],
            resolved_question=state.resolved_question,
            history_as_evidence=False,
        )

    return state
