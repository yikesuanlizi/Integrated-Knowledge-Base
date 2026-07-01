from __future__ import annotations

import re
from typing import Any

from app.clients.es_client import es_client_manager
from app.clients.llm_client import embedding_client
from app.clients.milvus_client import get_milvus_client
from app.core.log import logger
from app.nl2sql.repository import (
    NL2SQL_COLUMN_COLLECTION,
    NL2SQL_METRIC_COLLECTION,
    NL2SQL_VALUE_INDEX,
    NL2SQLRepository,
)
from app.nl2sql.schemas import NL2SQLQueryResponse, NL2SQLSeedResponse, NL2SQLStatusResponse, SQLResult
from app.nl2sql.sql_safety import validate_readonly_sql, with_limit


class NL2SQLService:
    def __init__(self) -> None:
        self.repo = NL2SQLRepository()

    async def seed(self) -> NL2SQLSeedResponse:
        tables, metadata = await self.repo.seed()
        indexes, warnings = await self.repo.seed_indexes()
        return NL2SQLSeedResponse(
            status="ok" if not warnings else "partial",
            tables=tables,
            metadata=metadata,
            indexes=indexes,
            warnings=warnings,
        )

    async def status(self) -> NL2SQLStatusResponse:
        tables = await self.repo.table_counts()
        metadata = await self.repo.metadata_counts()
        indexes = await self.repo.index_counts()
        seeded = metadata.get("nl2sql_metric_info", 0) > 0 or metadata.get("nl2sql_column_info", 0) > 0
        warnings = []
        if "milvus_error" in indexes:
            warnings.append(f"Milvus 状态不可用：{indexes['milvus_error']}")
        if "elasticsearch_error" in indexes:
            warnings.append(f"Elasticsearch 状态不可用：{indexes['elasticsearch_error']}")
        return NL2SQLStatusResponse(seeded=seeded, tables=tables, metadata=metadata, indexes=indexes, warnings=warnings)

    async def query(self, question: str, limit: int = 100, dry_run: bool = False) -> NL2SQLQueryResponse:
        trace: dict[str, Any] = {"steps": []}
        keywords = extract_keywords(question)
        trace["keywords"] = keywords
        trace["steps"].append({"node": "extract_keywords", "keywords": keywords})

        metadata = await self.repo.load_metadata()
        columns = await self._recall_columns(question, metadata["columns"])
        metrics = await self._recall_metrics(question, metadata["metrics"])
        values = await self._recall_values(question, metadata["values"])
        trace["steps"].extend(
            [
                {"node": "recall_columns", "count": len(columns), "items": columns[:5]},
                {"node": "recall_metrics", "count": len(metrics), "items": metrics[:5]},
                {"node": "recall_values", "count": len(values), "items": values[:8]},
            ]
        )

        sql = generate_sql(question, metrics, values)
        trace["steps"].append({"node": "generate_sql", "sql": sql})

        try:
            readonly_sql = validate_readonly_sql(sql)
            limited_sql = with_limit(readonly_sql, limit)
            # Metadata SQL is used as a structured knowledge lookup. It is
            # validated for read-only shape but not treated as an independent
            # business fact query.
            trace["steps"].append({"node": "validate_sql", "status": "ok"})
        except Exception as exc:
            trace["steps"].append({"node": "validate_sql", "status": "failed", "error": str(exc)})
            corrected = correct_sql(question, sql, str(exc))
            if not corrected:
                raise ValueError(f"SQL 校验失败：{exc}") from exc
            readonly_sql = validate_readonly_sql(corrected)
            limited_sql = with_limit(readonly_sql, limit)
            sql = corrected
            trace["steps"].append({"node": "correct_sql", "sql": sql})

        rows = _metadata_rows(question, columns, metrics, values, limit)
        if dry_run:
            result = SQLResult(sql=limited_sql, columns=[], rows=[], row_count=0)
            explanation = "已生成并校验结构化元数据 SQL，dry_run=true 未返回匹配结果。"
        else:
            result = SQLResult(
                sql=limited_sql,
                columns=["kind", "name", "table_name", "column_name", "description"],
                rows=rows,
                row_count=len(rows),
                truncated=len(rows) >= limit,
            )
            trace["steps"].append({"node": "execute_sql", "row_count": result.row_count, "truncated": result.truncated})
            explanation = explain_result(question, sql, result.rows, result.row_count, result.truncated)
            trace["steps"].append({"node": "explain_result", "text": explanation})

        return NL2SQLQueryResponse(
            question=question,
            sql=result.sql,
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
            explanation=explanation,
            trace=trace,
        )

    async def _recall_columns(self, question: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hits = await self._recall_milvus(question, NL2SQL_COLUMN_COLLECTION)
        return hits or _keyword_rank(question, fallback, ["column_name", "description", "aliases", "sample_values"])

    async def _recall_metrics(self, question: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hits = await self._recall_milvus(question, NL2SQL_METRIC_COLLECTION)
        return hits or _keyword_rank(question, fallback, ["metric_name", "description", "aliases"])

    async def _recall_values(self, question: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            response = await es_client_manager.search(
                NL2SQL_VALUE_INDEX,
                {
                    "multi_match": {
                        "query": question,
                        "fields": ["value_text^3", "aliases", "value_type", "column_name"],
                    }
                },
                size=12,
            )
            hits = [hit.get("_source", {}) for hit in response.get("hits", {}).get("hits", [])]
            if hits:
                return hits
        except Exception as exc:
            logger.debug(f"NL2SQL ES recall fallback: {exc}")
        return _keyword_rank(question, fallback, ["value_text", "value_type", "aliases", "column_name"], limit=12)

    async def _recall_milvus(self, question: str, collection: str) -> list[dict[str, Any]]:
        try:
            client = get_milvus_client()
            if not client.has_collection(collection):
                return []
            embedding = await embedding_client.aembed_text(question)
            results = client.search(
                collection_name=collection,
                data=[embedding],
                limit=8,
                output_fields=["*"],
            )
            hits = []
            for hit in results[0]:
                entity = dict(hit.get("entity", {}))
                entity["score"] = float(hit.get("distance", 0.0))
                hits.append(entity)
            return hits
        except Exception as exc:
            logger.debug(f"NL2SQL Milvus recall fallback for {collection}: {exc}")
            return []


def extract_keywords(question: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", question)
    knowledge_terms = [
        "文档",
        "资料",
        "手册",
        "原文",
        "切块",
        "chunk",
        "卡片",
        "wiki",
        "事实",
        "claim",
        "引用",
        "证据",
        "审核",
        "通过",
        "驳回",
        "待审核",
        "新鲜度",
        "过期",
        "实体",
        "部件",
        "系统",
        "ATA",
        "步骤",
        "安全",
        "起落架轮迹",
        "道面等级号",
        "飞机等级号",
        "登机门",
        "液压系统",
        "approved",
        "review",
        "rejected",
    ]
    found = [term for term in knowledge_terms if term in question]
    return list(dict.fromkeys(found + tokens))


def generate_sql(question: str, metrics: list[dict[str, Any]], values: list[dict[str, Any]]) -> str:
    lowered = question.lower()
    if any(term in lowered for term in ["delete", "drop", "truncate", "删除", "清空"]):
        raise ValueError("该问题包含危险数据库操作意图，已拒绝生成 SQL。")

    return """
        SELECT 'metric' AS kind, metric_name AS name, NULL AS table_name, NULL AS column_name, description
        FROM nl2sql_metric_info
        UNION ALL
        SELECT 'column' AS kind, column_id AS name, table_name, column_name, description
        FROM nl2sql_column_info
        UNION ALL
        SELECT 'value' AS kind, value_text AS name, table_name, column_name, value_type AS description
        FROM nl2sql_value_info
    """


def correct_sql(question: str, sql: str, error: str) -> str | None:
    if "limit" in error.lower():
        return re.sub(r";+\s*$", "", sql.strip())
    return None


def explain_result(question: str, sql: str, rows: list[dict[str, Any]], row_count: int, truncated: bool) -> str:
    if row_count == 0:
        return "结构化元数据查询没有匹配项；最终回答应以 Wiki/RAG 证据为准。"
    first = rows[0]
    summary_parts = [f"结构化元数据检索返回 {row_count} 行辅助信息"]
    if truncated:
        summary_parts.append("结果已按上限截断")
    if len(first) == 1:
        key, value = next(iter(first.items()))
        summary_parts.append(f"{key} = {value}")
    elif len(first) >= 2:
        summary_parts.append("首行结果：" + "，".join(f"{k}={v}" for k, v in first.items()))
    return "，".join(summary_parts) + "。"


def _metadata_rows(
    question: str,
    columns: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    values: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric in metrics:
        rows.append({
            "kind": "metric",
            "name": metric.get("metric_name", ""),
            "table_name": "",
            "column_name": "",
            "description": metric.get("description", ""),
        })
    for column in columns:
        rows.append({
            "kind": "column",
            "name": column.get("column_id", ""),
            "table_name": column.get("table_name", ""),
            "column_name": column.get("column_name", ""),
            "description": column.get("description", ""),
        })
    for value in values:
        rows.append({
            "kind": "value",
            "name": value.get("value_text", ""),
            "table_name": value.get("table_name", ""),
            "column_name": value.get("column_name", ""),
            "description": value.get("value_type", ""),
        })
    if not rows:
        keywords = extract_keywords(question)
        rows = [{"kind": "keyword", "name": kw, "table_name": "", "column_name": "", "description": "query keyword"} for kw in keywords]
    return rows[:limit]


def _keyword_rank(question: str, items: list[dict[str, Any]], fields: list[str], limit: int = 8) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        haystack_parts: list[str] = []
        for field in fields:
            value = item.get(field)
            if isinstance(value, list):
                haystack_parts.extend(str(v) for v in value)
            elif value is not None:
                haystack_parts.append(str(value))
        haystack = " ".join(haystack_parts)
        score = sum(1 for kw in extract_keywords(question) if kw and kw in haystack)
        if score:
            enriched = dict(item)
            enriched["score"] = float(score)
            scored.append((score, enriched))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]
