"""Minimal MCP server boundary.

This module intentionally avoids importing a concrete MCP SDK. It exposes the
tool registry used by future stdio/http MCP adapters.
"""
from __future__ import annotations

from app.mcp import tools


TOOL_REGISTRY = {
    "ingest_path": tools.ingest_path,
    "compile_knowledge": tools.compile_knowledge,
    "query": tools.query,
    "status": tools.status,
}


def get_tool_registry() -> dict:
    return TOOL_REGISTRY
