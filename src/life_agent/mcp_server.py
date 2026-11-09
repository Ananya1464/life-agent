"""
Life Agent MCP Server — Phase 6A prototype.

Exposes exactly three approved read-only tools through a local stdio
Model Context Protocol server. No external data transmission. No write
operations. Hermes bridge and all public APIs remain unchanged.

Transport: stdio (local only)
"""
import json
from typing import Any, Dict

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from life_agent.tools import mcp_adapter

# --- Server instance ---------------------------------------------------------

mcp = MCPServer("life-agent-mcp")

# --- Error handling ----------------------------------------------------------
# Validation errors raised by deterministic_tools / mcp_adapter only echo the
# caller's own input, so they are surfaced verbatim. Anything else is sanitised
# so internal details (absolute paths, stack traces) never reach the client.

_SAFE_ERROR_MARKERS = (
    "Access denied",
    "Absolute paths are not permitted",
    "Note not found",
    "Path is not a file",
    "Not a directory",
    "not approved",
)


def _call(tool_name: str, arguments: Dict[str, Any]) -> Any:
    try:
        return mcp_adapter.execute_tool(tool_name, arguments)
    except UnicodeDecodeError:
        raise ToolError("Note is not valid UTF-8 text.")
    except (ValueError, FileNotFoundError) as e:
        message = str(e)
        if any(marker in message for marker in _SAFE_ERROR_MARKERS):
            raise ToolError(message)
        raise ToolError("An unexpected error occurred.")
    except Exception:
        raise ToolError("An unexpected error occurred.")


# --- Tool registrations ------------------------------------------------------
# Each tool delegates directly to mcp_adapter, which enforces the allowlist
# and delegates to deterministic_tools (which enforces path validation).

@mcp.tool()
def get_recent_activity(days_back: int = 1) -> str:
    """Get recent activity records from the Life Agent journal.

    Returns a JSON array of focus sessions (date, task, start, end,
    duration_seconds, source, status).

    Args:
        days_back: How many days back to look (0 = today, 1 = yesterday, …).
    """
    result = _call("get_recent_activity", {"days_back": days_back})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def read_vault_note(relative_path: str) -> str:
    """Read the contents of a vault note by its path relative to the vault root.

    Args:
        relative_path: Path to the note relative to the vault root (e.g. "Journal/2026-09-30.md").
                       Absolute paths and traversal sequences are rejected.
    """
    return str(_call("read_vault_note", {"relative_path": relative_path}))


@mcp.tool()
def list_vault_notes(relative_dir: str = "") -> str:
    """List all markdown note paths within a vault directory.

    Returns a JSON array of paths relative to the vault root.

    Args:
        relative_dir: Directory path relative to the vault root (empty = vault root).
                      Absolute paths and traversal sequences are rejected.
    """
    result = _call("list_vault_notes", {"relative_dir": relative_dir})
    return json.dumps(result, ensure_ascii=False)


# --- Entry point -------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()  # stdio transport by default
