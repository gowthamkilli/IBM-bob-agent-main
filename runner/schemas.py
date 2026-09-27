"""
Data contracts for Witness. Implement exactly per spec §5.
Do not deviate from field names or types.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Guarantee:
    id: str                          # "G1"
    statement: str                   # "a single order request results in at most one gateway charge call"
    why: str                         # "the gateway rate-limits us and bills overage"
    provenance: list[str]            # ["docs/ADR-002.md:14", "app/limiter.py:8"]
    enforced_at: list[str]           # ["app/limiter.py:22"]
    covered_by_test: str | None      # "tests/test_limits.py::test_call_ceiling" or None
    surface: list[str]               # ["app.gateway.charge", "POST /orders"]


@dataclass
class Candidate:
    id: str                          # "C3"
    claim: str                       # one sentence, falsifiable
    guarantee_id: str | None
    fallacy_class: str | None        # from taxonomy, STANDING only
    proof_form: str                  # differential | contradiction | impossibility
    test_style: str                  # equivalence | guarantee
    rank_score: float


@dataclass
class LaneResult:
    lane_id: str
    candidate_id: str
    test_path: str
    expected_failure: dict[str, Any]  # {"exception": str | None, "assert_substring": str}
    base_result: str | None           # PASS | FAIL | ERROR | None (standing mode)
    head_result: str                  # PASS | FAIL | ERROR
    verdict: str                      # PROVEN | DISPROVEN | INCONCLUSIVE | INVALID
    stderr_excerpt: str               # <= 400 chars
    elapsed_s: float
    death_note: str                   # one line, why it died; seeds round 2


@dataclass
class RunMetrics:
    wall_clock_s: float
    lanes_total: int
    lanes_proven: int
    lanes_disproven: int
    lanes_inconclusive: int
    lanes_invalid: int


@dataclass
class RunFindings:
    defeated: list[dict[str, Any]] = field(default_factory=list)
    undefended: list[dict[str, Any]] = field(default_factory=list)
    disproven: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Run:
    run_id: str
    mode: str                        # gate | standing
    base_sha: str | None
    head_sha: str
    branches: list[str]
    ledger: list[Guarantee]
    candidates: list[Candidate]
    lanes: list[LaneResult]
    findings: RunFindings
    metrics: RunMetrics
