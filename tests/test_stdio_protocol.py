"""End-to-end test: spawn the MCP server as a subprocess and talk to it over real stdio."""
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SRC = str(Path(__file__).resolve().parent.parent / "src")


@pytest.fixture
def server_params(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Journal").mkdir(parents=True)
    (vault / "Journal" / "2026-09-30.md").write_text("café ☕ day", encoding="utf-8")
    (vault / "top.md").write_text("top", encoding="utf-8")

    # Events are read from ./data/events.jsonl relative to the server's cwd
    work = tmp_path / "work"
    (work / "data").mkdir(parents=True)
    today = date.today().isoformat()
    (work / "data" / "events.jsonl").write_text(
        json.dumps({"id": "1", "ts": f"{today}T10:00:00Z", "kind": "focus_completed",
                    "date": today, "task": "Task A", "duration_seconds": 1500,
                    "intent_id": "p:s1", "source": "pomodoro_app"}) + "\n",
        encoding="utf-8",
    )

    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "life_agent.mcp_server"],
        cwd=str(work),
        env={**os.environ, "PYTHONPATH": SRC, "LIFE_AGENT_VAULT_ROOT": str(vault)},
    )


async def _call(session, name, arguments):
    result = await session.call_tool(name, arguments)
    text = "".join(c.text for c in result.content if c.type == "text")
    return result, text


@pytest.mark.asyncio
async def test_stdio_list_tools(server_params):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert sorted(t.name for t in tools.tools) == [
                "get_recent_activity", "list_vault_notes", "read_vault_note",
            ]


@pytest.mark.asyncio
async def test_stdio_vault_root_env_and_reads(server_params):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            _, text = await _call(session, "list_vault_notes", {})
            assert json.loads(text) == [str(Path("Journal/2026-09-30.md")), "top.md"]

            result, text = await _call(session, "read_vault_note", {"relative_path": "Journal/2026-09-30.md"})
            assert not result.is_error
            assert text == "café ☕ day"


@pytest.mark.asyncio
@pytest.mark.parametrize("path, expected", [
    ("../hidden.md", "Access denied"),
    (os.path.abspath("note.md"), "Absolute paths are not permitted"),
    ("missing.md", "Note not found"),
    ("Journal", "Path is not a file"),
])
async def test_stdio_read_errors_are_surfaced(server_params, path, expected):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result, text = await _call(session, "read_vault_note", {"relative_path": path})
            assert result.is_error
            assert expected in text


@pytest.mark.asyncio
async def test_stdio_list_missing_dir_is_surfaced(server_params):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result, text = await _call(session, "list_vault_notes", {"relative_dir": "nope"})
            assert result.is_error
            assert "Not a directory" in text


@pytest.mark.asyncio
async def test_stdio_get_recent_activity_returns_json(server_params):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result, text = await _call(session, "get_recent_activity", {"days_back": 0})
            assert not result.is_error
            sessions = json.loads(text)
            assert [(s["task"], s["status"], s["duration_seconds"]) for s in sessions] == [
                ("Task A", "completed", 1500)
            ]
