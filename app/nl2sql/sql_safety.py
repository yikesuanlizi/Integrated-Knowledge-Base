from __future__ import annotations

import re


FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|call|execute|merge|vacuum|analyze)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(sql: str) -> str:
    """Return a cleaned SQL string if it is a single read-only SELECT query."""
    cleaned = sql.strip()
    if not cleaned:
        raise ValueError("SQL 为空。")

    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise ValueError("SQL 中不允许包含注释。")

    statements = [part.strip() for part in cleaned.split(";") if part.strip()]
    if len(statements) != 1:
        raise ValueError("只允许执行一条 SQL 查询。")
    cleaned = statements[0]

    if FORBIDDEN_SQL.search(cleaned):
        raise ValueError("只允许只读 SELECT / WITH 查询，禁止 DDL/DML。")

    lowered = cleaned.lower().lstrip()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("SQL 必须以 SELECT 或 WITH 开头。")

    return cleaned


def with_limit(sql: str, limit: int) -> str:
    cleaned = validate_readonly_sql(sql)
    if re.search(r"\blimit\s+\d+\s*$", cleaned, re.IGNORECASE):
        return cleaned
    return f"SELECT * FROM ({cleaned}) AS nl2sql_limited_result LIMIT {int(limit)}"

