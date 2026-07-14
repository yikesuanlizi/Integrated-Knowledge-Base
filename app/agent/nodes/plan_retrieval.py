"""plan_retrieval - 检索规划节点：LLM/Agent Planner 动态选择召回通道，规则兜底。"""
from __future__ import annotations

import json
import re
from typing import Any

from app.agent.nodes.recall_dispatch import ROUTE_CHANNELS
from app.agent.state import AgentState
from app.agent.trace import add_stage
from app.clients.llm_client import llm_client
from app.core.log import logger

ALLOWED_CHANNELS = {"wiki", "chunks", "entities", "structured_metadata"}

RERANK_PROFILES = {"default", "safety_strict", "concept_first", "procedure_first"}


def _build_baseline_plan(state: AgentState) -> dict[str, Any]:
    route = state.planner_route or "fact"
    baseline_channels = ROUTE_CHANNELS.get(route, ROUTE_CHANNELS["fact"])
    route_strategy_map = {
        "concept": "concept_definition",
        "fact": "fact_lookup",
        "complex": "comprehensive",
    }

    planner_feedback = state.planner_feedback or {}
    missing_requirements = planner_feedback.get("missing_requirements", []) or state.missing_requirements or []
    applicability_conflict = planner_feedback.get("applicability_conflict", False) or state.applicability_conflict
    applicability_filters = state.applicability_filters or {}

    if state.iteration == 0:
        missing_requirements = []
        applicability_conflict = False

    selected_channels = list(baseline_channels)
    rerank_profile = "safety_strict" if getattr(state.intent, "safety_sensitive", False) else "default"
    strategy = route_strategy_map.get(route, "fact_lookup")
    expand_graph = route in ("concept", "complex")
    reason = f"Baseline plan for {route} intent"
    responded_to_missing: list[str] = []

    def _ensure_chunks_front():
        nonlocal selected_channels
        if "chunks" in selected_channels:
            selected_channels.remove("chunks")
        selected_channels.insert(0, "chunks")

    def _ensure_chunks():
        nonlocal selected_channels
        if "chunks" not in selected_channels:
            selected_channels.insert(0, "chunks")

    if "warning" in missing_requirements or applicability_conflict:
        _ensure_chunks()
        rerank_profile = "safety_strict"
        if strategy != "comprehensive":
            strategy = "procedure_evidence_first"
        reason += "；根据反馈调整：优先chunks通道，安全严格模式"
        if "warning" in missing_requirements:
            responded_to_missing.append("warning")

    if "procedure" in missing_requirements:
        _ensure_chunks()
        if strategy != "comprehensive":
            strategy = "procedure_evidence_first"
        reason += "；根据反馈调整：优先步骤类原文证据"
        responded_to_missing.append("procedure")

    if "parameter" in missing_requirements:
        _ensure_chunks()
        if "structured_metadata" not in selected_channels:
            selected_channels.append("structured_metadata")
        reason += "；根据反馈调整：增加结构化元数据通道查询参数"
        responded_to_missing.append("parameter")

    if "tooling" in missing_requirements:
        _ensure_chunks()
        reason += "；根据反馈调整：优先chunks查找工具/材料信息"
        responded_to_missing.append("tooling")

    if applicability_conflict:
        _ensure_chunks_front()
        reason += "；适用性冲突：优先原文证据，避免跨机型混淆"

    seen: set[str] = set()
    deduped_channels: list[str] = []
    for ch in selected_channels:
        if ch not in seen:
            seen.add(ch)
            deduped_channels.append(ch)
    selected_channels = deduped_channels

    filter_applicability = bool(
        applicability_filters.get("aircraft_model")
        or applicability_filters.get("manual_type")
        or applicability_filters.get("ata_chapter")
    )

    return {
        "selected_channels": selected_channels,
        "reason": reason,
        "strategy": strategy,
        "expand_graph": expand_graph,
        "rerank_profile": rerank_profile,
        "fallback_used": False,
        "applicability_conflict": applicability_conflict,
        "missing_requirements": list(missing_requirements),
        "filter_applicability": filter_applicability,
        "responded_to_missing": responded_to_missing,
        "responded_to_applicability_conflict": applicability_conflict,
    }


