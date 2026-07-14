"""10. generate_answer - 用 LLM 基于证据生成答案。"""
from __future__ import annotations

import re

from app.agent.state import AgentState
from app.clients.llm_client import llm_client
from app.compiler.prompts import get_prompt
from app.core.log import logger
from app.retrieval.context_build import build_context_for_llm


def build_answer_messages(state: AgentState) -> tuple[list[dict], str | None]:
    """构建 LLM 答案生成的 messages 列表。

    返回 (messages, early_exit_answer):
    - 如果证据不足或仅有结构化元数据，返回 (None, early_exit_answer)，early_exit_answer 是直接可用的提示文本
    - 如果证据充分，返回 ([system, user], None)，可直接传给 LLM
    """
    context = build_context_for_llm(state.evidence_pack, max_tokens=8000)
    answer_question = state.original_question or state.question

    if not context:
        state.needs_clarification = True
        state.clarification_questions = ["您能否提供更多上下文？"]
        return [], "抱歉，没有找到充分的信息来回答您的问题。"

    if _has_only_structured_metadata(state):
        state.needs_clarification = True
        state.clarification_questions = ["请先摄入并审核相关 Wiki/原文证据，或换一个能命中已审核知识的问题。"]
        return [], (
            "结构化元数据只说明知识库字段、指标口径、值域和审核状态，"
            "当前没有召回到已审核的 Wiki 卡片或原文切块证据，因此不能生成独立事实答案。"
        )

    system, user_tpl = get_prompt("answer_generation")
    system = (
        f"{system}\n\n"
        "结构化元数据只能作为知识库字段、指标口径、值域和审核状态的辅助说明；"
        "不得把结构化元数据当作独立事实来源。回答事实性内容必须依赖已审核 Wiki 卡片或原文切块。"
        "\n\n"
        "重要：对话历史conversation_context仅用于理解用户指代（如'它'、'这个'指代什么），不是事实来源。"
        "你的答案必须完全基于evidence_pack中的context内容，禁止使用conversation_context中的信息作为事实证据。"
    )

    if state.applicability_summary:
        system += f"\n\n{state.applicability_summary}。"
        system += "\n在答案末尾，你必须明确标注本回答的适用范围（机型、手册类型、ATA章节）。如果所有来源适用范围一致，则统一标注；"
        system += "如果存在不同来源适用范围不一致（如不同机型或版本），请在对应的内容后分别标注适用范围，不要混为一谈。"
    if state.applicability_conflict:
        system += "\n\n注意：证据中存在跨机型/版本冲突！请在答案中明确说明哪些内容适用于哪个机型/版本，存在哪些差异，不要强行合并回答。"

    context_with_applicability = context
    if state.applicability_summary:
        conflict_note = "存在跨机型/版本冲突，请明确标注差异" if state.applicability_conflict else "无冲突"
        context_with_applicability += (
            f"\n\n---\n适用范围信息：{state.applicability_summary}\n"
            f"冲突提示：{conflict_note}"
        )

    user_prompt = user_tpl.substitute(
        question=answer_question,
        context=context_with_applicability,
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ], None


def generate_answer_node(state: AgentState) -> AgentState:
    return _run_sync(state)


async def generate_answer_node_async(state: AgentState) -> AgentState:
    return await _run_async(state)


def _get_answer_question(state: AgentState) -> str:
    return state.original_question or state.question


def _run_sync(state: AgentState) -> AgentState:
    messages, early_answer = build_answer_messages(state)
    if early_answer is not None:
        state.answer = early_answer
        return state

    try:
        state.answer = llm_client.generate_sync(
            messages=messages,
            temperature=0.2,
            max_tokens=2500,
            scene="generate_answer",
        )
        if not isinstance(state.answer, str):
            state.answer = str(state.answer)
        state.answer = _finalize_answer_text(state.answer)
    except Exception as e:
        logger.error(f"generate_answer failed: {e}")
        state.answer = _fallback_answer(state)

    return state


def _run(state: AgentState) -> AgentState:
    return _run_sync(state)


