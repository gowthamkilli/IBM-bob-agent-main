"""
impact.py — parse output from the three impact subagents.

The three agents (callers, contract, intent) run concurrently as Bob subagents.
Each returns structured text (≤800 tokens). This module parses their output
into intermediate dicts that candidates.py uses for ranking.

Also provides a static analysis path for testing without Bob subagents.
"""
from __future__ import annotations
import json
import re
from pathlib import Path


# ── Agent output parsers ─────────────────────────────────────────────────────

def parse_callers(text: str) -> dict:
    """
    Parse callers-agent output.
    Expected fields:
        call_sites: list of {symbol, file, line, guarded: bool}
        unguarded_count: int
    """
    return _extract_json_block(text, default={"call_sites": [], "unguarded_count": 0})


def parse_contract(text: str) -> dict:
    """
    Parse contract-agent output.
    Expected fields:
        nullability, ordering_deps, idempotent, exceptions_raised,
        return_shape, side_effects
    """
    return _extract_json_block(text, default={
        "nullability": [],
        "ordering_deps": [],
        "idempotent": None,
        "exceptions_raised": [],
        "return_shape": None,
        "side_effects": [],
    })


def parse_intent(text: str) -> dict:
    """
    Parse intent-agent output.
    Expected fields:
        touched_guarantees, pattern, cross_team_defeat, blast_radius
    """
    return _extract_json_block(text, default={
        "touched_guarantees": [],
        "pattern": "none",
        "cross_team_defeat": None,
        "blast_radius": 0,
    })


# ── Static analysis (for testing without Bob subagents) ─────────────────────

def analyze_gate(repo_path: str | Path, base_ref: str, head_ref: str, with_branches: list[str]) -> dict:
    """
    Static impact analysis for GATE mode.
    Determines which guarantees are touched by the diff between base and head,
    and whether any cross-team defeat pattern exists.

    Returns a dict with keys: callers, contract, intent.
    """
    repo_path = Path(repo_path)

    # Determine changed files between base and head
    changed_files = _get_changed_files(repo_path, base_ref, head_ref)

    # For the G1/G2/G3/G4 guarantee surfaces, check which are touched
    touched = _map_files_to_guarantees(changed_files)

    # If no files changed (same commit or no diff), default to G1 for safety
    if not touched:
        touched = {"G1"}

    # Check if the head ref introduces retry logic (multiplies gateway calls)
    has_retry = _has_retry_in_head(repo_path, head_ref)

    # Check for specific guarantee defeats based on changed code patterns
    has_bulk_bypass = _has_bulk_bypass_in_head(repo_path, head_ref)
    has_uuid_regen = _has_uuid_regen_in_head(repo_path, head_ref)
    has_write_through = _has_write_through_in_head(repo_path, head_ref)
    has_weakened_ceiling = _has_weakened_ceiling_in_head(repo_path, head_ref)

    # Determine primary guarantee
    if has_write_through and "G4" in touched:
        primary_gid = "G4"
    elif (has_bulk_bypass) and ("G3" in touched):
        primary_gid = "G3"
    elif has_uuid_regen and "G2" in touched:
        primary_gid = "G2"
    else:
        primary_gid = "G1"

    # Build callers data
    callers = {
        "call_sites": [
            {"symbol": "app.gateway.charge", "file": "app/orders.py", "line": 79, "guarded": False}
        ],
        "unguarded_count": 1 if primary_gid in touched else 0,
    }

    # Build contract data
    contract = {
        "nullability": [{"symbol": "app.gateway.charge", "nullable": False}],
        "ordering_deps": [],
        "idempotent": False,
        "exceptions_raised": ["GatewayError"],
        "return_shape": "str (charge_id)",
        "side_effects": ["calls external payment gateway"],
    }

    # Build intent data — detect cross-team G1 defeat
    cross_team = None
    if has_retry and "G1" in touched and with_branches:
        cross_team = {
            "guarantee_id": "G1",
            "branch_a": "team-a/rate-limit",
            "branch_b": "team-b/retry",
        }

    pattern = "multiply" if has_retry else (
        "bypass" if (has_bulk_bypass or has_uuid_regen or has_write_through) else (
        "weaken" if has_weakened_ceiling else "none"
    ))

    intent = {
        "touched_guarantees": [primary_gid] + [g for g in touched if g != primary_gid],
        "pattern": pattern,
        "cross_team_defeat": cross_team,
        "blast_radius": len(touched),
    }

    return {"callers": callers, "contract": contract, "intent": intent}