def _build_planner_prompt(state: AgentState, baseline: dict[str, Any], iteration: int) -> tuple[str, str]:
    intent_info = {
        "route": state.planner_route or "fact",
        "safety_sensitive": bool(getattr(state.intent, "safety_sensitive", False)),
    }
    query_features = dict(state.query_features) if state.query_features else {}
    keywords = list(state.keywords) if state.keywords else []
    entities = state.entities if state.entities else {}
    planner_feedback = dict(state.planner_feedback) if state.planner_feedback else {}
    rewrite_history = list(state.rewrite_history) if state.rewrite_history else []
    original_question = state.original_question or state.question
    active_question = state.question

    missing_requirements = planner_feedback.get("missing_requirements", []) or state.missing_requirements or []
    applicability_conflict = planner_feedback.get("applicability_conflict", False) or state.applicability_conflict
    applicability_filters = state.applicability_filters or {}

    if state.iteration == 0:
        missing_requirements = []
        applicability_conflict = False

    system_prompt = """你是一个专业的检索规划器（Retrieval Planner），负责为工业设备维修知识库的问答系统选择最优的召回通道。

## 允许选择的召回通道（只能从以下选择，不能编造工具名）：
1. **wiki** - Wiki知识卡片：适合概念解释、定义类问题、设备原理说明
2. **chunks** - 原文切块：适合具体操作步骤、维修流程、参数值、事实性问题（必须选择）
3. **entities** - 实体关联：包含部件名称、故障码、型号等实体时选择，辅助定位上下文
4. **structured_metadata** - 结构化元数据：仅当问题明确询问知识库统计信息（如"有多少已审核卡片"、"有哪些设备类型"）时选择，普通问题不要选

## 规划策略选项（strategy字段）：
- concept_definition: 概念定义类问题
- fact_lookup: 事实查找类问题（默认）
- procedure_evidence_first: 操作流程类问题，优先原文证据
- comprehensive: 复杂综合问题，多路召回
- metadata_only: 纯元数据统计问题

## Rerank配置（rerank_profile字段）：
- default: 默认配置
- safety_strict: 安全敏感问题（涉及高压、高温、安全操作等），严格审核
- concept_first: 概念优先
- procedure_first: 流程优先

## 重要规则：
1. chunks通道几乎总是需要选择（除纯概念或纯元数据问题）
2. 如果是第二轮检索（iteration > 0），请根据planner_feedback中的不足原因调整通道选择
3. 如果问题涉及安全操作，rerank_profile必须设为safety_strict
4. 必须返回严格的JSON格式，不要有任何其他说明文字
5. selected_channels保持合理顺序，把最相关的通道放前面
6. 如果planner_feedback中标记了missing_requirements（缺少warning/procedure/parameter/tooling等类型的证据），你必须确保选中能召回这类证据的通道（chunks通道几乎必选）。如果缺少warning/安全类内容，rerank_profile必须设为safety_strict；如果缺少procedure/步骤类内容，strategy可设为procedure_evidence_first。
7. 如果存在applicability_conflict（跨机型/版本冲突），你必须将chunks通道放在第一位优先召回原文证据，rerank_profile设为safety_strict，并在reason中说明需要强调指定机型过滤，避免跨机型混淆。
8. 如果存在applicability_filters（用户指定了机型/手册/ATA章节），确保你的规划能够配合前置过滤，优先chunks通道。"""

    rewrite_history_text = "首轮检索，无改写历史"
    if rewrite_history:
        parts = []
        for h in rewrite_history[-3:]:
            parts.append(f"- 第{h.get('iteration', '?')}轮: \"{h.get('previous_query', '')}\" → \"{h.get('rewritten_query', '')}\"")
            if h.get("analysis"):
                parts.append(f"  分析: {h['analysis']}")
            if h.get("strategy_adjustment"):
                parts.append(f"  调整建议: {h['strategy_adjustment']}")
        rewrite_history_text = "\n".join(parts)

    if missing_requirements:
        mr_explanations = {
            "procedure": "操作步骤类",
            "warning": "警告/注意事项",
            "parameter": "参数/限制值",
            "tooling": "工具/材料",
            "applicability": "适用范围",
        }
        mr_lines = []
        for mr in missing_requirements:
            mr_lines.append(f"- {mr}: {mr_explanations.get(mr, '')}")
        missing_requirements_text = "\n".join(mr_lines)
    else:
        missing_requirements_text = "无缺失，首轮检索"

    if applicability_conflict:
        applicability_conflict_text = "存在跨机型/版本冲突，请优先原文证据并强调指定机型过滤"
    else:
        applicability_conflict_text = "无冲突"

    has_filter = bool(applicability_filters.get("aircraft_model") or applicability_filters.get("manual_type") or applicability_filters.get("ata_chapter"))
    if has_filter:
        applicability_filters_text = json.dumps(applicability_filters, ensure_ascii=False, indent=2)
    else:
        applicability_filters_text = "未指定"

    user_prompt = f"""请为以下问题生成检索规划：

## 用户原始问题
{original_question}

## 当前轮次使用的查询（可能是改写后的）
{active_question}

## 当前迭代轮次
{iteration}

## 意图分类
{json.dumps(intent_info, ensure_ascii=False, indent=2)}

## 查询特征
{json.dumps(query_features, ensure_ascii=False, indent=2)}

## 提取的关键词
{json.dumps(keywords, ensure_ascii=False)}

## 识别的实体
{json.dumps(entities, ensure_ascii=False, indent=2) if entities else "无"}

## 上一轮检索反馈
{json.dumps(planner_feedback, ensure_ascii=False, indent=2) if planner_feedback else "首轮检索，无反馈"}

## 缺失的证据类型
{missing_requirements_text}

## 适用性冲突
{applicability_conflict_text}

## 用户指定的过滤条件
{applicability_filters_text}

## 历史改写记录
{rewrite_history_text}

## 基线规划（供参考和调整）
{json.dumps(baseline, ensure_ascii=False, indent=2)}

请返回JSON格式的检索规划，包含以下字段：
- selected_channels: 通道列表，按优先级排序
- reason: 选择理由（中文）
- strategy: 策略名称
- expand_graph: true/false
- rerank_profile: 配置名称
- channel_top_k: 可选，指定各通道召回数量，如{{"chunks": 5, "wiki": 3}}

示例JSON：
{{
  "selected_channels": ["chunks", "wiki"],
  "reason": "选择理由",
  "strategy": "fact_lookup",
  "expand_graph": false,
  "rerank_profile": "default"
}}"""

    return system_prompt, user_prompt


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _sanitize_plan(plan: dict[str, Any] | None, baseline: dict[str, Any]) -> dict[str, Any]:
    if not plan or not isinstance(plan, dict):
        result = dict(baseline)
        result["fallback_used"] = True
        result["invalid_reason"] = "LLM returned empty or invalid plan"
        return result

    selected = plan.get("selected_channels")
    valid_channels: list[str] = []
    invalid_channels: list[str] = []

    if isinstance(selected, list):
        seen = set()
        for ch in selected:
            if isinstance(ch, str):
                ch_lower = ch.strip().lower()
                if ch_lower in ALLOWED_CHANNELS and ch_lower not in seen:
                    valid_channels.append(ch_lower)
                    seen.add(ch_lower)
                elif ch_lower not in ALLOWED_CHANNELS:
                    invalid_channels.append(ch)

    if not valid_channels:
        result = dict(baseline)
        result["fallback_used"] = True
        result["invalid_reason"] = f"No valid channels selected, invalid: {invalid_channels}"
        return result

    strategy = plan.get("strategy")
    if strategy not in {"concept_definition", "fact_lookup", "procedure_evidence_first", "comprehensive", "metadata_only"}:
        strategy = baseline.get("strategy", "fact_lookup")

    rerank_profile = plan.get("rerank_profile")
    if rerank_profile not in RERANK_PROFILES:
        rerank_profile = baseline.get("rerank_profile", "default")

    expand_graph = bool(plan.get("expand_graph", baseline.get("expand_graph", False)))

    reason = plan.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = baseline.get("reason", "LLM adjusted plan")

    channel_top_k = plan.get("channel_top_k")
    if not isinstance(channel_top_k, dict):
        channel_top_k = baseline.get("channel_top_k")

    result = {
        "selected_channels": valid_channels,
        "reason": reason,
        "strategy": strategy,
        "expand_graph": expand_graph,
        "rerank_profile": rerank_profile,
        "fallback_used": False,
        "invalid_channels": invalid_channels if invalid_channels else None,
        "applicability_conflict": baseline.get("applicability_conflict", False),
        "missing_requirements": baseline.get("missing_requirements", []),
        "filter_applicability": baseline.get("filter_applicability", False),
        "responded_to_missing": baseline.get("responded_to_missing", []),
        "responded_to_applicability_conflict": baseline.get("responded_to_applicability_conflict", False),
    }

    if channel_top_k is not None:
        result["channel_top_k"] = channel_top_k

    return result


