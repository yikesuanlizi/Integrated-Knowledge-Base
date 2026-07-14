"""MCP tool functions for Agentic Knowledge OS.

The functions are dependency-light wrappers so they can be bound to a concrete
MCP SDK without changing service-layer contracts.
"""
from __future__ import annotations

from app.api.query import query_knowledge
from app.models.schemas import QueryRequest
from app.services.compile_service import CompileService
from app.services.ingest_service import IngestService


async def ingest_path(path: str, force: bool = False) -> dict:
    return await IngestService().ingest_directory(path, force=force)


async def compile_knowledge(build_id: str | None = None) -> dict:
    result = await CompileService().compile(build_id=build_id)
    return result


async def query(question: str, top_k: int = 8) -> dict:
    result = await query_knowledge(QueryRequest(question=question, top_k=top_k))
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)


async def status() -> dict:
    ingest = await IngestService().get_status()
    return {"ingest": ingest}


def list_tools() -> list[dict]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "input_schema": spec["input_schema"],
        }
        for name, spec in get_tool_registry().items()
    ]


def get_tool_registry() -> dict[str, dict]:
    return {
        "ingest_path": {
            "description": "Ingest a local directory of documents.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Local directory path to ingest."},
                    "force": {"type": "boolean", "description": "Re-ingest even if documents already exist.", "default": False},
                },
                "required": ["path"],
            },
            "handler": ingest_path,
        },
        "compile_knowledge": {
            "description": "Compile ingested chunks into Wiki cards.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "build_id": {"type": "string", "description": "Optional build id. Uses latest build when omitted."},
                },
            },
            "handler": compile_knowledge,
        },
        "query": {
            "description": "Run unified RAG/NL2SQL question answering.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "User question."},
                    "top_k": {"type": "integer", "description": "Retrieval candidate count.", "default": 8},
                },
                "required": ["question"],
            },
            "handler": query,
        },
        "status": {
            "description": "Return ingestion/index status.",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
            "handler": status,
        },
    }
