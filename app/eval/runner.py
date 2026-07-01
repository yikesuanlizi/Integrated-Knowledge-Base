"""评测运行器：统一执行 health / citation / retrieval / evidence / full 五类评测。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal

from app.eval import citation_eval, evidence_eval, health_eval, retrieval_eval
from app.eval.queryset import load_eval_queries
from app.models.schemas import EvalResult
from app.retrieval.es_repo import ElasticsearchRepository
from app.retrieval.milvus_repo import MilvusRepository
from app.services.wiki_pg_service import count_pg_rows


@dataclass
class EvalReport:
    build_id: str
    health_score: float
    citation_coverage: float
    retrieval_precision: float
    evidence_completeness: float
    # 综合分 = 四项加权几何平均
    overall_score: float
    # 各子项详情（原始输出）
    health_detail: dict = field(default_factory=dict)
    citation_detail: dict = field(default_factory=dict)
    retrieval_detail: dict = field(default_factory=dict)
    evidence_detail: dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_schema(self) -> EvalResult:
        return EvalResult(
            build_id=self.build_id,
            health_score=self.overall_score,
            citation_coverage=self.citation_coverage,
            retrieval_precision=self.retrieval_precision,
            evidence_completeness=self.evidence_completeness,
            report=self.summary_text(),
        )

    def summary_text(self) -> str:
        return f"""## 评测报告
- 健康分: {self.health_score:.2%}
- 引用覆盖率: {self.citation_coverage:.2%}
- 检索精度: {self.retrieval_precision:.2%}
- 证据完整度: {self.evidence_completeness:.2%}
- 综合分: {self.overall_score:.2%}
- 错误: {len(self.errors)} 项
"""


async def run_eval(
    kind: Literal["health", "citation", "retrieval", "evidence", "full"],
    build_id: str = "",
    test_queries: Optional[List[str]] = None,
) -> EvalReport:
    """根据 kind 决定评测范围。

    - health: 只跑健康度（用传入的 chunk/card/es 数量）
    - citation: 只跑引用覆盖率
    - retrieval: 只跑检索精度
    - evidence: 只跑证据完整性
    - full: 四个全跑，然后聚合
    """
    timestamp = datetime.now().isoformat()
    errors: List[str] = []
    health_detail: dict = {}
    citation_detail: dict = {}
    retrieval_detail: dict = {}
    evidence_detail: dict = {}
    health_score = 0.0
    citation_coverage = 0.0
    retrieval_precision = 0.0
    evidence_completeness = 0.0

    effective_queries = test_queries
    if kind in {"citation", "evidence", "full"} and not effective_queries:
        effective_queries = await load_eval_queries(build_id, limit=5, fallback=citation_eval.TEST_QUERIES)

    if kind == "health":
        try:
            milvus_repo = MilvusRepository()
            es_repo = ElasticsearchRepository()
            chunk_count = milvus_repo.count()
        except Exception as e:
            errors.append(f"Milvus chunk count failed: {e}")
            chunk_count = 0
        try:
            card_count = await count_pg_rows("wiki_cards", "status = 'approved'")
        except Exception as e:
            errors.append(f"Wiki card count failed: {e}")
            card_count = 0
        try:
            es_count = await es_repo.count()
        except Exception as e:
            errors.append(f"Elasticsearch count failed: {e}")
            es_count = 0
        health_detail = health_eval.evaluate_health(chunk_count, card_count, es_count)
        health_score = health_detail.get("score", 0.0)
        overall_score = health_score

    elif kind == "citation":
        try:
            citation_detail = await citation_eval.evaluate_citation_coverage(build_id, effective_queries)
            citation_coverage = citation_detail.get("score", 0.0)
        except Exception as e:
            errors.append(f"Citation eval failed: {e}")
        overall_score = citation_coverage

    elif kind == "retrieval":
        try:
            retrieval_detail = await retrieval_eval.evaluate_retrieval_precision(build_id)
            retrieval_precision = retrieval_detail.get("score", 0.0)
        except Exception as e:
            errors.append(f"Retrieval eval failed: {e}")
        overall_score = retrieval_precision

    elif kind == "evidence":
        try:
            evidence_detail = await evidence_eval.evaluate_evidence_completeness(build_id, effective_queries)
            evidence_completeness = evidence_detail.get("score", 0.0)
        except Exception as e:
            errors.append(f"Evidence eval failed: {e}")
        overall_score = evidence_completeness

    elif kind == "full":
        # 并发执行四个子项
        async def run_health() -> dict:
            try:
                milvus_repo = MilvusRepository()
                es_repo = ElasticsearchRepository()
                chunk_count = milvus_repo.count()
            except Exception as e:
                errors.append(f"Milvus chunk count failed: {e}")
                chunk_count = 0
            try:
                card_count = await count_pg_rows("wiki_cards", "status = 'approved'")
            except Exception as e:
                errors.append(f"Wiki card count failed: {e}")
                card_count = 0
            try:
                es_count = await es_repo.count()
            except Exception as e:
                errors.append(f"Elasticsearch count failed: {e}")
                es_count = 0
            return health_eval.evaluate_health(chunk_count, card_count, es_count)

        async def run_citation() -> dict:
            try:
                return await citation_eval.evaluate_citation_coverage(build_id, effective_queries)
            except Exception as e:
                errors.append(f"Citation eval failed: {e}")
                return {"score": 0.0}

        async def run_retrieval() -> dict:
            try:
                return await retrieval_eval.evaluate_retrieval_precision(build_id)
            except Exception as e:
                errors.append(f"Retrieval eval failed: {e}")
                return {"score": 0.0}

        async def run_evidence() -> dict:
            try:
                return await evidence_eval.evaluate_evidence_completeness(build_id, effective_queries)
            except Exception as e:
                errors.append(f"Evidence eval failed: {e}")
                return {"score": 0.0}

        health_r, citation_r, retrieval_r, evidence_r = await asyncio.gather(
            run_health(), run_citation(), run_retrieval(), run_evidence()
        )

        health_detail = health_r
        citation_detail = citation_r
        retrieval_detail = retrieval_r
        evidence_detail = evidence_r

        health_score = health_detail.get("score", 0.0)
        citation_coverage = citation_detail.get("score", 0.0)
        retrieval_precision = retrieval_detail.get("score", 0.0)
        evidence_completeness = evidence_detail.get("score", 0.0)

        # 几何平均
        overall_score = (health_score * citation_coverage * retrieval_precision * evidence_completeness) ** 0.25

    return EvalReport(
        build_id=build_id,
        health_score=health_score,
        citation_coverage=citation_coverage,
        retrieval_precision=retrieval_precision,
        evidence_completeness=evidence_completeness,
        overall_score=overall_score,
        health_detail=health_detail,
        citation_detail=citation_detail,
        retrieval_detail=retrieval_detail,
        evidence_detail=evidence_detail,
        errors=errors,
        timestamp=timestamp,
    )


async def run_full_eval(build_id: str = "", test_queries: Optional[List[str]] = None) -> EvalReport:
    """完整评测：health + citation + retrieval + evidence。"""
    return await run_eval("full", build_id, test_queries)
