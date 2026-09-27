"""
race.py — spawn lane agents and collect LaneResult objects.

Control flow (DECISIONS.md D2):
    Bob spawns 5 lane subagents concurrently.
    Each agent returns a D3 protocol block (text, ≤2000 tokens).
    This module parses the block, writes the test file to disk,
    and invokes execute.py on both worktrees.
    Each result is flushed to dashboard/data/run-<id>.json incrementally.

D3 return protocol (all fields required; missing any = INVALID):
    LANE_ID: <id>
    CANDIDATE_ID: <id>
    PROOF_FORM: differential | contradiction | impossibility
    EXPECTED_FAILURE: <exception class or assert substring>
    DEATH_NOTE: <one line>
    TEST_SOURCE_START
    <test file content>
    TEST_SOURCE_END
"""
from __future__ import annotations
import json
import re
import tempfile
import time
from pathlib import Path

from runner.schemas import LaneResult
from runner.execute import run_test


def parse_lane_output(text: str) -> dict:
    """
    Parse a lane agent's D3 protocol block.
    Returns a dict with keys: lane_id, candidate_id, proof_form,
    expected_failure, death_note, test_source.
    Returns {"invalid": True, "reason": str} if any required field is missing.
    """
    fields = {}

    for field_name in ("LANE_ID", "CANDIDATE_ID", "PROOF_FORM", "EXPECTED_FAILURE", "DEATH_NOTE"):
        m = re.search(rf"^{field_name}:\s*(.+)$", text, re.MULTILINE)
        if not m:
            return {"invalid": True, "reason": f"Missing required field: {field_name}"}
        fields[field_name.lower()] = m.group(1).strip()

    src_match = re.search(r"TEST_SOURCE_START\s*\n(.*?)\nTEST_SOURCE_END", text, re.DOTALL)
    if not src_match:
        return {"invalid": True, "reason": "Missing TEST_SOURCE_START/END block"}

    fields["test_source"] = src_match.group(1)
    return fields


def run_lane(
    parsed: dict,
    base_worktree: str | Path,
    head_worktree: str | Path,
    mode: str,  # "gate" | "standing"
    run_id: str,
    output_dir: str | Path,
) -> LaneResult:
    """
    Execute one lane: write the test file, run on base and head worktrees,
    build a LaneResult, flush it to disk.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lane_id = parsed.get("lane_id", "L?")
    candidate_id = parsed.get("candidate_id", "C?")
    death_note = parsed.get("death_note", "")
    expected_failure_str = parsed.get("expected_failure", "")
    test_source = parsed.get("test_source", "")
    test_filename = f"test_witness_lane_{lane_id}.py"

    expected_failure = {
        "exception": None,
        "assert_substring": expected_failure_str,
    }
    # If it looks like an exception class name, put it there
    if re.match(r"^[A-Z][a-zA-Z]+Error$", expected_failure_str):
        expected_failure["exception"] = expected_failure_str
        expected_failure["assert_substring"] = ""

    t0 = time.monotonic()

    # Run on base (None for standing mode)
    if mode == "gate":
        base_res = run_test(base_worktree, test_source, test_filename)
        base_result = base_res["result"]
        stderr = base_res["stderr_excerpt"]
    else:
        base_result = None
        base_res = {"stderr_excerpt": "", "elapsed_s": 0.0}
        stderr = ""

    # Run on head
    head_res = run_test(head_worktree, test_source, test_filename)
    head_result = head_res["result"]
    stderr = (stderr + head_res["stderr_excerpt"])[-400:]
    elapsed = time.monotonic() - t0

    verdict = _classify_verdict(mode, base_result, head_result, expected_failure, test_source)

    result = LaneResult(
        lane_id=lane_id,
        candidate_id=candidate_id,
        test_path=test_filename,
        expected_failure=expected_failure,
        base_result=base_result,
        head_result=head_result,
        verdict=verdict,
        stderr_excerpt=stderr,
        elapsed_s=elapsed,
        death_note=death_note,
    )

    # Flush incrementally (spec §6)
    _flush_lane_result(result, run_id, output_dir)
    return result


def _classify_verdict(
    mode: str,
    base_result: str | None,
    head_result: str,
    expected_failure: dict,
    test_source: str,
) -> str:
    if head_result == "ERROR":
        return "INVALID"
    if mode == "gate":
        if base_result == "ERROR":
            return "INVALID"
        if base_result == "PASS" and head_result == "FAIL":
            return "PROVEN"
        if base_result == "PASS" and head_result == "PASS":
            return "DISPROVEN"
    else:  # standing
        if head_result == "FAIL":
            return "PROVEN"
        if head_result == "PASS":
            return "DISPROVEN"
    return "INCONCLUSIVE"


def _flush_lane_result(result: LaneResult, run_id: str, output_dir: Path) -> None:
    """Append this lane result to the run JSON file immediately."""
    run_file = output_dir / f"run-{run_id}.json"
    existing: list[dict] = []
    if run_file.exists():
        try:
            existing = json.loads(run_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []

    existing.append({
        "lane_id": result.lane_id,
        "candidate_id": result.candidate_id,
        "test_path": result.test_path,
        "expected_failure": result.expected_failure,
        "base_result": result.base_result,
        "head_result": result.head_result,
        "verdict": result.verdict,
        "stderr_excerpt": result.stderr_excerpt,
        "elapsed_s": result.elapsed_s,
        "death_note": result.death_note,
    })
    run_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")
