from __future__ import annotations

from enum import Enum
from typing import List, Optional

from app.models.schemas import QueryIntent


class IntentType(str, Enum):
    PROCEDURE = "procedure"
    TOOLS_MATERIALS = "tools_materials"
    WARNING_SAFETY = "warning_safety"
    NUMERICAL_REQUIREMENT = "numerical_requirement"
    PART_FUNCTION = "part_function"
    TROUBLESHOOTING = "troubleshooting"
    GENERAL_QUERY = "general_query"


INTENT_KEYWORDS: dict[IntentType, List[str]] = {
    IntentType.PROCEDURE: [
        "步骤", "流程", "操作", "方法", "过程", "如何", "怎样",
        "拆卸", "安装", "更换", "检查", "清洁", "润滑", "调试",
        "启动", "停止", "打开", "关闭", "调整",
    ],
    IntentType.TOOLS_MATERIALS: [
        "工具", "材料", "设备", "耗材", "配件", "零件",
        "需要", "准备", "使用",
    ],
    IntentType.WARNING_SAFETY: [
        "警告", "注意", "危险", "安全", "严禁", "不得",
        "禁止", "小心", "避免",
    ],
    IntentType.NUMERICAL_REQUIREMENT: [
        "参数", "规格", "要求", "标准", "数值", "范围",
        "压力", "温度", "尺寸", "重量",
    ],
    IntentType.PART_FUNCTION: [
        "功能", "作用", "用途", "原理", "结构",
        "部件", "组件", "系统",
    ],
    IntentType.TROUBLESHOOTING: [
        "故障", "问题", "异常", "错误", "失效",
        "排除", "解决", "修复", "诊断",
    ],
    IntentType.GENERAL_QUERY: [
        "什么", "定义", "概念", "说明", "介绍",
        "包括", "包含", "有哪些", "区别", "差异",
    ],
}


INTENT_ROUTES: dict[IntentType, str] = {
    IntentType.PROCEDURE: "fact",
    IntentType.TOOLS_MATERIALS: "fact",
    IntentType.WARNING_SAFETY: "complex",
    IntentType.NUMERICAL_REQUIREMENT: "fact",
    IntentType.PART_FUNCTION: "concept",
    IntentType.TROUBLESHOOTING: "complex",
    IntentType.GENERAL_QUERY: "concept",
}


def classify_intent(question: str) -> QueryIntent:
    scores: dict[IntentType, int] = {intent: 0 for intent in IntentType}

    question_lower = question.lower()
    question_upper = question.upper()

    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in question_lower or keyword in question:
                scores[intent] += 1

    if any(keyword in question for keyword in ["区别", "差异", "关系", "联系"]):
        scores[IntentType.TROUBLESHOOTING] += 2

    primary = max(scores, key=scores.get)
    confidence = scores[primary] / max(sum(scores.values()), 1)

    secondary = sorted(
        [intent for intent in IntentType if intent != primary and scores[intent] > 0],
        key=lambda x: scores[x],
        reverse=True,
    )

    keywords = extract_query_keywords(question)
    entities = extract_entities_from_query(question)

    safety_sensitive = scores[IntentType.WARNING_SAFETY] > 0 or any(
        kw in question for kw in ["危险", "安全", "警告", "注意"]
    )
    expects_procedure = scores[IntentType.PROCEDURE] > 0 or scores[IntentType.TROUBLESHOOTING] > 0

    return QueryIntent(
        primary=primary.value,
        secondary=[intent.value for intent in secondary],
        confidence=confidence,
        route=INTENT_ROUTES[primary],
        keywords=keywords,
        entities=entities,
        safety_sensitive=safety_sensitive,
        expects_procedure=expects_procedure,
    )


def extract_query_keywords(question: str) -> List[str]:
    keywords: List[str] = []

    import re

    for intent, intent_keywords in INTENT_KEYWORDS.items():
        for keyword in intent_keywords:
            if keyword in question and keyword not in keywords:
                keywords.append(keyword)

    for match in re.finditer(r"(?<![\u4e00-\u9fff])[\u4e00-\u9fff]{2,6}(?![\u4e00-\u9fff])", question):
        word = match.group(0)
        if word not in keywords:
            keywords.append(word)

    for match in re.finditer(r"(?<![A-Za-z0-9])[A-Z0-9]{3,}(?![A-Za-z0-9])", question):
        word = match.group(0)
        if word not in keywords:
            keywords.append(word)

    return keywords[:20]


def extract_entities_from_query(question: str) -> dict:
    entities: dict = {
        "part_numbers": [],
        "components": [],
        "actions": [],
    }

    import re

    part_pattern = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{3,}[-_]?[A-Z0-9]+(?![A-Za-z0-9])")
    for match in part_pattern.finditer(question):
        entities["part_numbers"].append(match.group(0))

    component_pattern = re.compile(r"(?<![\u4e00-\u9fff])[\u4e00-\u9fff]{2,}(?:[部件组件零件装置设备系统])(?![\u4e00-\u9fff])")
    for match in component_pattern.finditer(question):
        entities["components"].append(match.group(0))

    action_pattern = re.compile(r"(?:拆卸|安装|更换|检查|清洁|润滑|调试|测试|启动|停止|关闭|打开|调节|调整|控制|监控)")
    for match in action_pattern.finditer(question):
        entities["actions"].append(match.group(0))

    return entities


def is_safety_sensitive(intent: QueryIntent) -> bool:
    return intent.safety_sensitive or IntentType.WARNING_SAFETY.value in intent.secondary


def requires_procedure(intent: QueryIntent) -> bool:
    return intent.expects_procedure or IntentType.PROCEDURE.value == intent.primary


def get_intent_config(intent: QueryIntent) -> dict:
    intent_type = IntentType(intent.primary)

    configs = {
        IntentType.PROCEDURE: {
            "top_k": 10,
            "rerank_weight": 0.7,
            "graph_expand_hops": 2,
            "require_evidence": True,
        },
        IntentType.TOOLS_MATERIALS: {
            "top_k": 8,
            "rerank_weight": 0.6,
            "graph_expand_hops": 1,
            "require_evidence": True,
        },
        IntentType.WARNING_SAFETY: {
            "top_k": 12,
            "rerank_weight": 0.8,
            "graph_expand_hops": 2,
            "require_evidence": True,
            "safety_critical": True,
        },
        IntentType.NUMERICAL_REQUIREMENT: {
            "top_k": 8,
            "rerank_weight": 0.7,
            "graph_expand_hops": 1,
            "require_evidence": True,
        },
        IntentType.PART_FUNCTION: {
            "top_k": 6,
            "rerank_weight": 0.5,
            "graph_expand_hops": 2,
            "require_evidence": False,
        },
        IntentType.TROUBLESHOOTING: {
            "top_k": 10,
            "rerank_weight": 0.7,
            "graph_expand_hops": 2,
            "require_evidence": True,
        },
        IntentType.GENERAL_QUERY: {
            "top_k": 6,
            "rerank_weight": 0.5,
            "graph_expand_hops": 1,
            "require_evidence": False,
        },
    }

    return configs.get(intent_type, configs[IntentType.GENERAL_QUERY])
