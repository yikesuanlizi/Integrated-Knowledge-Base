"""知识库评测 API。"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.graph import run_agent_sync
from app.core.log import logger
from app.eval.citation_eval import TEST_QUERIES as CITATION_TEST_QUERIES, evaluate_citation_coverage
from app.eval.fixtures import load_eval_fixtures
from app.eval.evidence_eval import evaluate_evidence_completeness
from app.eval.health_eval import evaluate_health
from app.eval.queryset import load_eval_queries
from app.eval.retrieval_eval import evaluate_retrieval_precision, score_golden_retrieval_cases
from app.eval.runner import run_full_eval
from app.retrieval.es_repo import ElasticsearchRepository
from app.retrieval.milvus_repo import MilvusRepository
from app.services.wiki_pg_service import count_pg_rows

router = APIRouter(tags=["eval"])
REPORTS_PATH = Path("logs") / "retrieval_eval_reports.json"


class EvalRequest(BaseModel):
    build_id: str = ""


class GoldenRetrievalCase(BaseModel):
    question: str
    expected_doc_ids: list[str] = []
    expected_chunk_ids: list[str] = []
    expected_card_ids: list[str] = []
    intent: str | None = None
    tags: list[str] = []


class GoldenRetrievalRunRequest(BaseModel):
    cases: list[GoldenRetrievalCase]
    top_k: int = 10


@router.get("/fixtures")
async def eval_fixtures(build_id: str = ""):
    """Return the fixed eval questions and resolved golden cases for the current corpus."""
    try:
        return await load_eval_fixtures(build_id)
    except Exception as e:
        logger.error(f"Load eval fixtures failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/health")
async def eval_health(request: EvalRequest):
    """健康度评估：统计 chunk / wiki / 索引数据量。"""
    milvus_repo = MilvusRepository()
    es_repo = ElasticsearchRepository()

    try:
        chunk_count = milvus_repo.count()
    except Exception:
        chunk_count = 0

    try:
        card_count = await count_pg_rows("wiki_cards", "status = 'approved'")
    except Exception:
        card_count = 0

    try:
        es_count = await es_repo.count()
    except Exception:
        es_count = 0

    return evaluate_health(
        chunk_count=chunk_count,
        card_count=card_count,
        es_count=es_count,
    )


@router.post("/citation")
async def eval_citation(request: EvalRequest):
    """引用覆盖率评估（用历史 query 集合）。"""
    try:
        queries = await load_eval_queries(request.build_id, limit=5, fallback=CITATION_TEST_QUERIES)
        result = await evaluate_citation_coverage(request.build_id, queries)
        result["query_source"] = "corpus" if queries and queries != CITATION_TEST_QUERIES else "fallback"
        result["queries"] = queries
        return result
    except Exception as e:
        logger.error(f"Citation eval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieval")
async def eval_retrieval(request: EvalRequest):
    """检索精度评估。"""
    try:
        return await evaluate_retrieval_precision(request.build_id)
    except Exception as e:
        logger.error(f"Retrieval eval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieval/run")
async def eval_retrieval_golden(request: GoldenRetrievalRunRequest):
    """Run true recall metrics against a golden set.

    This endpoint computes recall@k / MRR only from labeled cases. Production
    online traces remain observation metrics and are not called recall.
    """
    if not request.cases:
        raise HTTPException(status_code=400, detail="cases 不能为空")
    try:
        scored_cases: list[dict] = []
        for case in request.cases:
            state = run_agent_sync(case.question, top_k=max(1, min(request.top_k, 30)))
            scored_cases.append(
                {
                    **case.model_dump(),
                    "retrieved": state.reranked_results or state.merged_results or [],
                }
            )
        report = score_golden_retrieval_cases(scored_cases)
        _save_retrieval_report(report)
        return report
    except Exception as e:
        logger.error(f"Golden retrieval eval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/retrieval/report/latest")
async def eval_retrieval_latest_report():
    reports = _load_retrieval_reports()
    return reports[0] if reports else None


@router.get("/retrieval/reports")
async def eval_retrieval_reports():
    return {"reports": _load_retrieval_reports()}


@router.post("/evidence")
async def eval_evidence(request: EvalRequest):
    """证据完整性评估。"""
    try:
        queries = await load_eval_queries(request.build_id, limit=5)
        result = await evaluate_evidence_completeness(request.build_id, queries)
        result["query_source"] = "corpus" if queries else "fallback"
        result["queries"] = queries
        return result
    except Exception as e:
        logger.error(f"Evidence eval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full")
async def eval_full(request: EvalRequest):
    """综合评估：health + citation + retrieval + evidence（使用 runner 统一执行）。"""
    try:
        report = await run_full_eval(request.build_id)
        return {
            "build_id": report.build_id,
            "overall_score": report.overall_score,
            "health": report.health_detail,
            "citation": report.citation_detail,
            "retrieval": report.retrieval_detail,
            "evidence": report.evidence_detail,
            "timestamp": report.timestamp,
            "errors": report.errors,
        }
    except Exception as e:
        logger.error(f"Full eval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _load_retrieval_reports() -> list[dict]:
    if not REPORTS_PATH.exists():
        return []
    try:
        return json.loads(REPORTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_retrieval_report(report: dict) -> None:
    REPORTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    reports = [report] + _load_retrieval_reports()
    REPORTS_PATH.write_text(json.dumps(reports[:30], ensure_ascii=False, indent=2), encoding="utf-8")
