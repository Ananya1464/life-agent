import subprocess
from pathlib import Path

from life_agent.agent import project_state as ps


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(tmp_path, name="proj"):
    repo = tmp_path / name
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("1")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "first commit")
    return repo


def test_configured_projects_parsing():
    got = ps.configured_projects("Lifebot=D:/a; Job Agent = D:/b ;bad;=x;y=")
    assert got == {"Lifebot": Path("D:/a"), "Job Agent": Path("D:/b")}


def test_repo_state_reports_branch_commits_and_dirty_files(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("changed")
    (repo / "new.txt").write_text("x")
    out = ps.repo_state("Proj", repo)
    assert "Proj (branch " in out and "first commit" in out
    assert "1 modified/staged file(s), 1 untracked" in out


def test_non_repo_and_missing_path_are_skipped(tmp_path):
    assert ps.repo_state("X", tmp_path) is None
    assert ps.repo_state("X", tmp_path / "nope") is None


def test_open_tasks_lists_only_unchecked(tmp_path):
    f = tmp_path / "tasks.md"
    f.write_text("## Today\n- [ ] Finish Lifebot tests\n- [x] Done thing (done 2026-10-01T10:00)\n- [ ]\n- [ ] Study ML\n", encoding="utf-8")
    assert ps.open_tasks(f) == ["Finish Lifebot tests", "Study ML"]
    assert ps.open_tasks(tmp_path / "missing.md") == []


def test_build_combines_and_never_raises(tmp_path):
    repo = make_repo(tmp_path)
    f = tmp_path / "tasks.md"
    f.write_text("- [ ] Ship it\n", encoding="utf-8")
    out = ps.build({"Proj": repo, "Gone": tmp_path / "nope"}, f)
    assert "Proj (branch" in out and "Gone" not in out and "Ship it" in out
    assert ps.build({}, tmp_path / "none.md") == "(no project state available)"
