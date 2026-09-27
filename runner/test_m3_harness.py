"""
test_m3_harness.py — M3 acceptance test for the differential execution harness.

Verifies that:
1. base worktree (team-a pre-merge) returns PASS for G1 proof test
2. head worktree (team-a after merge with team-b) returns FAIL for G1 proof test

Run from the project root:
    python -m pytest runner/test_m3_harness.py -v
"""
import pytest
from pathlib import Path
from runner.worktrees import create, teardown
from runner.execute import run_test
from runner.proof_tests import G1_TEST_SOURCE

REPO = Path(__file__).parent.parent / "sample-repo"
BASE_REF = "6d6a58e"       # team-a/rate-limit before merge — no retry
HEAD_REF = "team-a/rate-limit"   # after merge with team-b — has retry


def test_g1_proof_differential():
    """
    M3 acceptance: base=PASS (pre-merge), head=FAIL (post-merge with retries).
    This is the critical proof that the harness correctly identifies the G1 defeat.
    """
    base_wt = create(REPO, BASE_REF, "m3-g1-base")
    head_wt = create(REPO, HEAD_REF, "m3-g1-head")

    try:
        base_res = run_test(base_wt, G1_TEST_SOURCE, "test_g1_ceiling.py")
        head_res = run_test(head_wt, G1_TEST_SOURCE, "test_g1_ceiling.py")
    finally:
        teardown(base_wt)
        teardown(head_wt)

    assert base_res["result"] == "PASS", (
        f"G1 proof: base ({BASE_REF}) should PASS, got {base_res['result']}\n"
        f"stderr: {base_res['stderr_excerpt']}"
    )
    assert head_res["result"] == "FAIL", (
        f"G1 proof: head ({HEAD_REF}) should FAIL, got {head_res['result']}\n"
        f"stderr: {head_res['stderr_excerpt']}"
    )