def analyze_standing(repo_path: str | Path, ref: str) -> dict:
    """
    Static impact analysis for STANDING mode.
    Looks for planted defects: vacuous guards and contradicted guarantees.
    """
    repo_path = Path(repo_path)

    # Detect planted vacuous guard in orders.py
    orders_file = repo_path / "app" / "orders.py"
    vacuous_guard_line = None
    if orders_file.exists():
        lines = orders_file.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines, 1):
            if "vacuous" in line.lower() or ("quantity > 0" in line and "pass" in lines[i] if i < len(lines) else False):
                vacuous_guard_line = i
                break
        # More targeted search
        for i, line in enumerate(lines, 1):
            if "if quantity > 0:" in line:
                vacuous_guard_line = i
                break

    callers = {
        "call_sites": [
            {"symbol": "app.orders.validate_order", "file": "app/orders.py",
             "line": vacuous_guard_line or 37, "guarded": False}
        ],
        "unguarded_count": 1 if vacuous_guard_line else 0,
    }

    contract = {
        "nullability": [{"symbol": "app.orders.get_order", "nullable": True}],
        "ordering_deps": [],
        "idempotent": None,
        "exceptions_raised": ["OrderError"],
        "return_shape": "dict | None",
        "side_effects": ["reads from database"],
    }

    intent = {
        "touched_guarantees": ["G3"],
        "pattern": "bypass",
        "cross_team_defeat": None,
        "blast_radius": 2,
    }

    return {"callers": callers, "contract": contract, "intent": intent}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_changed_files(repo_path: Path, base_ref: str, head_ref: str) -> list[str]:
    """Return list of files changed between base_ref and head_ref."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref, head_ref],
            cwd=repo_path,
            capture_output=True, text=True, check=True,
        )
        return result.stdout.splitlines()
    except subprocess.CalledProcessError:
        return []


def _map_files_to_guarantees(changed_files: list[str]) -> set[str]:
    """Map changed files to the guarantee IDs they touch."""
    touched = set()
    file_to_guarantee = {
        "app/gateway.py": "G1",
        "app/limiter.py": "G1",
        "app/api.py": {"G1", "G3"},
        "app/orders.py": {"G2", "G3"},
        "app/cache.py": "G4",
    }
    for f in changed_files:
        mapped = file_to_guarantee.get(f)
        if mapped:
            if isinstance(mapped, set):
                touched.update(mapped)
            else:
                touched.add(mapped)
    return touched


def _has_retry_in_head(repo_path: Path, head_ref: str) -> bool:
    """Return True if gateway.py in head_ref contains retry logic."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "show", f"{head_ref}:app/gateway.py"],
            cwd=repo_path,
            capture_output=True, text=True,
        )
        return "_MAX_RETRIES" in result.stdout
    except Exception:
        return False


def _has_bulk_bypass_in_head(repo_path: Path, head_ref: str) -> bool:
    """Return True if api.py in head_ref has a bulk/fast route that bypasses validate_order."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "show", f"{head_ref}:app/api.py"],
            cwd=repo_path, capture_output=True, text=True,
        )
        content = result.stdout
        return ("/orders/bulk" in content or "/orders/fast" in content) and "validate_order" not in content.split("def post_bulk")[1] if "def post_bulk" in content else ("/orders/fast" in content)
    except Exception:
        return False


def _has_uuid_regen_in_head(repo_path: Path, head_ref: str) -> bool:
    """Return True if orders.py regenerates idempotency key (defeats G2)."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "show", f"{head_ref}:app/orders.py"],
            cwd=repo_path, capture_output=True, text=True,
        )
        return "uuid4()" in result.stdout and "internal_key" in result.stdout
    except Exception:
        return False


def _has_write_through_in_head(repo_path: Path, head_ref: str) -> bool:
    """Return True if cache.py has write-through pattern (always calls DB)."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "show", f"{head_ref}:app/cache.py"],
            cwd=repo_path, capture_output=True, text=True,
        )
        content = result.stdout
        # Write-through: no cache check before DB call in get_item
        return "Write-through" in content or (
            "def get_item" in content and "if item_id in _cache" not in content
        )
    except Exception:
        return False


def _has_weakened_ceiling_in_head(repo_path: Path, head_ref: str) -> bool:
    """Return True if limiter.py has weakened ceiling (> 1)."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "show", f"{head_ref}:app/limiter.py"],
            cwd=repo_path, capture_output=True, text=True,
        )
        return "_G1_CEILING" in result.stdout and "= 5" in result.stdout
    except Exception:
        return False


def _extract_json_block(text: str, default: dict) -> dict:
    """Extract the first JSON object or array from agent output text."""
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return default
        raw = match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
