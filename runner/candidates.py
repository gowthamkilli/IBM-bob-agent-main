"""
candidates.py — rank and select the top 5 candidates for the race.

Ranking formulas (spec §8 M5):
    GATE:     rank = unguarded_call_sites * (1 if uncovered else 0.3)
    STANDING: rank = blast_radius * (1 if uncovered else 0.3)
"""
from __future__ import annotations
from runner.schemas import Candidate, Guarantee


def rank_candidates(
    impact_data: dict,
    ledger: list[Guarantee],
    mode: str,  # "gate" | "standing"
) -> list[Candidate]:
    """
    Build and rank Candidate objects from parsed impact agent output.
    Returns the top 5, distinct and non-overlapping.
    """
    callers = impact_data.get("callers", {})
    intent = impact_data.get("intent", {})
    contract = impact_data.get("contract", {})

    covered_ids = {g.id for g in ledger if g.covered_by_test is not None}
    candidates: list[Candidate] = []

    # --- GATE: cross-team guarantee defeat ---
    cross = intent.get("cross_team_defeat")
    if mode == "gate" and cross:
        gid = cross.get("guarantee_id")
        uncovered = gid not in covered_ids if gid else True
        unguarded = callers.get("unguarded_count", 0)
        score = unguarded * (1.0 if uncovered else 0.3)
        candidates.append(Candidate(
            id="C1",
            claim=f"Merging {cross.get('branch_b')} into {cross.get('branch_a')} defeats guarantee {gid}",
            guarantee_id=gid,
            fallacy_class=None,
            proof_form="differential",
            test_style="guarantee",
            rank_score=max(score, 1.0),  # floor at 1 so it stays visible
        ))

    # --- Surface guarantees touched ---
    for i, gid in enumerate(intent.get("touched_guarantees", []), start=2):
        g = next((x for x in ledger if x.id == gid), None)
        if g is None:
            continue
        uncovered = g.covered_by_test is None
        if mode == "gate":
            unguarded = callers.get("unguarded_count", 1)
            score = unguarded * (1.0 if uncovered else 0.3)
        else:
            blast = intent.get("blast_radius", 1)
            score = blast * (1.0 if uncovered else 0.3)

        pattern = intent.get("pattern", "none")
        candidates.append(Candidate(
            id=f"C{i}",
            claim=f"This change {pattern}s the enforcement of {g.statement}",
            guarantee_id=gid,
            fallacy_class=_pattern_to_fallacy(pattern),
            proof_form="differential" if mode == "gate" else "contradiction",
            test_style="guarantee",
            rank_score=score,
        ))

    # --- Unguarded call sites (structural) ---
    for j, site in enumerate(callers.get("call_sites", []), start=len(candidates) + 1):
        if site.get("guarded"):
            continue
        candidates.append(Candidate(
            id=f"C{j}",
            claim=f"Call to {site.get('symbol')} at {site.get('file')}:{site.get('line')} has no guard",
            guarantee_id=None,
            fallacy_class="defeated-enforcement",
            proof_form="impossibility",
            test_style="equivalence",
            rank_score=0.5,
        ))

    # Sort descending by rank_score, deduplicate by claim, take top 5
    seen_claims: set[str] = set()
    ranked: list[Candidate] = []
    for c in sorted(candidates, key=lambda x: x.rank_score, reverse=True):
        if c.claim not in seen_claims:
            seen_claims.add(c.claim)
            ranked.append(c)
        if len(ranked) == 5:
            break

    return ranked


def _pattern_to_fallacy(pattern: str) -> str | None:
    mapping = {
        "bypass": "defeated-enforcement",
        "weaken": "contradicted-guarantee",
        "multiply": "assumption-mismatch",
    }
    return mapping.get(pattern)
