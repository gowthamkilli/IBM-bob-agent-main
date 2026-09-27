"""
test_m6_race.py — M6 acceptance test for the race and confirm pipeline.

Simulates what Bob lane agents return and runs the full race+confirm pipeline.
Verifies: exactly one PROVEN lane for the G1 gate scenario.

The PROVEN test must pass on team-a pre-merge (base) and fail on the merge (head).
"""
import json
import pytest
from pathlib import Path
from runner.g1_proof_test import G1_TEST_SOURCE
from runner.race import parse_lane_output, run_lane
from runner.confirm import validate_lane, is_tautology, is_over_broad
from runner.worktrees import create, teardown
from runner.schemas import LaneResult
from runner.ledger import extract_from_repo

REPO = Path(__file__).parent.parent / "sample-repo"
BASE_REF = "6d6a58e"        # team-a pre-merge (no retry)
HEAD_REF = "team-a/rate-limit"   # team-a post-merge (has retry)
OUTPUT_DIR = Path(__file__).parent.parent / "dashboard" / "data"


# Simulate what a lane agent returns (D3 protocol)
G1_LANE_OUTPUT = f"""LANE_ID: L1
CANDIDATE_ID: C1
PROOF_FORM: differential
EXPECTED_FAILURE: AssertionError
DEATH_NOTE: If _do_charge is not monkeypatched correctly the count may not register
TEST_SOURCE_START
{G1_TEST_SOURCE.strip()}
TEST_SOURCE_END"""

# A tautology lane (should be rejected)
TAUTOLOGY_LANE_OUTPUT = """LANE_ID: L2
CANDIDATE_ID: C2
PROOF_FORM: differential
EXPECTED_FAILURE: AssertionError
DEATH_NOTE: This is a tautology
TEST_SOURCE_START
def test_always_fails():
    assert False
TEST_SOURCE_END"""

# An over-broad lane (should be rejected)
OVERBROAD_LANE_OUTPUT = """LANE_ID: L3
CANDIDATE_ID: C3
PROOF_FORM: differential
EXPECTED_FAILURE: AssertionError
DEATH_NOTE: No specific assertion
TEST_SOURCE_START
import app.gateway as gw

def test_overbroad():
    pass  # no assert
TEST_SOURCE_END"""

# A lane missing required fields (should be INVALID)
INCOMPLETE_LANE_OUTPUT = """LANE_ID: L4
CANDIDATE_ID: C4
TEST_SOURCE_START
def test_something():
    assert True
TEST_SOURCE_END"""


def test_parse_lane_output_valid():
    parsed = parse_lane_output(G1_LANE_OUTPUT)
    assert not parsed.get("invalid"), f"Should be valid: {parsed}"
    assert parsed["lane_id"] == "L1"
    assert parsed["candidate_id"] == "C1"
    assert parsed["proof_form"] == "differential"
    assert parsed["expected_failure"] == "AssertionError"
    assert "test_single_order" in parsed["test_source"]


def test_parse_lane_output_missing_fields():
    parsed = parse_lane_output(INCOMPLETE_LANE_OUTPUT)
    assert parsed.get("invalid"), "Should be INVALID — missing PROOF_FORM, EXPECTED_FAILURE, DEATH_NOTE"


def test_tautology_rejected():
    assert is_tautology("def test_x():\n    assert False\n")
    assert not is_tautology(G1_TEST_SOURCE)


def test_overbroad_rejected():
    assert is_over_broad("def test_x():\n    pass\n")
    assert not is_over_broad(G1_TEST_SOURCE)


def test_g1_lane_proven():
    """
    Full race+confirm: G1 lane must return PROVEN (base=PASS, head=FAIL).
    """
    parsed = parse_lane_output(G1_LANE_OUTPUT)
    assert not parsed.get("invalid"), f"Parse failed: {parsed}"

    base_wt = create(REPO, BASE_REF, "m6-g1-base")
    head_wt = create(REPO, HEAD_REF, "m6-g1-head")
    ledger = extract_from_repo(REPO)

    try:
        result = run_lane(
            parsed=parsed,
            base_worktree=base_wt,
            head_worktree=head_wt,
            mode="gate",
            run_id="m6-test",
            output_dir=OUTPUT_DIR,
        )
        # validate_lane must run before teardown so flake re-runs work
        result = validate_lane(
            result=result,
            test_source=parsed["test_source"],
            head_worktree=head_wt,
            ledger=ledger,
            mode="gate",
        )
    finally:
        teardown(base_wt)
        teardown(head_wt)

    assert result.base_result == "PASS", f"base should PASS, got {result.base_result}\n{result.stderr_excerpt}"
    assert result.head_result == "FAIL", f"head should FAIL, got {result.head_result}\n{result.stderr_excerpt}"
    assert result.verdict == "PROVEN", f"verdict should be PROVEN, got {result.verdict}\n{result.stderr_excerpt}"

    # Verify run JSON was written
    run_file = OUTPUT_DIR / "run-m6-test.json"
    assert run_file.exists(), "Run JSON not written"
    lanes = json.loads(run_file.read_text())
    assert any(l["verdict"] == "PROVEN" for l in lanes), "No PROVEN lane in run JSON"
