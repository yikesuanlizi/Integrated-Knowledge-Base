"""问答 API：LangGraph Agent 入口。"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import run_unified_query
from app.compiler.llm_utils import call_llm_json
from app.compiler.prompts import get_prompt
from app.core.log import logger
from app.models.schemas import QueryRequest, QueryResponse
from app.retrieval.intent import classify_intent, get_intent_config

router = APIRouter(tags=["query"])


@router.post("/")
async def query_knowledge(request: QueryRequest):
    """执行一次 Agent 问答。"""
    try:
        return await run_unified_query(request.question, top_k=request.top_k)
    except Exception as e:
        logger.error(f"Unified query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")


@router.post("/stream")
async def query_stream(request: QueryRequest):
    """SSE 流式问答。"""
    async def generate():
        try:
            # 先把 trace 信息以 event 形式发送
            intent = classify_intent(request.question)
            yield f"event: intent\ndata: {json.dumps(intent.model_dump(), ensure_ascii=False)}\n\n"

            config = get_intent_config(intent)
            yield f"event: config\ndata: {json.dumps(config, ensure_ascii=False)}\n\n"

            response = await run_unified_query(request.question, top_k=request.top_k)

            # 流式输出 answer：保留段落分隔，避免前端把整段压成一团
            answer = response.answer or ""
            chunks = re.split(r"(\n\n+)", answer)
            for chunk in chunks:
                if not chunk:
                    continue
                yield f"event: answer\ndata: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"

            # 结束：citations 元素可能是 Pydantic 模型，先统一转为 dict
            def _to_dict(x: Any) -> Any:
                if hasattr(x, "model_dump"):
                    return x.model_dump()
                return x
            citations_data = [_to_dict(c) for c in (response.citations or [])]
            trace_data = response.retrieval_trace.model_dump() if response.retrieval_trace else None
            yield f"event: done\ndata: {json.dumps({'citations': citations_data, 'trace': trace_data, 'mode': response.mode, 'sql_result': response.sql_result}, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.error(f"Stream query failed: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/intent")
async def classify_query_intent(request: QueryRequest):
    """仅做意图分类（轻量）。"""
    intent = classify_intent(request.question)
    config = get_intent_config(intent)
    return {
        "question": request.question,
        "intent": intent.model_dump(),
        "config": config,
    }


@router.post("/rewrite")
async def rewrite_query(request: QueryRequest):
    """LLM 改写查询。"""
    from app.retrieval.query_features import hybrid_rewrite_query
    try:
        variants = await hybrid_rewrite_query(request.question)
    except Exception as e:
        logger.warning(f"LLM rewrite failed: {e}")
        from app.retrieval.query_features import generate_query_variants
        variants = generate_query_variants(request.question)

    return {
        "question": request.question,
        "variants": variants,
    }
