from __future__ import annotations

import re

from app.nl2sql.schemas import RouteDecision


STRUCTURED_METADATA_HINTS = {
    "故障次数",
    "故障数",
    "工单数",
    "维修次数",
    "停场小时",
    "停场时间",
    "AOG",
    "维修工时",
    "人工工时",
    "平均停场",
    "统计",
    "排行",
    "排名",
    "最高",
    "最低",
    "各基地",
    "各区域",
    "维修基地",
    "基地",
    "区域",
    "地区",
    "机型",
    "飞机",
    "注册号",
    "部件",
    "组件",
    "系统",
    "ATA",
    "起落架轮迹",
    "液压泵",
    "道面等级号",
    "飞机等级号",
    "登机门",
    "同比",
    "环比",
    "按月",
    "按年",
    "2025",
}

KNOWLEDGE_KEYWORDS = {
    "文档",
    "手册",
    "步骤",
    "拆卸",
    "安装",
    "引用",
    "证据",
    "wiki",
    "Wiki",
    "知识库",
    "解释",
    "原文",
    "章节",
    "维护",
    "故障",
}

DESTRUCTIVE_HINTS = {"删除", "drop", "truncate", "update", "insert", "清空", "建表", "修改表"}


def classify_query_route(question: str) -> RouteDecision:
    """Detect whether structured metadata may help, while keeping /api/query in evidence lookup mode."""
    normalized = question.strip()
    lower = normalized.lower()
    reasons: list[str] = []

    if any(hint in lower for hint in DESTRUCTIVE_HINTS):
        return RouteDecision(
            route="evidence_lookup",
            confidence=0.9,
            reasons=["contains database operation wording; keep in evidence lookup and let SQL safety gate reject if used"],
        )

    structured_hits = [kw for kw in STRUCTURED_METADATA_HINTS if kw in normalized or kw.lower() in lower]
    knowledge_hits = [kw for kw in KNOWLEDGE_KEYWORDS if kw in normalized or kw.lower() in lower]

    if structured_hits:
        reasons.append(f"structured metadata hints: {', '.join(structured_hits[:5])}")
    if knowledge_hits:
        reasons.append(f"knowledge keywords: {', '.join(knowledge_hits[:5])}")

    if re.search(r"(20\d{2})\s*年", normalized) and structured_hits:
        reasons.append("contains year plus structured-query wording")

    if structured_hits and not knowledge_hits:
        return RouteDecision(route="evidence_lookup", confidence=min(0.95, 0.65 + len(structured_hits) * 0.06), reasons=reasons)

    if structured_hits and knowledge_hits:
        structured_score = len(structured_hits)
        knowledge_score = len(knowledge_hits)
        if structured_score >= knowledge_score + 1:
            return RouteDecision(route="evidence_lookup", confidence=0.72, reasons=reasons)

    return RouteDecision(route="evidence_lookup", confidence=0.75 if knowledge_hits else 0.55, reasons=reasons or ["default to document RAG"])
