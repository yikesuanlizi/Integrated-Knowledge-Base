"""评测：引用覆盖率。

通过运行一批测试 query，检查答案是否带引用。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import List

from app.agent.graph import run_agent_sync
from app.core.log import logger


# 标准测试 query 集（可扩展）
TEST_QUERIES: List[str] = [
    "起落架轮迹是什么意思？",
    "What is the landing gear wheel track?",
    "飞机等级号/道面等级号报告系统是什么？",
    "登机门是什么？",
    "平尾后部离地高度是什么意思？",
]


async def evaluate_citation_coverage(build_id: str = "", test_queries: List[str] = None) -> dict:
    """评估答案的引用覆盖率。"""
    queries = test_queries or TEST_QUERIES
    if not queries:
        return {"score": 0.0, "total_queries": 0, "with_citation": 0}

    total = len(queries)
    with_citation = 0
    details: list[dict] = []

    loop = asyncio.get_running_loop()
    for q in queries:
        try:
            state = await loop.run_in_executor(None, run_agent_sync, q)
            citations = state.citations or []
            answer = state.answer or ""
            # 检查 answer 是否带 [1] [2] 这样的引用标记
            has_inline_citation = "[" in answer and "]" in answer
            ok = bool(citations) and has_inline_citation
            if ok:
                with_citation += 1
            # 收集 retrieval_trace 信息
            trace_keys = []
            if state.retrieval_trace is not None:
                trace_keys = list(state.retrieval_trace.model_dump().keys())
            details.append({
                "query": q,
                "citation_count": len(citations),
                "has_inline_citation": has_inline_citation,
                "ok": ok,
                "trace_keys": trace_keys,
            })
        except Exception as e:
            logger.warning(f"Citation eval query '{q}' failed: {e}")
            details.append({"query": q, "error": str(e), "ok": False})

    score = with_citation / total
    return {
        "score": round(score, 4),
        "total_queries": total,
        "with_citation": with_citation,
        "details": details,
    }
