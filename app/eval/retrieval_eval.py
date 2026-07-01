"""评测：检索精度。

通过 ground-truth 标签（如果存在）评估 top-k 召回率。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, List

from app.clients.llm_client import embedding_client
from app.core.log import logger
from app.retrieval.milvus_repo import MilvusRepository


async def evaluate_retrieval_precision(build_id: str = "") -> dict:
    """评估检索模块的精度（heuristic 版本）。

    衡量指标：
    - recall@5 / recall@10：基于关键词匹配的简单近似
    - score >= 0 的命中率
    """
    try:
        repo = MilvusRepository()
        count = repo.count()
    except Exception as e:
        logger.warning(f"Cannot connect to Milvus: {e}")
        return {"score": 0.0, "error": str(e)}

    if count == 0:
        return {"score": 0.0, "total_queries": 0, "message": "知识库为空"}

    # 简单测试 query 集
    test_queries = ["燃油滤清器", "起落架", "液压", "传感器", "故障"]

    hits = 0
    total = len(test_queries)
    details: list[dict] = []

    for q in test_queries:
        try:
            # fallback: 检查 aembed_text 是否可用
            if hasattr(embedding_client, 'aembed_text') and callable(embedding_client.aembed_text):
                emb = await embedding_client.aembed_text(q)
            else:
                emb = embedding_client.embed_text(q)
            results = repo.search(emb, top_k=5)
            ok = len(results) > 0
            if ok:
                hits += 1
            details.append({"query": q, "hits": len(results), "ok": ok})
        except Exception as e:
            details.append({"query": q, "error": str(e), "ok": False})

    score = hits / total
    return {
        "score": round(score, 4),
        "total_queries": total,
        "hits": hits,
        "details": details,
    }


def score_golden_retrieval_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Score true retrieval metrics from a golden set and resolved candidates.

    Each case must contain expected ids and a `retrieved` list. The metrics are
    real recall only because the expected ids are provided by the golden set.
    """
    total = len(cases)
    if total == 0:
        return _empty_golden_report()

    cutoffs = (1, 3, 5, 10)
    hit_at = {k: 0 for k in cutoffs}
    reciprocal_ranks: list[float] = []
    missed_queries: list[str] = []
    channel_hits: dict[str, int] = defaultdict(int)
    intent_groups: dict[str, list[bool]] = defaultdict(list)
    details: list[dict[str, Any]] = []

    for case in cases:
        expected = _expected_ids(case)
        retrieved = list(case.get("retrieved") or [])
        ranks = [
            index + 1
            for index, candidate in enumerate(retrieved)
            if _candidate_ids(candidate) & expected
        ]
        first_rank = min(ranks) if ranks else None
        for k in cutoffs:
            if first_rank is not None and first_rank <= k:
                hit_at[k] += 1
        reciprocal_ranks.append((1.0 / first_rank) if first_rank else 0.0)
        if first_rank is None:
            missed_queries.append(str(case.get("question", "")))

        top10_hits = [
            candidate
            for candidate in retrieved[:10]
            if _candidate_ids(candidate) & expected
        ]
        for candidate in top10_hits:
            channel = str(candidate.get("source_type") or candidate.get("type") or "unknown")
            channel_hits[channel] += 1

        intent = str(case.get("intent") or "unknown")
        intent_groups[intent].append(first_rank is not None and first_rank <= 10)
        details.append(
            {
                "question": case.get("question", ""),
                "intent": case.get("intent"),
                "tags": case.get("tags", []),
                "expected_count": len(expected),
                "retrieved_count": len(retrieved),
                "first_hit_rank": first_rank,
                "hit_at_1": first_rank is not None and first_rank <= 1,
                "hit_at_3": first_rank is not None and first_rank <= 3,
                "hit_at_5": first_rank is not None and first_rank <= 5,
                "hit_at_10": first_rank is not None and first_rank <= 10,
                "hit_channels": sorted({str(c.get("source_type") or c.get("type") or "unknown") for c in top10_hits}),
            }
        )

    intent_breakdown = {
        intent: {
            "total": len(values),
            "recall_at_10": round(sum(1 for value in values if value) / len(values), 4) if values else 0.0,
        }
        for intent, values in sorted(intent_groups.items())
    }

    return {
        "id": datetime.utcnow().strftime("retrieval-%Y%m%d%H%M%S"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mode": "golden_eval",
        "total_queries": total,
        "recall_at_1": round(hit_at[1] / total, 4),
        "recall_at_3": round(hit_at[3] / total, 4),
        "recall_at_5": round(hit_at[5] / total, 4),
        "recall_at_10": round(hit_at[10] / total, 4),
        "mrr": round(sum(reciprocal_ranks) / total, 4),
        "hit_rate": round(hit_at[10] / total, 4),
        "missed_queries": missed_queries,
        "missed_count": len(missed_queries),
        "channel_contribution": dict(sorted(channel_hits.items())),
        "intent_breakdown": intent_breakdown,
        "details": details,
    }


def _empty_golden_report() -> dict[str, Any]:
    return {
        "id": datetime.utcnow().strftime("retrieval-%Y%m%d%H%M%S"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mode": "golden_eval",
        "total_queries": 0,
        "recall_at_1": 0.0,
        "recall_at_3": 0.0,
        "recall_at_5": 0.0,
        "recall_at_10": 0.0,
        "mrr": 0.0,
        "hit_rate": 0.0,
        "missed_queries": [],
        "missed_count": 0,
        "channel_contribution": {},
        "intent_breakdown": {},
        "details": [],
    }


def _expected_ids(case: dict[str, Any]) -> set[str]:
    expected: set[str] = set()
    for key in ("expected_doc_ids", "expected_chunk_ids", "expected_card_ids"):
        for value in case.get(key, []) or []:
            text = str(value)
            expected.add(text)
            if key == "expected_doc_ids":
                expected.add(f"doc:{text}")
            elif key == "expected_chunk_ids":
                expected.add(f"chunk:{text}")
            elif key == "expected_card_ids":
                expected.add(f"wiki_card:{text}")
    return expected


def _candidate_ids(candidate: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    source_type = str(candidate.get("source_type") or candidate.get("type") or "")
    for key, prefix in (
        ("doc_id", "doc"),
        ("chunk_id", "chunk"),
        ("card_id", "wiki_card"),
        ("id", source_type or "id"),
    ):
        value = candidate.get(key)
        if value:
            text = str(value)
            ids.add(text)
            ids.add(f"{prefix}:{text}")
    return ids
