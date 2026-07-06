"""监控 API：查询历史、LLM 调用、节点耗时、聚合统计。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.log import logger
from app.services.monitor_service import (
    get_llm_call_detail,
    get_query_detail,
    get_stats,
    list_llm_calls,
    list_queries,
)

router = APIRouter(tags=["monitor"])


@router.get("/queries")
async def queries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """分页查询历史。"""
    try:
        return await list_queries(page=page, page_size=page_size)
    except Exception as e:
        logger.error(f"monitor queries failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list queries: {e}")


@router.get("/queries/{trace_id}")
async def query_detail(trace_id: str):
    """单次查询详情：trace + node 执行明细 + LLM 调用列表。"""
    try:
        result = await get_query_detail(trace_id)
        if not result:
            raise HTTPException(status_code=404, detail="Trace not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"monitor query detail failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get query detail: {e}")


@router.get("/llm-calls")
async def llm_calls(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    scene: str | None = None,
):
    """LLM 调用列表，支持 scene 过滤。"""
    try:
        return await list_llm_calls(page=page, page_size=page_size, scene=scene)
    except Exception as e:
        logger.error(f"monitor llm-calls failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list LLM calls: {e}")


@router.get("/llm-calls/{call_id}")
async def llm_call_detail(call_id: str):
    """单次 LLM 调用详情：完整 prompt + completion。"""
    try:
        result = await get_llm_call_detail(call_id)
        if not result:
            raise HTTPException(status_code=404, detail="LLM call not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"monitor llm-call detail failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get LLM call detail: {e}")


@router.get("/stats")
async def stats(hours: int = Query(24, ge=1, le=168)):
    """聚合统计。"""
    try:
        return await get_stats(hours=hours)
    except Exception as e:
        logger.error(f"monitor stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {e}")