async def _run_async(state: AgentState) -> AgentState:
    messages, early_answer = build_answer_messages(state)
    if early_answer is not None:
        state.answer = early_answer
        return state

    try:
        state.answer = await llm_client.generate(
            messages=messages,
            temperature=0.2,
            max_tokens=2500,
            scene="generate_answer",
        )
        if not isinstance(state.answer, str):
            state.answer = str(state.answer)
        state.answer = _finalize_answer_text(state.answer)
    except Exception as e:
        logger.error(f"generate_answer failed: {e}")
        state.answer = _fallback_answer(state)

    return state


def _has_only_structured_metadata(state: AgentState) -> bool:
    pack = state.evidence_pack or {}
    return (
        int(pack.get("structured_metadata_count", 0) or 0) > 0
        and int(pack.get("chunk_count", 0) or 0) == 0
        and int(pack.get("card_count", 0) or 0) == 0
    )


def _append_applicability_suffix(answer: str, state: AgentState) -> str:
    if state.applicability_summary:
        suffix = f"\n\n适用范围：{state.applicability_summary}"
        if state.applicability_conflict:
            suffix += "（注意：存在跨机型/版本冲突）"
        return answer + suffix
    return answer


def _fallback_answer(state: AgentState) -> str:
    items = state.evidence_pack.get("evidence_items", [])[:5]
    answer_question = _get_answer_question(state)
    if not items:
        return _finalize_answer_text(_append_applicability_suffix("抱歉，未能生成答案。", state))

    first = items[0]
    content = str(first.get("content", "") or "").strip()
    title = str(first.get("title", "") or "").strip()
    if first.get("type") == "wiki_card" and content:
        answer = _naturalize_markdown_answer(title or answer_question, content)
        return _finalize_answer_text(_append_applicability_suffix(answer, state))

    summary_parts: list[str] = []
    for item in items:
        text = str(item.get("content", "") or "").strip()
        if not text:
            continue
        source = item.get("source_file") or item.get("source_ref") or item.get("title", "")
        compact = _compact_text(text, limit=180)
        if compact:
            prefix = f"{source}：".strip("：") if source else ""
            summary_parts.append(f"{prefix}{compact}" if prefix else compact)

    if not summary_parts:
        return _finalize_answer_text(_append_applicability_suffix("抱歉，未能生成答案。", state))
    if len(summary_parts) == 1:
        answer = summary_parts[0]
    else:
        answer = "；".join(summary_parts)
    return _finalize_answer_text(_append_applicability_suffix(answer, state))


def _naturalize_markdown_answer(title: str, content: str) -> str:
    lines = [line.strip() for line in content.splitlines()]
    summary_lines: list[str] = []
    definition_lines: list[str] = []
    fact_lines: list[str] = []
    current_section = ""

    for line in lines:
        if not line:
            continue
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        if line.startswith("- "):
            if current_section == "关键事实":
                fact_lines.append(re.sub(r"\s*_\(.+?\)_\s*$", "", line[2:].strip()))
            continue
        if current_section == "摘要":
            summary_lines.append(line)
        elif current_section == "定义":
            definition_lines.append(line)
        elif current_section and current_section not in {"关键事实", "相关概念"}:
            fact_lines.append(line)

    core = definition_lines or summary_lines or fact_lines
    if not core:
        return _finalize_answer_text(_compact_text(content, limit=260))

    answer = _compact_text(" ".join(core[:2]), limit=320)
    if title and answer and not answer.startswith(title):
        return _finalize_answer_text(answer)
    return _finalize_answer_text(answer)


def _compact_text(text: str, limit: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit].rstrip()


def _finalize_answer_text(text: str) -> str:
    cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"(?m)^#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(
        r"^(根据(?:原文|资料|材料|以上内容|已知信息|现有信息)(?:和|及)?(?:检索到的)?(?:\s*Wiki\s*卡片|\s*卡片|\s*切片|\s*证据)?[，,：:]*)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"^(根据(?:检索结果|检索到的信息|现有证据|以上证据|当前证据)(?:可知|显示)?[，,：:]*)",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(检索到的\s*Wiki\s*卡片|检索到的卡片|原文切块|切片卡片|证据链路)", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
