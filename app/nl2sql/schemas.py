from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RouteName = Literal["evidence_lookup", "data_query"]


class RouteDecision(BaseModel):
    route: RouteName
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class NL2SQLQueryRequest(BaseModel):
    question: str
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class SQLResult(BaseModel):
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False


class NL2SQLQueryResponse(BaseModel):
    question: str
    mode: Literal["data_query"] = "data_query"
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    explanation: str
    trace: dict[str, Any] = Field(default_factory=dict)


class NL2SQLSeedResponse(BaseModel):
    status: str
    tables: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, int] = Field(default_factory=dict)
    indexes: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class NL2SQLStatusResponse(BaseModel):
    seeded: bool
    tables: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, int] = Field(default_factory=dict)
    indexes: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

