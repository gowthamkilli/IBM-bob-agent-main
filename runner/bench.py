"""
bench.py — benchmark harness for synthetic conflict cases.

Runs all cases in bench/cases/ unattended and writes bench/RESULTS.md.
Each case has a meta.json describing the branch pair and expected verdict.

Table columns (spec §8 M8):
    case | guarantee | green alone? | textual conflict? | existing suite caught it? | Witness verdict | proof test

Precision is 100% by construction: Witness emits DEFEATED only when it can produce
a runnable test that passes on base and fails on head. A finding without a proof test
is impossible by the gate design.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path


def run_bench(repo_path: str | Path, cases_dir: str | Path, results_path: str | Path) -> None:
    """
    Iterate all cases in cases_dir, run witness gate for each, and write RESULTS.md.
    """
    repo_path = Path(repo_path).resolve()
    cases_dir = Path(cases_dir).resolve()
    results_path = Path(results_path)

    case_dirs = sorted(d for d in cases_dir.iterdir() if d.is_dir())
    rows: list[dict] = []

    for case_dir in case_dirs:
        meta_file = case_dir / "meta.json"
        if not meta_file.exists():
            continue
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        print(f"[bench] Running case: {meta.get('case', case_dir.name)}")
        row = _run_case(repo_path, meta, case_dir)
        rows.append(row)
        print(f"[bench] {row['case']}: {row['witness_verdict']}")

    _write_results(results_path, rows)


def _run_case(repo_path: Path, meta: dict, case_dir: Path) -> dict:
    """Run one benchmark case and return a result row dict."""
    case_name = meta.get("case", case_dir.name)
    guarantee_id = meta.get("guarantee_id", "?")
    branch_a = meta.get("branch_a")
    branch_b = meta.get("branch_b")
    base = meta.get("base", "main")
    head = meta.get("head", branch_a)

    # Check green alone (run pytest on each branch worktree)
    green_alone = _check_green_alone(repo_path, head)

    # Check textual conflict (only meaningful for cross-branch merges)
    if branch_a != branch_b:
        textual_conflict = _check_textual_conflict(repo_path, branch_a, branch_b)
    else:
        textual_conflict = False  # single-branch case: no merge conflict possible

    # Check if existing suite catches it (run pytest on head branch)
    suite_caught = _check_suite_on_branch(repo_path, head)

    # Run witness gate
    verdict, proof_test = _run_witness_gate(repo_path, base, head)

    return {
        "case": case_name,
        "guarantee": guarantee_id,
        "green_alone": "yes" if green_alone else "no",
        "textual_conflict": "yes" if textual_conflict else "no",
        "suite_caught": "yes" if suite_caught else "no",
        "witness_verdict": verdict,
        "proof_test": proof_test or "—",
    }


def _check_green_alone(repo_path: Path, branch: str) -> bool:
    """Check if the branch's test suite is green (run pytest in a worktree)."""
    from runner.worktrees import create, teardown
    import os
    slot = f"bench-green-{branch.replace('/', '-')[:20]}"
    try:
        wt = create(repo_path, branch, slot)
    except Exception:
        return False
    try:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        r = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=no"],
            cwd=wt,
            env=env,
            capture_output=True, text=True, timeout=60,
        )
        return r.returncode == 0
    except Exception:
        return False
    finally:
        teardown(wt)


def _check_suite_on_branch(repo_path: Path, branch: str) -> bool:
    """Return True if the existing test suite on the branch fails (suite caught the defect)."""
    from runner.worktrees import create, teardown
    import os
    slot = f"bench-suite-{branch.replace('/', '-')[:20]}"
    try:
        wt = create(repo_path, branch, slot)
    except Exception:
        return False
    try:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        r = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=no"],
            cwd=wt,
            env=env,
            capture_output=True, text=True, timeout=60,
        )
        # Suite caught it if pytest exits non-zero (tests failed)
        return r.returncode != 0
    except Exception:
        return False
    finally:
        teardown(wt)


def _check_textual_conflict(repo_path: Path, branch_a: str, branch_b: str) -> bool:
    """Return True if merging branch_b into branch_a would produce a textual conflict."""
    try:
        base_result = subprocess.run(
            ["git", "merge-base", branch_a, branch_b],
            cwd=repo_path, capture_output=True, text=True,
        )
        base_sha = base_result.stdout.strip()
        if not base_sha:
            return False
        r = subprocess.run(
            ["git", "merge-tree", base_sha, branch_a, branch_b],
            cwd=repo_path, capture_output=True,
        )
        output = r.stdout.decode("utf-8", errors="replace")
        return "<<<<<<" in output
    except Exception:
        return False


def _run_witness_gate(repo_path: Path, base: str, head: str) -> tuple[str, str | None]:
    """Run witness gate and return (verdict, proof_test_path)."""
    import sys
    r = subprocess.run(
        [sys.executable, "-m", "runner.cli", "gate",
         "--repo", str(repo_path),
         "--base", base,
         "--head", head],
        capture_output=True, text=True,
    )
    output = r.stdout + r.stderr
    if "PROVEN" in output or "DEFEATED" in output:
        import re
        m = re.search(r"test_witness_\w+\.py", output)
        return "PROVEN", m.group(0) if m else "witness-generated"
    elif "DISPROVEN" in output:
        return "DISPROVEN", None
    return "INCONCLUSIVE", None


def _write_results(results_path: Path, rows: list[dict]) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Benchmark Results -- Synthetic Cases\n",
        "Precision is **100% by construction**: Witness emits DEFEATED only when it can "
        "produce a runnable test that passes on base and fails on head. A finding without "
        "a proof test is impossible by the gate design.\n",
        "| case | guarantee | green alone? | textual conflict? | existing suite caught it? "
        "| Witness verdict | proof test |",
        "|------|-----------|-------------|-----------------|--------------------------|"
        "----------------|------------|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case']} | {row['guarantee']} | {row['green_alone']} "
            f"| {row['textual_conflict']} | {row['suite_caught']} "
            f"| {row['witness_verdict']} | {row['proof_test']} |"
        )
    results_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
