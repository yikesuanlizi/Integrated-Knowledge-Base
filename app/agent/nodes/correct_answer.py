"""12. correct_answer - 证据不足时LLM反思失败原因，改写查询词，触发重新检索。"""
from __future__ import annotations

import json
import re

from app.agent.state import AgentState
from app.agent.nodes.generate_answer import _finalize_answer_text
from app.agent.trace import add_stage
from app.clients.llm_client import llm_client
from app.core.log import logger


def _build_rewrite_prompt(state: AgentState) -> tuple[str, str]:
    feedback = state.planner_feedback or {}
    reasons = feedback.get("reasons", [])
    wiki_count = feedback.get("wiki_count", 0)
    chunk_count = feedback.get("chunk_count", 0)
    entity_count = feedback.get("entity_count", 0)
    structured_count = feedback.get("structured_count", 0)
    blocked_by_review = feedback.get("blocked_by_review", False)
    prev_channels = (state.retrieval_plan or {}).get("selected_channels", [])
    original_q = state.original_question or state.question
    current_q = state.question

    system_prompt = """你是一个专业的检索查询改写器（Query Rewriter）。
当前检索证据不足，你需要分析失败原因并重写用户查询，使其更容易检索到相关内容。

## 改写策略：
1. 如果是概念/术语问题没找到wiki卡片，可以补充同义术语、上位概念
2. 如果是操作步骤问题没找到原文切块，可以把问题拆成更具体的关键词组合
3. 如果实体识别遗漏了部件名/故障码，可以显式补充关键实体词
4. 如果是因为审核门控挡住了，可以提示"已审核"相关内容（但不要编造信息）
5. 不要偏离用户原始意图，改写后的query必须仍然回答原问题
6. 使用工业维修领域的标准术语，避免口语化
7. 返回JSON格式，不要有其他说明文字
8. 如果缺失某些证据类型（如warning、procedure、parameter），在改写时主动补充对应领域关键词（如缺少警告类证据则加入"注意事项 警告 小心"等词）
9. 如果存在适用性冲突（如指定A320但召回到其他机型），在改写时明确强调指定机型/ATA章节，过滤无关内容"""

    reasons_text = "\n".join([f"- {r}" for r in reasons]) if reasons else "未提供具体原因"
    channel_stats = f"wiki:{wiki_count}, chunks:{chunk_count}, entities:{entity_count}, structured:{structured_count}"

    missing_requirements_text = "无"
    if state.missing_requirements:
        missing_requirements_text = ", ".join(state.missing_requirements)

    applicability_conflict_text = "无"
    if state.applicability_conflict:
        applicability_conflict_text = "检索到的证据与指定机型不符，需要强调指定机型过滤无关内容"

    applicability_filters_text = json.dumps(state.applicability_filters, ensure_ascii=False, indent=2)

    user_prompt = f"""请根据以下信息，改写用户查询：

## 原始问题
{original_q}

## 当前使用的查询（第{state.iteration}轮）
{current_q}

## 上一轮检索结果统计
{channel_stats}

## 上一轮选择的通道
{json.dumps(prev_channels, ensure_ascii=False)}

## 证据不足原因
{reasons_text}

## 是否被审核门控挡住
{"是" if blocked_by_review else "否"}

## 缺失的证据类型
{missing_requirements_text}

## 适用性冲突
{applicability_conflict_text}

## 指定的过滤条件
{applicability_filters_text}

请返回JSON：
{{
  "analysis": "分析为什么上一轮检索失败（中文）",
  "rewritten_query": "改写后的查询词（中文，更精准、更适合检索）",
  "strategy_adjustment": "建议下一轮planner如何调整通道选择"
}}"""

    return system_prompt, user_prompt


def _extract_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


REQUIREMENT_KEYWORDS_APPEND = {
    "warning": " 注意事项 警告 小心 warning caution",
    "procedure": " 步骤 流程 方法 拆装 procedure step",
    "parameter": " 参数 规格 力矩 值 限制 parameter torque limit",
    "tooling": " 工具 设备 准备 材料 tool equipment",
    "applicability": " 适用范围 机型 版本 applicability model",
}


