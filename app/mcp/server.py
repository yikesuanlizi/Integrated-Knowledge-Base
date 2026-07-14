"""MCP server boundary shared by stdio and HTTP adapters."""
from __future__ import annotations

from app.mcp.tools import get_tool_registry as _get_tool_registry


def get_tool_registry() -> dict:
    return _get_tool_registry()
