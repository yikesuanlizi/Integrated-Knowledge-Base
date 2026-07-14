import pytest


@pytest.mark.asyncio
async def test_stdio_server_initializes_with_tool_capability():
    from app.mcp.stdio_server import handle_jsonrpc_message

    response = await handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    })

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["serverInfo"]["name"] == "agentic-knowledge-os"
    assert "tools" in response["result"]["capabilities"]


@pytest.mark.asyncio
async def test_stdio_server_lists_tools_with_mcp_schema():
    from app.mcp.stdio_server import handle_jsonrpc_message

    response = await handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    })

    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}

    assert {"query", "ingest_path", "compile_knowledge", "status"}.issubset(names)
    assert all("inputSchema" in tool for tool in tools)


@pytest.mark.asyncio
async def test_stdio_server_calls_registered_tool_and_wraps_text_content():
    from app.mcp.stdio_server import handle_jsonrpc_message

    async def echo_tool(message: str) -> dict:
        return {"echo": message}

    registry = {
        "echo": {
            "description": "Echo a message.",
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
            "handler": echo_tool,
        }
    }

    response = await handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "echo",
                "arguments": {"message": "hello"},
            },
        },
        registry=registry,
    )

    assert response["result"]["content"][0]["type"] == "text"
    assert '"echo": "hello"' in response["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_stdio_server_returns_jsonrpc_error_for_unknown_tool():
    from app.mcp.stdio_server import handle_jsonrpc_message

    response = await handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "missing", "arguments": {}},
    })

    assert response["id"] == 4
    assert response["error"]["code"] == -32602
    assert "Unknown tool" in response["error"]["message"]