def plan_retrieval_node(state: AgentState) -> AgentState:
    baseline = _build_baseline_plan(state)

    current_iteration = state.iteration + 1

    try:
        system_prompt, user_prompt = _build_planner_prompt(state, baseline, current_iteration)
        llm_response = llm_client.generate_sync(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
            scene="retrieval_planner",
        )
        llm_plan = _extract_json(llm_response)
        plan = _sanitize_plan(llm_plan, baseline)
    except Exception as e:
        logger.warning(f"Retrieval planner LLM failed: {e}, using baseline")
        plan = dict(baseline)
        plan["fallback_used"] = True
        plan["llm_error"] = str(e)[:200]

    state.retrieval_plan = plan

    if state.retrieval_trace is None:
        from app.models.schemas import RetrievalTrace
        state.retrieval_trace = RetrievalTrace()

    grounding = state.retrieval_trace.grounding if state.retrieval_trace.grounding else {}
    grounding["agent_planner"] = {
        "selected_channels": plan.get("selected_channels", []),
        "reason": plan.get("reason", ""),
        "strategy": plan.get("strategy", ""),
        "expand_graph": plan.get("expand_graph", False),
        "rerank_profile": plan.get("rerank_profile", "default"),
        "fallback_used": plan.get("fallback_used", False),
        "iteration": current_iteration,
        "allowed_channels": sorted(list(ALLOWED_CHANNELS)),
        "invalid_channels": plan.get("invalid_channels"),
        "llm_error": plan.get("llm_error"),
    }
    state.retrieval_trace.grounding = grounding

    add_stage(
        state,
        "plan_retrieval",
        "检索规划",
        selected_channels=plan.get("selected_channels", []),
        strategy=plan.get("strategy", ""),
        fallback_used=plan.get("fallback_used", False),
        iteration=current_iteration,
        responded_to_missing=plan.get("responded_to_missing", []),
        responded_to_applicability_conflict=plan.get("responded_to_applicability_conflict", False),
        filter_applicability=plan.get("filter_applicability", False),
        missing_requirements=plan.get("missing_requirements", []),
    )

    return state
