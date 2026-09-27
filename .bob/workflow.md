# Witness Pipeline — Bob Workflow

This document describes the Witness pipeline end-to-end. Bob reads it at task start
to orient the entire orchestration. Steps marked **PARALLEL** must be executed as
concurrent `spawn_subagent` calls in a single assistant turn.

---

## Pipeline Overview

```
GATE mode:  base + head + [with-branches] → ledger → impact(×3 PARALLEL) → candidates → race(×5 PARALLEL) → confirm → report
STANDING mode: ref → ledger → impact(×3 PARALLEL) → candidates → race(×5 PARALLEL) → confirm → report
```

---

## Step 1 — Read STATE.json

Always start here. If `STATE.json` shows a milestone other than M0 with status=passed,
resume from the recorded `next` milestone. Never restart from M0.

---

## Step 2 — Purpose Ledger (M4)

Spawn one `general` subagent with the instructions in `.bob/agents/ledger-agent.md`.
Pass the full repository path and the ref to audit.

The agent returns a JSON array of Guarantee objects. Call:
```
python -m runner.cli standing --repo <path> --ref <ref>
```
which will invoke `runner/ledger.py` to parse, validate, and persist the ledger
to `dashboard/data/ledger.json`.

Acceptance: G1–G4 recovered with correct provenance, G1/G3/G4 have `covered_by_test: null`.

---

## Step 3 — Impact Analysis (M5) — PARALLEL

In a single assistant turn, spawn THREE `general` subagents concurrently:

1. `.bob/agents/callers-agent.md` — transitive callers of changed symbols, up to 3 hops
2. `.bob/agents/contract-agent.md` — mechanical guarantees of the old code
3. `.bob/agents/intent-agent.md` — which ledger guarantees does this change touch, and how?

Each agent returns structured JSON (≤800 tokens).

Then call:
```
python -m runner.cli gate --repo <path> --base <base> --head <head> [--with <branches>]
```
which invokes `runner/impact.py` + `runner/candidates.py` to rank and persist top 5 candidates.

Acceptance (GATE): top candidate is the G1 ceiling defeat.
Acceptance (STANDING): planted vacuous guard appears in top 5.

---

## Step 4 — Race (M6) — PARALLEL

In a single assistant turn, spawn FIVE `general` subagents concurrently,
one per candidate, each using `.bob/agents/lane-agent.md`.

Pass each agent:
- The candidate (`id`, `claim`, `guarantee_id`, `proof_form`)
- The shared surface (function signatures that exist in both refs)
- The expected failure signature

Each agent returns a D3 protocol block (≤2000 tokens):
```
LANE_ID: L<n>
CANDIDATE_ID: C<n>
PROOF_FORM: differential | contradiction | impossibility
EXPECTED_FAILURE: <exception class or assert substring>
DEATH_NOTE: <one line — why this might fail to prove>
TEST_SOURCE_START
<full pytest test file>
TEST_SOURCE_END
```

Pass all five blocks to:
```
python -m runner.cli gate --repo <path> --base <base> --head <head> [--with <branches>]
```
which invokes `runner/race.py` to write test files, execute on worktrees,
and flush each `LaneResult` to `dashboard/data/run-<id>.json` incrementally.

---

## Step 5 — Confirm gate

`runner/confirm.py` applies rejection gates automatically (called by race.py):
- Tautology, import error, signature mismatch, flake, over-broad

If zero PROVEN after round 1:
- Collect all `death_note` values
- Spawn ONE more round-2 race (five more lane agents) seeded by the death notes
- If still zero PROVEN → proceed to report with nothing as DEFEATED

---

## Step 6 — Report (M7)

```
python -m runner.cli replay --run <run-id>
```

`runner/report.py` generates the markdown report and appends to `METRICS.md`.

---

## Checkpointing

After each milestone acceptance test passes, write `STATE.json`:
```json
{"milestone": "M<n>", "status": "passed", "next": "M<n+1>", "notes": "..."}
```

On any session restart, read `STATE.json` first and resume at `next`.

---

## Scope cut order (if forced)

1. Benchmark table B (real history cases)
2. team-c/bulk-endpoint
3. Round-2 race
4. Suggested-test generation
5. STANDING mode

Never cut the race or the proof gate.
