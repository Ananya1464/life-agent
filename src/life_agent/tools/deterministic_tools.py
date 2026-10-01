"""
Deterministic access layer for the Lifebot agent runtime.

Rules:
- Strictly read-only access to vault paths and event data.
- Strict path validation to prevent traversal outside ANANYA-OS vault.
- No LLM calls.
- Deterministic behavior.
"""
from typing import List, Dict, Optional, Union
import os
from pathlib import Path
from life_agent.tools import activity

# Canonical vault root path. Override with LIFE_AGENT_VAULT_ROOT; the default is the
# ANANYA-OS vault on the current user's OneDrive desktop.
VAULT_ROOT = Path(
    os.environ.get("LIFE_AGENT_VAULT_ROOT")
    or Path.home() / "OneDrive" / "Desktop" / "ANANYA-OS"
).resolve()

def _validate_vault_path(relative_path: str) -> Path:
    """Validate and resolve path, ensuring it stays within VAULT_ROOT."""
    # Reject absolute paths
    if os.path.isabs(relative_path):
        raise ValueError("Absolute paths are not permitted.")

    # Resolve requested path relative to VAULT_ROOT
    target = (VAULT_ROOT / relative_path).resolve()

    # Ensure it's within vault using pathlib.Path.is_relative_to (Python 3.9+)
    # If not supported by python version, fall back to comparing parents
    if hasattr(target, "is_relative_to"):
        if not target.is_relative_to(VAULT_ROOT):
            raise ValueError("Access denied: path outside vault.")
    else:
        # Fallback check
        if not (target == VAULT_ROOT or VAULT_ROOT in target.parents):
            raise ValueError("Access denied: path outside vault.")

    return target

def get_recent_activity(days_back: int = 1) -> List[Dict]:
    """
    Retrieves activity records using existing deterministic tools.
    Delegates to life_agent.tools.activity.get_activity with negative offset.
    - 0 represents 'today'.
    - 1 represents 'yesterday'.
    - days_back=N represents exactly N days before today.
    """
    return activity.get_activity(date_spec=-days_back)

def read_vault_note(relative_path: str) -> str:
    """
    Read note content if it exists within the vault.
    Strictly read-only.
    """
    target = _validate_vault_path(relative_path)

    if not target.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    if not target.is_file():
        raise ValueError(f"Path is not a file: {relative_path}")

    return target.read_text(encoding="utf-8")

def list_vault_notes(relative_dir: str = "") -> List[str]:
    """
    List note paths beneath the vault root (or a subdirectory).
    """
    target_dir = _validate_vault_path(relative_dir)

    if not target_dir.is_dir():
        raise ValueError(f"Not a directory: {relative_dir}")

    # Return relative paths from vault root, deterministically sorted
    # Ensure we only list files within VAULT_ROOT
    files = []
    for path in target_dir.rglob("*.md"):
        # Ensure path is truly within vault
        if hasattr(path, "is_relative_to"):
            if not path.is_relative_to(VAULT_ROOT):
                continue
        elif not (path == VAULT_ROOT or VAULT_ROOT in path.parents):
            continue

        files.append(str(path.relative_to(VAULT_ROOT)))

    return sorted(files)
