"""Real project state for the planner: git status of her active projects plus open Typewriter tasks.

Read-only and best-effort: a missing repo or a failing git call just drops that project from the
context. The planner is told to use ONLY this state, so it can plan around what is genuinely
unfinished instead of generic templates.

Opt repos in with LIFE_AGENT_PROJECTS="Name=path;Other=path" (none are assumed by default).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_PROJECTS = ""   # nothing assumed: set LIFE_AGENT_PROJECTS to opt repos in
GIT_TIMEOUT = 8


def configured_projects(env: str | None = None) -> dict[str, Path]:
    raw = env if env is not None else os.getenv("LIFE_AGENT_PROJECTS", DEFAULT_PROJECTS)
    out: dict[str, Path] = {}
    for part in raw.split(";"):
        if "=" in part:
            name, _, path = part.partition("=")
            if name.strip() and path.strip():
                out[name.strip()] = Path(path.strip())
    return out


def _git(repo: Path, *args: str) -> str | None:
    try:
        res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def repo_state(name: str, repo: Path, days: int = 7, max_commits: int = 6) -> str | None:
    """One compact paragraph about a repo, or None if it is not a readable git repo."""
    if not (repo / ".git").exists():
        return None
    branch = _git(repo, "branch", "--show-current")
    if branch is None:
        return None
    commits = _git(repo, "log", f"--since={days}.days", f"--max-count={max_commits}", "--format=%s") or ""
    status = _git(repo, "status", "--porcelain") or ""
    tracked = [l for l in status.splitlines() if l and not l.startswith("??")]
    untracked = [l for l in status.splitlines() if l.startswith("??")]
    lines = [f"{name} (branch {branch or 'detached'}):"]
    lines.append(f"  - uncommitted changes: {len(tracked)} modified/staged file(s), {len(untracked)} untracked")
    recent = [c.strip() for c in commits.splitlines() if c.strip()]
    lines.append("  - commits in the last %d days: %s" % (days, "; ".join(c[:90] for c in recent) if recent else "none"))
    return "\n".join(lines)


def open_tasks(tasks_file: Path | None = None, limit: int = 12) -> list[str]:
    path = tasks_file or Path.home() / "Documents" / "Typewriter" / "tasks.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    tasks = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]") and stripped[5:].strip():
            tasks.append(stripped[5:].strip())
    return tasks[:limit]


def build(projects: dict[str, Path] | None = None, tasks_file: Path | None = None) -> str:
    """The PROJECT STATE block for the prompt. Never raises."""
    try:
        projects = projects if projects is not None else configured_projects()
        blocks = [s for s in (repo_state(n, p) for n, p in projects.items()) if s]
        tasks = open_tasks(tasks_file)
        parts = []
        if blocks:
            parts.append("\n".join(blocks))
        if tasks:
            parts.append("Open tasks in her Typewriter list:\n" + "\n".join(f"  - {t}" for t in tasks))
        return "\n\n".join(parts) if parts else "(no project state available)"
    except Exception as exc:
        print(f"[project_state] unavailable: {exc}")
        return "(no project state available)"
