"""2. extract_query - 抽取查询关键词、实体、查询变体。"""
from __future__ import annotations

import asyncio
import re

from app.agent.state import AgentState
from app.agent.trace import add_stage
from app.retrieval.query_features import (
    QueryFeatures,
    extract_query_entities,
    hybrid_rewrite_query,
)


ANSWER_REQUIREMENTS_KEYWORDS = {
    "procedure": [
        "步骤", "怎么", "如何", "拆卸", "安装", "流程", "拆装", "更换", "程序",
        "procedure", "step", "how to", "disassemble", "assemble", "remove", "install", "replace"
    ],
    "warning": [
        "注意", "警告", "危险", "小心", "注意事项", "警示",
        "warning", "caution", "danger", "note", "notice"
    ],
    "parameter": [
        "参数", "压力", "温度", "力矩", "值", "规格", "限制", "扭矩", "尺寸", "标准",
        "parameter", "value", "torque", "limit", "spec", "pressure", "temperature"
    ],
    "applicability": [
        "适用于", "哪些机型", "哪个版本", "适用范围",
        "applicable", "model", "version", "revision", "applicability"
    ],
    "tooling": [
        "工具", "设备", "需要什么", "准备", "材料", "耗材",
        "tool", "equipment", "material", "prepare", "tooling", "consumable"
    ],
}

MANUAL_TYPE_MAP = {
    "AMM": "AMM",
    "FIM": "FIM",
    "TSM": "TSM",
    "IPC": "IPC",
    "WDM": "WDM",
    "SRM": "SRM",
    "CMM": "CMM",
    "SB": "SB",
    "AD": "AD",
    "MEL": "MEL",
    "CDL": "CDL",
    "飞机维护手册": "AMM",
    "故障隔离手册": "FIM",
    "排故手册": "TSM",
    "零件目录": "IPC",
    "线路图手册": "WDM",
}


def extract_answer_requirements(query: str) -> dict:
    """基于关键词规则抽取 answer_requirements。"""
    result = {
        "procedure": False,
        "warning": False,
        "parameter": False,
        "applicability": False,
        "tooling": False,
    }
    query_lower = query.lower()
    for req_type, keywords in ANSWER_REQUIREMENTS_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                result[req_type] = True
                break
    return result


def extract_applicability_filters(query: str) -> dict:
    """基于正则规则抽取 applicability_filters。"""
    result = {
        "aircraft_model": None,
        "manual_type": None,
        "ata_chapter": None,
    }

    haystack = query.upper()

    aircraft_patterns = [
        r"(?<![A-Z0-9])(A320|A321|A330|A350|A380)(?![A-Z0-9])",
        r"(?<![A-Z0-9])(B737NG|B737MAX|B737|B787)(?![A-Z0-9])",
        r"(?<![A-Z0-9])(C919|ARJ21)(?![A-Z0-9])",
        r"(?<![A-Z0-9])(CH[-_ ]?\d+[A-Z]?)(?![A-Z0-9])",
    ]
    for pattern in aircraft_patterns:
        match = re.search(pattern, haystack)
        if match:
            result["aircraft_model"] = match.group(1).replace("_", "-").replace(" ", "-")
            break

    for zh_name, code in MANUAL_TYPE_MAP.items():
        if zh_name in query:
            result["manual_type"] = code
            break
    if not result["manual_type"]:
        for code in ["AMM", "FIM", "TSM", "IPC", "WDM", "SRM", "CMM", "SB", "AD", "MEL", "CDL"]:
            if re.search(rf"\b{code}\b", haystack):
                result["manual_type"] = code
                break

    ata_match = re.search(r"第\s*(\d{2})\s*章", query)
    if not ata_match:
        ata_match = re.search(r"ATA[\s_-]*(\d{2})", haystack)
    if not ata_match:
        ata_match = re.search(r"(?:^|[^\d])(\d{2})[-_ ](?:\d{2}|[A-Z])", haystack)
    if ata_match:
        result["ata_chapter"] = ata_match.group(1)

    return result


def _apply_rule_extraction(state: AgentState) -> tuple[dict, dict]:
    """应用规则抽取并更新 state。"""
    answer_requirements = extract_answer_requirements(state.question)
    applicability_filters = extract_applicability_filters(state.question)

    state.answer_requirements.update(answer_requirements)
    state.applicability_filters.update({k: v for k, v in applicability_filters.items() if v is not None})

    if state.retrieval_trace:
        state.retrieval_trace.answer_requirements = state.answer_requirements.copy()
        state.retrieval_trace.applicability_filters = state.applicability_filters.copy()

    return answer_requirements, applicability_filters


def extract_query_node(state: AgentState) -> AgentState:
    """同步版本：仅本地规则扩展。"""
    features = QueryFeatures(state.question)
    features.extract()
    state.query_features = {
        **state.query_features,
        "query_variants": features.query_variants,
        "synonyms": features.synonyms,
    }
    state.entities = extract_query_entities(state.question)

    answer_requirements, applicability_filters = _apply_rule_extraction(state)

    if state.retrieval_trace:
        state.retrieval_trace.query_variants = features.query_variants
        add_stage(
            state,
            "extract_query",
            "查询特征抽取",
            variants=len(features.query_variants),
            entities=state.entities,
            answer_requirements=answer_requirements,
            applicability_filters=applicability_filters,
        )
    return state


async def extract_query_node_async(state: AgentState) -> AgentState:
    """异步版本：含 LLM 改写。"""
    features = QueryFeatures(state.question)
    features.extract()

    _apply_rule_extraction(state)

    all_variants = features.build_fusion_queries()
    try:
        llm_variants = await hybrid_rewrite_query(state.question)
        all_variants = list(set(features.build_fusion_queries() + llm_variants))
    except Exception:
        pass

    state.query_features = {
        **state.query_features,
        "query_variants": all_variants[:8],
        "synonyms": features.synonyms,
    }
    state.entities = extract_query_entities(state.question)
    if state.retrieval_trace:
        state.retrieval_trace.query_variants = all_variants[:8]
        add_stage(
            state,
            "extract_query",
            "查询特征抽取",
            variants=len(all_variants[:8]),
            entities=state.entities,
            answer_requirements=state.answer_requirements,
            applicability_filters=state.applicability_filters,
        )
    return state
