"""Structured metadata SQL API for the knowledge base."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.log import logger
from app.nl2sql.schemas import NL2SQLQueryRequest
from app.nl2sql.service import NL2SQLService

router = APIRouter(tags=["nl2sql"])


@router.post("/seed")
async def seed_nl2sql():
    service = NL2SQLService()
    try:
        return await service.seed()
    except Exception as exc:
        logger.error(f"NL2SQL seed failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"NL2SQL seed failed: {exc}") from exc


@router.get("/status")
async def nl2sql_status():
    service = NL2SQLService()
    return await service.status()


@router.post("/query")
async def query_nl2sql(request: NL2SQLQueryRequest):
    service = NL2SQLService()
    try:
        return await service.query(request.question, limit=request.limit, dry_run=request.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"NL2SQL query failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"NL2SQL query failed: {exc}") from exc


@router.post("/stream")
async def stream_nl2sql(request: NL2SQLQueryRequest):
    async def generate():
        service = NL2SQLService()
        try:
            yield _event("progress", {"node": "start", "message": "开始解析知识库结构化元数据检索"})
            result = await service.query(request.question, limit=request.limit, dry_run=request.dry_run)
            for step in result.trace.get("steps", []):
                yield _event("progress", step)
            yield _event("sql", {"sql": result.sql})
            yield _event("result", {"columns": result.columns, "rows": result.rows, "row_count": result.row_count})
            yield _event("explanation", {"text": result.explanation})
            yield _event("done", result.model_dump())
        except Exception as exc:
            logger.error(f"NL2SQL stream failed: {exc}", exc_info=True)
            yield _event("error", {"error": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
