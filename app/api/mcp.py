"""MCP (Model Context Protocol) 兼容 API。
MCP 工具注册表 + 工具调用分发。
"""
from __future__ import annotations

import json
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.graph import run_agent_sync
from app.core.log import logger
from app.retrieval.es_repo import ElasticsearchRepository, WikiCardESRepository
from app.retrieval.milvus_repo import MilvusRepository

router = APIRouter(tags=["mcp"])


class MCPToolInputSchema(BaseModel):
    """MCP 工具输入 schema。"""
    pass


class MCPTool(BaseModel):
    name: str
    description: str
    input_schema: dict


class MCPToolCallRequest(BaseModel):
    tool: str
    arguments: dict = {}


# MCP 返回格式包装
def _mcp_result(content: str | dict | list) -> dict:
    """把任意结果包装成 MCP 协议格式 {content: [{type, text}]}。"""
    if isinstance(content, str):
        text = content
    else:
        text = json.dumps(content, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


# 工具注册表
MCP_TOOLS: List[MCPTool] = [
    MCPTool(
        name="query",
        description="基于知识库的智能问答，返回答案和引用",
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "用户问题"},
                "top_k": {"type": "integer", "description": "召回数量", "default": 8},
            },
            "required": ["question"],
        },
    ),
    MCPTool(
        name="search_wiki",
        description="全文搜索 Wiki 知识卡片",
        input_schema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"},
                "top_k": {"type": "integer", "description": "返回数量", "default": 5},
                "card_type": {"type": "string", "description": "按卡片类型过滤"},
            },
            "required": ["keyword"],
        },
    ),
    MCPTool(
        name="get_wiki_card",
        description="获取单张 Wiki 卡片详情",
        input_schema={
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "卡片 ID"},
            },
            "required": ["card_id"],
        },
    ),
    MCPTool(
        name="list_wiki_cards",
        description="分页列出 Wiki 卡片",
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "页码", "default": 1},
                "page_size": {"type": "integer", "description": "每页数量", "default": 20},
                "card_type": {"type": "string", "description": "按类型过滤"},
                "status": {"type": "string", "description": "按状态过滤"},
            },
        },
    ),
    MCPTool(
        name="health",
        description="系统健康检查和存储统计",
        input_schema={"type": "object", "properties": {}},
    ),
    MCPTool(
        name="evaluate",
        description="运行评测（health/citation/retrieval/evidence/full）",
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "评测类型", "enum": ["health", "citation", "retrieval", "evidence", "full"]},
                "build_id": {"type": "string", "description": "构建 ID"},
            },
            "required": ["kind"],
        },
    ),
    MCPTool(
        name="export_card",
        description="导出 Wiki 卡片为 Markdown 或 JSON",
        input_schema={
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "卡片 ID"},
                "format": {"type": "string", "description": "格式: markdown 或 json", "default": "markdown"},
            },
            "required": ["card_id"],
        },
    ),
]


@router.get("/tools")
async def mcp_list_tools():
    """列出所有 MCP 工具。"""
    return {"tools": [t.model_dump() for t in MCP_TOOLS]}


