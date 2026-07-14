"""Stdio MCP server backed by the local tool registry.

The implementation keeps the transport dependency-free: every stdin line is a
JSON-RPC request and every stdout line is a JSON-RPC response.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
from collections.abc import Callable
from typing import Any, TextIO

from app.mcp.tools import get_tool_registry


SERVER_NAME = "agentic-knowledge-os"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


ToolRegistry = dict[str, dict[str, Any]]


async def handle_jsonrpc_message(message: dict[str, Any], registry: ToolRegistry | None = None) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    tool_registry = registry or get_tool_registry()

    if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return _error(request_id, JSONRPC_INVALID_REQUEST, "Invalid JSON-RPC request.")

    if request_id is None and method.startswith("notifications/"):
        return None

    try:
        if method == "initialize":
            return _result(request_id, _initialize_result(params))
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": _list_tools(tool_registry)})
        if method == "tools/call":
            return _result(request_id, await _call_tool(params, tool_registry))
        if method.startswith("notifications/"):
            return None
        return _error(request_id, JSONRPC_METHOD_NOT_FOUND, f"Unknown method: {method}")
    except ValueError as exc:
        return _error(request_id, JSONRPC_INVALID_PARAMS, str(exc))
    except Exception as exc:
        return _error(request_id, JSONRPC_INTERNAL_ERROR, f"Internal MCP server error: {exc}")


async def run_stdio_server(stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout

    for line in in_stream:
        raw = line.strip()
        if not raw:
            continue

        response = await _handle_raw_line(raw)
        if response is None:
            continue

        out_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        out_stream.flush()


async def _handle_raw_line(raw: str) -> dict[str, Any] | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc.msg}")

    if not isinstance(message, dict):
        return _error(None, JSONRPC_INVALID_REQUEST, "JSON-RPC message must be an object.")

    return await handle_jsonrpc_message(message)


def _initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
    return {
        "protocolVersion": requested_version or DEFAULT_PROTOCOL_VERSION,
        "capabilities": {
            "tools": {
                "listChanged": False,
            },
        },
        "serverInfo": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
        },
    }


def _list_tools(registry: ToolRegistry) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name, spec in registry.items():
        tools.append({
            "name": name,
            "description": spec.get("description", ""),
            "inputSchema": spec.get("input_schema", {"type": "object", "properties": {}}),
        })
    return tools


async def _call_tool(params: dict[str, Any], registry: ToolRegistry) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("tools/call params must be an object.")

    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str) or not name:
        raise ValueError("Tool name is required.")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object.")

    spec = registry.get(name)
    if spec is None:
        raise ValueError(f"Unknown tool: {name}")

    handler = spec.get("handler")
    if not callable(handler):
        raise ValueError(f"Tool has no callable handler: {name}")

    result = await _invoke_handler(handler, arguments)
    return {
        "content": [
            {
                "type": "text",
                "text": _to_text(result),
            }
        ]
    }


async def _invoke_handler(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    output = handler(**arguments)
    if inspect.isawaitable(output):
        return await output
    return output


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def main() -> None:
    asyncio.run(run_stdio_server())


if __name__ == "__main__":
    main()
