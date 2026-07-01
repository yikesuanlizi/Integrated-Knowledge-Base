"""评测服务：封装 eval API 的业务逻辑。"""
from __future__ import annotations

from typing import List, Literal, Optional

from app.core.log import logger
from app.eval.runner import run_eval, run_full_eval
from app.models.schemas import EvalResult


class EvalService:
    """评测服务，封装健康度、引用覆盖率、检索精度、证据完整度等评测逻辑。"""

    async def run(
        self,
        kind: Literal["health", "citation", "retrieval", "evidence", "full"],
        build_id: Optional[str] = None,
        test_queries: Optional[List[str]] = None,
    ) -> EvalResult:
        """执行指定类型的评测。

        Args:
            kind: 评测类型，可选 health/citation/retrieval/evidence/full。
            build_id: 可选的 build ID。
            test_queries: 可选的测试查询列表。

        Returns:
            EvalResult 评测结果。
        """
        try:
            report = await run_eval(kind, build_id, test_queries)
            return report.to_schema()
        except Exception as e:
            logger.error(f"Eval run failed: {e}", exc_info=True)
            return EvalResult(
                build_id=build_id or "",
                health_score=0.0,
                citation_coverage=0.0,
                retrieval_precision=0.0,
                evidence_completeness=0.0,
                report=f"评测执行失败: {e}",
            )

    async def run_full(
        self,
        build_id: Optional[str] = None,
        test_queries: Optional[List[str]] = None,
    ) -> EvalResult:
        """执行完整评测（health + citation + retrieval + evidence）。

        Args:
            build_id: 可选的 build ID。
            test_queries: 可选的测试查询列表。

        Returns:
            EvalResult 评测结果。
        """
        try:
            report = await run_full_eval(build_id, test_queries)
            return report.to_schema()
        except Exception as e:
            logger.error(f"Full eval run failed: {e}", exc_info=True)
            return EvalResult(
                build_id=build_id or "",
                health_score=0.0,
                citation_coverage=0.0,
                retrieval_precision=0.0,
                evidence_completeness=0.0,
                report=f"完整评测执行失败: {e}",
            )
