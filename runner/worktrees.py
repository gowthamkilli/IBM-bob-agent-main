"""
worktrees.py — create and tear down git worktrees for differential execution.

Rules (DECISIONS.md D7, spec §8 M3):
- Use `git worktree add` only. Never run git checkout/stash/reset on the main tree.
- Worktrees live under <repo>/.wt/<slot>/
"""
from __future__ import annotations
import subprocess
import shutil
from pathlib import Path


def create(repo: str | Path, ref: str, slot: str) -> Path:
    """
    Create a git worktree at <repo>/.wt/<slot> checked out at <ref>.
    Returns the absolute path to the worktree.
    """
    repo = Path(repo).resolve()
    wt_path = repo / ".wt" / slot
    if wt_path.exists():
        teardown(wt_path)
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(wt_path), ref],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return wt_path


def teardown(wt_path: str | Path) -> None:
    """Remove a worktree and its directory."""
    wt_path = Path(wt_path)
    repo = _find_repo_root(wt_path)
    if repo:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt_path)],
            cwd=repo,
            capture_output=True,
            text=True,
        )
    if wt_path.exists():
        shutil.rmtree(wt_path, ignore_errors=True)


def _find_repo_root(path: Path) -> Path | None:
    """Walk up from path to find the .git directory."""
    for parent in [path, *path.parents]:
        if (parent / ".git").exists():
            return parent
    return None
