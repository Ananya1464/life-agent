"""
Adapter to expose deterministic_tools via MCP.
Strictly read-only interaction with Life Agent tools.
"""
from typing import Dict, Any, List
from life_agent.tools import deterministic_tools

# Exactly three approved read-only tools
APPROVED_TOOLS = {
    "get_recent_activity": deterministic_tools.get_recent_activity,
    "read_vault_note": deterministic_tools.read_vault_note,
    "list_vault_notes": deterministic_tools.list_vault_notes,
}

def list_available_tools() -> List[str]:
    return list(APPROVED_TOOLS.keys())

def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    if tool_name not in APPROVED_TOOLS:
        raise ValueError(f"Tool {tool_name} not found or not approved.")

    # Direct delegation, no changes to business logic or security validation.
    # Security validation (e.g. _validate_vault_path) is already inside deterministic_tools.
    return APPROVED_TOOLS[tool_name](**arguments)
