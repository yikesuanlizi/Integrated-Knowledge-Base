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
        {"name": "ingest_path", "description": "Ingest a local directory of documents."},
        {"name": "compile_knowledge", "description": "Compile ingested chunks into Wiki cards."},
        {"name": "query", "description": "Run unified RAG/NL2SQL question answering."},
        {"name": "status", "description": "Return ingestion/index status."},
    ]
