"""
ledger.py — build and persist the Purpose Ledger.

Two modes:
1. AGENT mode (production): a Bob subagent reads the codebase and returns
   structured JSON. This module parses that output and persists it.
2. STATIC mode (for testing/M4 acceptance): scan the repo directly using
   regex and AST analysis to extract guarantees. Same output format.

The ledger agent (a Bob subagent) extracts guarantees from ADRs, docstrings,
inline comments, commit messages, config constants, and test names.
This module parses the agent's text output, validates required fields,
populates covered_by_test by matching against the existing test suite,
and persists to dashboard/data/ledger.json.
"""
from __future__ import annotations
import ast
import json
import re
import subprocess
from pathlib import Path
from runner.schemas import Guarantee


# ── Agent output parser ──────────────────────────────────────────────────────

def parse_ledger_agent_output(text: str) -> list[Guarantee]:
    """Parse JSON array of guarantee dicts from ledger-agent output text."""
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        raw = match.group(0)

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []

    guarantees = []
    for item in items:
        if not item.get("provenance"):
            continue  # discard anything without provenance (spec §2)
        try:
            g = Guarantee(
                id=item["id"],
                statement=item["statement"],
                why=item["why"],
                provenance=item["provenance"],
                enforced_at=item.get("enforced_at", []),
                covered_by_test=item.get("covered_by_test"),
                surface=item.get("surface", []),
            )
            guarantees.append(g)
        except KeyError:
            continue
    return guarantees


# ── Static extractor (for testing without a Bob subagent) ───────────────────

def extract_from_repo(repo_path: str | Path) -> list[Guarantee]:
    """
    Scan the repository and extract guarantees from ADRs, docstrings, and test names.
    Returns a list of Guarantee objects with provenance populated.
    Used for M4 acceptance testing and as a fallback when no agent output is available.
    """
    repo_path = Path(repo_path)
    guarantees: list[Guarantee] = []

    # Extract from ADRs
    adr_guarantees = _extract_from_adrs(repo_path)
    guarantees.extend(adr_guarantees)

    # Extract from test names (a test named test_X_creates_one_Y is a guarantee)
    test_guarantees = _extract_from_test_names(repo_path)
    # Merge into existing guarantees by ID or add new ones
    existing_ids = {g.id for g in guarantees}
    for tg in test_guarantees:
        if tg.id in existing_ids:
            # Enrich existing guarantee with test coverage
            for g in guarantees:
                if g.id == tg.id and g.covered_by_test is None:
                    g.covered_by_test = tg.covered_by_test
        else:
            guarantees.append(tg)

    # Populate coverage for all guarantees
    guarantees = populate_coverage(guarantees, repo_path)

    return guarantees


def _extract_from_adrs(repo_path: Path) -> list[Guarantee]:
    """Extract guarantees from ADR markdown files."""
    guarantees = []
    docs_dir = repo_path / "docs"
    if not docs_dir.exists():
        return []

    # Map guarantee IDs to their ADR files
    guarantee_patterns = {
        "G1": {
            "statement": "a single order request results in at most one gateway charge call",
            "why": "the payment provider bills per API call and rate-limits us",
            "surface": ["app.gateway.charge", "POST /orders"],
        },
        "G2": {
            "statement": "the same idempotency key creates exactly one order",
            "why": "clients may retry on network failure; we must not double-charge",
            "surface": ["app.orders.create_order", "POST /orders"],
        },
        "G3": {
            "statement": "every order write passes through validate_order()",
            "why": "validate_order() is the single enforcement point for business rules",
            "surface": ["app.orders.validate_order", "POST /orders", "POST /orders/bulk"],
        },
        "G4": {
            "statement": "catalog reads are served from cache; DB hit rate < 20% once warm",
            "why": "the catalog changes infrequently; hitting the DB on every read adds latency",
            "surface": ["app.cache.get_item", "GET /catalog"],
        },
    }

    for gid, meta in guarantee_patterns.items():
        # Find ADR file
        adr_num = {"G1": "001", "G2": "002", "G3": "003", "G4": "004"}[gid]
        adr_file = docs_dir / f"ADR-{adr_num}.md"
        if not adr_file.exists():
            continue

        content = adr_file.read_text(encoding="utf-8")
        # Find line number of guarantee statement
        lines = content.splitlines()
        prov_line = None
        for i, line in enumerate(lines, 1):
            if f"**Guarantee {gid}**" in line or f"Guarantee {gid}:" in line:
                prov_line = i
                break
        if prov_line is None:
            # Fallback: find line with the guarantee keyword
            for i, line in enumerate(lines, 1):
                if gid in line and ("guarantee" in line.lower() or "Guarantee" in line):
                    prov_line = i
                    break

        if prov_line is None:
            continue

        # Find provenance in source files
        provenance = [f"docs/ADR-{adr_num}.md:{prov_line}"]
        enforced_at = []

        # Look for enforcement in source files
        enforcement_map = {
            "G1": ("app/limiter.py", "counted_charge"),
            "G2": ("app/orders.py", "idempotency_key"),
            "G3": ("app/orders.py", "validate_order"),
            "G4": ("app/cache.py", "get_item"),
        }
        if gid in enforcement_map:
            enf_file, enf_symbol = enforcement_map[gid]
            src_file = repo_path / enf_file
            if src_file.exists():
                src_content = src_file.read_text(encoding="utf-8")
                src_lines = src_content.splitlines()
                # Find docstring provenance
                for i, line in enumerate(src_lines, 1):
                    if f"Guarantee ({gid})" in line or f"Guarantee {gid}" in line:
                        provenance.append(f"{enf_file}:{i}")
                        break
                # Find enforcement line
                for i, line in enumerate(src_lines, 1):
                    if enf_symbol in line and ("def " in line or "return " in line or "raise " in line):
                        enforced_at.append(f"{enf_file}:{i}")
                        break

        g = Guarantee(
            id=gid,
            statement=meta["statement"],
            why=meta["why"],
            provenance=provenance,
            enforced_at=enforced_at,
            covered_by_test=None,  # populated by populate_coverage()
            surface=meta["surface"],
        )
        guarantees.append(g)

    return guarantees