def _rule_based_rewrite(state: AgentState) -> dict:
    original_q = state.original_question or state.question
    feedback = state.planner_feedback or {}
    reasons = feedback.get("reasons", [])

    rewritten = original_q
    if any("wiki" in str(r).lower() or "卡片" in str(r) for r in reasons):
        rewritten = f"{original_q} 定义 原理 说明"
    elif any("chunk" in str(r).lower() or "切块" in str(r) or "原文" in str(r) for r in reasons):
        rewritten = f"{original_q} 步骤 方法 流程"
    elif any("entity" in str(r).lower() or "实体" in str(r) for r in reasons):
        entities = state.entities or {}
        entity_terms = []
        for etype, evals in entities.items():
            if isinstance(evals, list):
                entity_terms.extend([str(v) for v in evals[:3]])
        if entity_terms:
            rewritten = f"{original_q} {' '.join(entity_terms)}"

    if state.missing_requirements:
        for req in state.missing_requirements:
            if req in REQUIREMENT_KEYWORDS_APPEND:
                rewritten += REQUIREMENT_KEYWORDS_APPEND[req]

    if state.applicability_conflict and state.applicability_filters:
        aircraft_model = state.applicability_filters.get("aircraft_model")
        if aircraft_model:
            rewritten = f"{aircraft_model} {rewritten}"

    return {
        "analysis": "LLM rewrite failed, using rule-based fallback",
        "rewritten_query": rewritten,
        "strategy_adjustment": "broaden recall scope",
    }


def correct_answer_node(state: AgentState) -> AgentState:
    state.iteration += 1

    if state.iteration >= state.max_iterations:
        items = state.reranked_results[:3]
        if items:
            parts = []
            for item in items:
                content = item.get("content", "")
                if content:
                    parts.append(_finalize_answer_text(str(content)[:300]))
            if len(parts) == 1:
                state.answer = parts[0]
            else:
                state.answer = "\n\n".join(parts)
        else:
            state.answer = "抱歉，没有找到充分的相关信息来回答您的问题。"
        state.needs_clarification = True
        return state

    logger.info(f"Correcting answer, iteration {state.iteration}/{state.max_iterations}, feedback: {state.planner_feedback.get('reasons', [])}")

    rewrite_result = None
    fallback_used = False

    try:
        system_prompt, user_prompt = _build_rewrite_prompt(state)
        llm_response = llm_client.generate_sync(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=500,
            scene="query_rewrite",
        )
        parsed = _extract_json(llm_response)
        if parsed and isinstance(parsed.get("rewritten_query"), str) and parsed["rewritten_query"].strip():
            rewrite_result = parsed
        else:
            logger.warning("Query rewrite LLM returned invalid format, using rule-based fallback")
            fallback_used = True
    except Exception as e:
        logger.warning(f"Query rewrite LLM failed: {e}, using rule-based fallback")
        fallback_used = True

    if rewrite_result is None:
        rewrite_result = _rule_based_rewrite(state)

    prev_question = state.question
    new_question = rewrite_result.get("rewritten_query", "").strip()
    if not new_question:
        new_question = state.original_question or state.question

    state.question = new_question

    state.rewrite_history.append({
        "iteration": state.iteration,
        "previous_query": prev_question,
        "rewritten_query": new_question,
        "analysis": rewrite_result.get("analysis", ""),
        "strategy_adjustment": rewrite_result.get("strategy_adjustment", ""),
        "fallback_used": fallback_used,
    })

    state.wiki_results = []
    state.chunk_results = []
    state.entity_results = []
    state.structured_results = []
    state.merged_results = []
    state.expanded_results = []
    state.reranked_results = []
    state.evidence_pack = {}
    state.citations = []
    state.evidence_sufficiency = {}
    state.retrieval_plan = {}

    if state.retrieval_trace:
        add_stage(
            state,
            "correct_answer",
            "查询反思改写",
            iteration=state.iteration,
            rewritten_query=new_question,
            analysis=rewrite_result.get("analysis", ""),
            fallback_used=fallback_used,
            missing_requirements=state.missing_requirements,
            applicability_conflict=state.applicability_conflict,
            applicability_filters=state.applicability_filters,
        )

    return state
