"""
execute.py — run one test file against one worktree and return a tri-state result.

Rules (DECISIONS.md D7, spec §8 M3):
- Never install the sample app (no pip install -e .).
- Share one venv for third-party deps only.
- Run pytest with cwd=worktree_path so `import app` resolves locally.
- Clear PYTHONPATH before each run.
- Hard 120s timeout → INCONCLUSIVE.
- Import/collection error in stderr → ERROR (never FAIL).
"""
from __future__ import annotations
import os
import subprocess
import tempfile
import time
from pathlib import Path

TIMEOUT_S = 120
STDERR_MAX = 400


def run_test(
    worktree_path: str | Path,
    test_file_content: str,
    test_filename: str = "test_witness_probe.py",
) -> dict:
    """
    Write test_file_content to a temp file inside worktree_path, run pytest,
    and return:
        {
            "result": "PASS" | "FAIL" | "ERROR" | "INCONCLUSIVE",
            "stderr_excerpt": str,   # <= 400 chars
            "elapsed_s": float,
        }
    """
    worktree_path = Path(worktree_path).resolve()
    test_file = worktree_path / test_filename
    test_file.write_text(test_file_content, encoding="utf-8")

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)  # never leak caller's path (D7)

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", test_filename, "-x", "--tb=short", "-q"],
            cwd=worktree_path,   # app/ resolves from here (D7)
            env=env,
            timeout=TIMEOUT_S,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        return {
            "result": "INCONCLUSIVE",
            "stderr_excerpt": "Timeout after 120s",
            "elapsed_s": elapsed,
        }
    finally:
        # Clean up probe file
        if test_file.exists():
            test_file.unlink()

    elapsed = time.monotonic() - t0
    stderr_combined = (proc.stdout + proc.stderr)[-STDERR_MAX:]

    # Collection/import error → ERROR (not FAIL)
    if _is_collection_error(proc.stdout, proc.stderr):
        return {
            "result": "ERROR",
            "stderr_excerpt": stderr_combined,
            "elapsed_s": elapsed,
        }

    if proc.returncode == 0:
        result = "PASS"
    else:
        result = "FAIL"

    return {
        "result": result,
        "stderr_excerpt": stderr_combined,
        "elapsed_s": elapsed,
    }


def _is_collection_error(stdout: str, stderr: str) -> bool:
    """Return True if pytest failed at collection/import, not at assertion."""
    combined = stdout + stderr
    markers = [
        "ERROR collecting",
        "ImportError",
        "ModuleNotFoundError",
        "SyntaxError",
        "collection errors",
        "ERRORS",
    ]
    # Only flag as collection error if no tests were actually run
    if "passed" in combined or "failed" in combined:
        return False
    return any(m in combined for m in markers)