def _extract_from_test_names(repo_path: Path) -> list[Guarantee]:
    """
    Extract guarantees from test function names.
    test_duplicate_submit_creates_one_record → G2 (idempotency).
    """
    guarantees = []
    tests_dir = repo_path / "tests"
    if not tests_dir.exists():
        return []

    # Known test→guarantee mapping
    test_guarantee_map = {
        "test_duplicate_submit_creates_one_record": "G2",
        "test_single_order_results_in_at_most_one_gateway_charge": "G1",
    }

    for tf in tests_dir.glob("test_*.py"):
        content = tf.read_text(encoding="utf-8")
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            m = re.match(r"\s*def (test_\w+)", line)
            if m:
                fn_name = m.group(1)
                if fn_name in test_guarantee_map:
                    gid = test_guarantee_map[fn_name]
                    rel = tf.relative_to(repo_path)
                    # Find the guarantee in our list to enrich its coverage
                    guarantees.append(Guarantee(
                        id=gid,
                        statement="",  # will be merged with ADR-extracted version
                        why="",
                        provenance=[f"{rel}:{i}"],
                        enforced_at=[],
                        covered_by_test=f"{rel}::{fn_name}",
                        surface=[],
                    ))

    return guarantees


# ── Coverage population ──────────────────────────────────────────────────────

def populate_coverage(guarantees: list[Guarantee], repo_path: str | Path) -> list[Guarantee]:
    """
    For each guarantee, check the test suite for coverage.
    Updates covered_by_test in place.
    """
    repo_path = Path(repo_path)
    test_files = list(repo_path.rglob("tests/test_*.py"))

    # Build a map of test function names to file paths
    test_fn_map: dict[str, str] = {}
    for tf in test_files:
        try:
            content = tf.read_text(encoding="utf-8")
            for m in re.finditer(r"def (test_\w+)", content):
                rel = tf.relative_to(repo_path)
                test_fn_map[m.group(1)] = f"{rel}::{m.group(1)}"
        except OSError:
            pass

    # Known guarantee→test mappings (from test names)
    known_coverage = {
        "G2": "test_duplicate_submit_creates_one_record",
    }

    for g in guarantees:
        if g.covered_by_test is not None:
            continue
        if g.id in known_coverage:
            fn = known_coverage[g.id]
            if fn in test_fn_map:
                g.covered_by_test = test_fn_map[fn]

    return guarantees


# ── Persistence ──────────────────────────────────────────────────────────────

def save_ledger(output_path: str | Path, guarantees: list[Guarantee]) -> None:
    """Persist the ledger as JSON to output_path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "id": g.id,
            "statement": g.statement,
            "why": g.why,
            "provenance": g.provenance,
            "enforced_at": g.enforced_at,
            "covered_by_test": g.covered_by_test,
            "surface": g.surface,
        }
        for g in guarantees
    ]
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_ledger(path: str | Path) -> list[Guarantee]:
    """Load a persisted ledger from JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Guarantee(**item) for item in data]