@router.post("/call")
async def mcp_call_tool(request: MCPToolCallRequest):
    """统一工具调用入口（JSON-RPC 风格）。"""
    tool_name = request.tool
    args = request.arguments

    DISPATCH = {
        "query": _tool_query,
        "search_wiki": _tool_search_wiki,
        "get_wiki_card": _tool_get_wiki_card,
        "list_wiki_cards": _tool_list_wiki_cards,
        "health": _tool_health,
        "evaluate": _tool_evaluate,
        "export_card": _tool_export_card,
    }

    handler = DISPATCH.get(tool_name)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")

    try:
        result = await handler(args)
        return _mcp_result(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MCP tool '{tool_name}' failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Tool '{tool_name}' failed: {e}")


# ---- 工具实现 ----

async def _tool_query(args: dict) -> dict:
    question = args.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    import asyncio
    loop = asyncio.get_running_loop()
    state = await loop.run_in_executor(None, run_agent_sync, question)
    return {
        "question": question,
        "answer": state.answer or "",
        "citations": [c.model_dump() if hasattr(c, "model_dump") else c for c in (state.citations or [])],
        "intent": state.intent.model_dump() if state.intent else None,
    }


async def _tool_search_wiki(args: dict) -> dict:
    keyword = args.get("keyword", "")
    top_k = args.get("top_k", 5)
    card_type = args.get("card_type")

    es_repo = WikiCardESRepository()
    try:
        await es_repo.create_index()
    except Exception:
        pass

    filters = {"card_type": card_type} if card_type else None
    results = await es_repo.search(keyword, top_k=top_k, filters=filters)
    return {"keyword": keyword, "count": len(results), "results": results}


async def _tool_get_wiki_card(args: dict) -> dict:
    card_id = args.get("card_id")
    if not card_id:
        raise HTTPException(status_code=400, detail="card_id is required")

    es_repo = WikiCardESRepository()
    card = await es_repo.get_card(card_id)  # 修复：get_chunk → get_card
    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
    return card


async def _tool_list_wiki_cards(args: dict) -> dict:
    page = args.get("page", 1)
    page_size = args.get("page_size", 20)
    card_type = args.get("card_type")
    status = args.get("status")

    es_repo = WikiCardESRepository()
    try:
        await es_repo.create_index()
    except Exception:
        pass

    from_ = max(0, (page - 1) * page_size)
    filters = {}
    if card_type:
        filters["card_type"] = card_type
    if status:
        filters["status"] = status

    results = await es_repo.search("", top_k=page_size, filters=filters or None, from_=from_)
    total = await es_repo.count(filters=filters or None)
    return {"cards": results, "total": total, "page": page, "page_size": page_size}


async def _tool_health() -> dict:
    es_repo = ElasticsearchRepository()
    milvus_repo = MilvusRepository()
    card_repo = WikiCardESRepository()

    try:
        es_count = await es_repo.count()
        es_ok = True
    except Exception:
        es_count = 0
        es_ok = False

    try:
        milvus_count = milvus_repo.count()
        milvus_ok = True
    except Exception:
        milvus_count = 0
        milvus_ok = False

    try:
        card_count = await card_repo.count()
        cards_ok = True
    except Exception:
        card_count = 0
        cards_ok = False

    return {
        "elasticsearch_ok": es_ok,
        "elasticsearch_count": es_count,
        "milvus_ok": milvus_ok,
        "milvus_chunk_count": milvus_count,
        "wiki_cards_ok": cards_ok,
        "wiki_card_count": card_count,
    }


async def _tool_evaluate(args: dict) -> dict:
    kind = args.get("kind", "full")
    build_id = args.get("build_id") or ""

    from app.eval.runner import run_eval
    report = await run_eval(kind=kind, build_id=build_id)
    return report.model_dump() if hasattr(report, "model_dump") else {
        "health_score": getattr(report, "health_score", 0.0),
        "citation_coverage": getattr(report, "citation_coverage", 0.0),
        "retrieval_precision": getattr(report, "retrieval_precision", 0.0),
        "evidence_completeness": getattr(report, "evidence_completeness", 0.0),
        "overall_score": getattr(report, "overall_score", 0.0),
    }


async def _tool_export_card(args: dict) -> dict:
    card_id = args.get("card_id")
    fmt = args.get("format", "markdown")
    if not card_id:
        raise HTTPException(status_code=400, detail="card_id is required")

    es_repo = WikiCardESRepository()
    card_dict = await es_repo.get_card(card_id)
    if not card_dict:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")

    if fmt == "json":
        return {"format": "json", "content": json.dumps(card_dict, ensure_ascii=False, indent=2)}
    else:  # markdown
        title = card_dict.get("title", "")
        content = card_dict.get("content", "")
        card_type = card_dict.get("card_type", "")
        source_ref = card_dict.get("source_ref", "")
        md = f"# {title}\n\n**类型**: {card_type}  **来源**: {source_ref}\n\n{content}"
        return {"format": "markdown", "content": md}
