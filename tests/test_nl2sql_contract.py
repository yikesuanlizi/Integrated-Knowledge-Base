import pytest

from app.models.schemas import QueryResponse


def test_structured_signal_stays_inside_evidence_lookup_route():
    from app.nl2sql.routing import classify_query_route

    decision = classify_query_route("统计 2025 年 1 月各维修基地停场小时排名")

    assert decision.route == "evidence_lookup"
    assert decision.confidence >= 0.7


def test_readonly_sql_validator_rejects_destructive_sql():
    from app.nl2sql.sql_safety import validate_readonly_sql

    with pytest.raises(ValueError):
        validate_readonly_sql("DELETE FROM wiki_cards")


def test_query_response_accepts_sql_payload_in_integrated_mode():
    response = QueryResponse(
        question="哪些字段控制 Wiki 卡片审核状态",
        answer="已生成结构化元数据 SQL，并结合知识库证据返回结果。",
        needs_clarification=False,
        clarification_questions=[],
        citations=[],
        mode="mixed",
        sql_result={
            "sql": "SELECT kind, name, description FROM nl2sql_metric_info",
            "columns": ["kind", "name", "description"],
            "rows": [{"kind": "metric", "name": "待审核卡片数", "description": "知识库治理指标口径"}],
        },
    )

    assert response.mode == "mixed"
    assert response.sql_result["columns"] == ["kind", "name", "description"]
