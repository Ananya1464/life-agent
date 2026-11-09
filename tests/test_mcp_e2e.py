import json

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from life_agent import mcp_server
from mcp.types import CallToolResult, TextContent

@pytest.mark.asyncio
async def test_sdk_list_tools():
    # Calling the SDK's internal async list_tools()
    tools = await mcp_server.mcp.list_tools()
    assert len(tools) == 3
    names = [t.name for t in tools]
    assert "get_recent_activity" in names
    assert "read_vault_note" in names
    assert "list_vault_notes" in names

@pytest.mark.asyncio
async def test_call_tool_valid_mocked():
    # Use AsyncMock for the adapter call
    with patch("life_agent.tools.mcp_adapter.execute_tool") as mock_exec:
        mock_exec.return_value = "note content"
        # call_tool is expected to be called via the SDK manager, which is async
        result = await mcp_server.mcp.call_tool("read_vault_note", {"relative_path": "test.md"})

        # Verify result structure
        assert isinstance(result, CallToolResult)
        assert result.content[0].text == "note content"
        assert result.is_error is False

@pytest.mark.asyncio
async def test_call_tool_traversal_denied_mocked():
    with patch("life_agent.tools.mcp_adapter.execute_tool", side_effect=ValueError("Access denied")):
        with pytest.raises(ToolError):
            await mcp_server.mcp.call_tool("read_vault_note", {"relative_path": "../hidden.md"})


@pytest.mark.asyncio
async def test_validation_errors_are_surfaced():
    with patch("life_agent.tools.mcp_adapter.execute_tool",
               side_effect=ValueError("Absolute paths are not permitted.")):
        with pytest.raises(ToolError, match="Absolute paths are not permitted"):
            await mcp_server.mcp.call_tool("read_vault_note", {"relative_path": "/x.md"})


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    RuntimeError(r"boom at C:\secret\path"),
    ValueError(r"internal detail C:\secret\path"),
    PermissionError(r"denied C:\secret\path"),
])
async def test_unexpected_errors_are_sanitised(error):
    with patch("life_agent.tools.mcp_adapter.execute_tool", side_effect=error):
        with pytest.raises(ToolError) as exc:
            await mcp_server.mcp.call_tool("read_vault_note", {"relative_path": "a.md"})
    assert "secret" not in str(exc.value)
    assert "unexpected error" in str(exc.value)


@pytest.mark.asyncio
async def test_list_and_activity_return_json():
    with patch("life_agent.tools.mcp_adapter.execute_tool", return_value=["a.md", "b/é.md"]):
        result = await mcp_server.mcp.call_tool("list_vault_notes", {})
        assert json.loads(result.content[0].text) == ["a.md", "b/é.md"]

    sessions = [{"task": "Task A", "status": "completed", "duration_seconds": 1500, "end": None}]
    with patch("life_agent.tools.mcp_adapter.execute_tool", return_value=sessions):
        result = await mcp_server.mcp.call_tool("get_recent_activity", {"days_back": 0})
        assert json.loads(result.content[0].text) == sessions
