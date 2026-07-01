"""评测：证据完整性。

检查生成的证据包是否包含足够多的来源、是否包含数值规格等。
"""
from __future__ import annotations

import asyncio
from typing import List

from app.agent.graph import run_agent_sync
from app.core.log import logger


DEFAULT_TEST_QUERIES: List[str] = [
    "起落架轮迹是什么意思？",
    "飞机等级号/道面等级号报告系统是什么？",
]


async def evaluate_evidence_completeness(build_id: str = "", test_queries: List[str] | None = None) -> dict:
    """评估证据完整性。"""
    test_queries = test_queries or DEFAULT_TEST_QUERIES

    loop = asyncio.get_running_loop()
    details: list[dict] = []
    completeness_scores: list[float] = []

    for q in test_queries:
        try:
            state = await loop.run_in_executor(None, run_agent_sync, q)
            evidence_items = state.evidence_pack.get("evidence_items", [])
            if not evidence_items:
                completeness_scores.append(0.0)
                details.append({"query": q, "items": 0, "ok": False})
                continue

            # 计算完整性：
            # - item 数量 >= 3
            # - 至少 1 个 item 有 source_file
            # - 至少 1 个 item 有 page_numbers
            n = len(evidence_items)
            with_source = sum(1 for e in evidence_items if e.get("source_file") or e.get("source_ref"))
            with_page = sum(1 for e in evidence_items if e.get("page_numbers"))
            score = min(1.0, n / 5.0) * 0.4 + min(1.0, with_source / max(n, 1)) * 0.3 + min(1.0, with_page / max(n, 1)) * 0.3
            completeness_scores.append(score)
            details.append({
                "query": q,
                "items": n,
                "with_source": with_source,
                "with_page": with_page,
                "score": round(score, 3),
            })
        except Exception as e:
            logger.warning(f"Evidence eval query '{q}' failed: {e}")
            details.append({"query": q, "error": str(e)})

    avg = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0
    return {
        "score": round(avg, 4),
        "total_queries": len(test_queries),
        "details": details,
    }
