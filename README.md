# Witness

A pre-merge gate and standing code auditor that **proves** when code defeats the purpose of other code.

Witness does not guess. It emits a finding only when it can produce a runnable test that demonstrates the problem.

---

## What it does

| Mode | When | Question |
|------|------|----------|
| **GATE** | A PR targets main | Does merging this defeat a guarantee main or another team already holds? |
| **STANDING** | Any other time | Does this code contradict its own documented intent, or itself? |

**Output categories:**
- **DEFEATED** — a guarantee is broken; a proof test ships with the finding
- **UNDEFENDED** — a guarantee is documented, this change touches its surface, and no test covers it
- **Silence** — nothing found worth reporting

**Forbidden:** confidence scores, "consider reviewing", "this might", severity ratings on unproven items.

---

## Architecture

```
Bob (Agent mode, orchestrator)
  ├── reads .bob/workflow.md          ← pipeline narrative
  ├── spawns ledger-agent             ← M4: extract Purpose Ledger
  ├── spawns callers/contract/intent  ← M5: impact analysis (parallel)
  ├── spawns lane-agent ×5            ← M6: write proof tests (parallel)
  └── calls python -m runner.cli      ← all deterministic steps

Python (runner/, zero LLM calls)
  ├── worktrees.py    git worktree create/teardown
  ├── execute.py      run pytest, tri-state PASS/FAIL/ERROR, 120s timeout
  ├── ledger.py       parse + persist Purpose Ledger
  ├── impact.py       parse impact agent output
  ├── candidates.py   rank top 5 candidates
  ├── race.py         parse lane output, run tests on worktrees
  ├── confirm.py      reject flaky/tautology/over-broad tests
  ├── report.py       generate markdown report + METRICS.md
  └── bench.py        benchmark harness

dashboard/ (static, zero backend)
  └── replays stored runs offline — no agent calls in demo mode
```

---

## Prerequisites

- Python 3.11+
- Git 2.20+ (for `git worktree`)
- `pip install -r sample-repo/requirements.txt` (for running tests in worktrees)

---

## Usage

```bash
# Pre-merge gate
python -m runner.cli gate \
  --repo sample-repo \
  --base main \
  --head team-a/rate-limit \
  --with team-b/retry

# Standing auditor
python -m runner.cli standing \
  --repo sample-repo \
  --ref HEAD

# Benchmark (all synthetic cases)
python -m runner.cli bench \
  --repo sample-repo

# Replay a stored run in the dashboard
python -m runner.cli replay --run <run-id>
# Then open: dashboard/index.html?run=<run-id>
```

---

## Project Structure

```
.bob/
  workflow.md            Bob pipeline narrative
  agents/
    ledger-agent.md      Purpose Ledger extraction prompt
    callers-agent.md     Transitive callers impact agent prompt
    contract-agent.md    Mechanical contract extraction prompt
    intent-agent.md      Guarantee defeat detection prompt
    lane-agent.md        Proof test writing prompt

runner/
  cli.py                 Entry point (gate|standing|bench|replay)
  schemas.py             Data contracts (Guarantee, Candidate, LaneResult, Run)
  worktrees.py           git worktree create/teardown
  execute.py             pytest runner, tri-state, 120s timeout
  ledger.py              Purpose Ledger parser + persister
  impact.py              Impact agent output parser
  candidates.py          Candidate ranking (top 5)
  race.py                Lane result collector + incremental JSON flush
  confirm.py             Rejection gates (flake, tautology, signature)
  report.py              Markdown report + METRICS.md
  bench.py               Benchmark harness

sample-repo/             Real git repo — small order service (FastAPI + SQLite)
dashboard/               Static HTML dashboard (replay only)
bench/cases/             Synthetic benchmark cases (6 cases)
docs/bob-sessions/       IBM Bob task session screenshots (submission requirement)

STATE.json               Milestone checkpoint (read on restart)
DECISIONS.md             Architecture decisions + verified Bob capabilities
METRICS.md               Run metrics log
witness-plan.md          Full implementation plan (M0–M8)
```

---

## Guarantees in the sample app

| ID | Guarantee | Covered by test? |
|----|-----------|-----------------|
| G1 | A single order request results in at most one gateway charge call | No |
| G2 | The same idempotency key creates exactly one order | Yes |
| G3 | Every order write passes through `validate_order()` | No |
| G4 | Catalog reads are served from cache; DB hit rate < 20% once warm | No |

---

## The demo scenario

- `team-a/rate-limit` — enforces G1 at the route layer (`app/api.py` + `app/limiter.py`). Green alone.
- `team-b/retry` — adds retry-with-backoff inside `app/gateway.py`. Green alone.
- **Merged: zero textual conflict, green CI — but retries multiply gateway calls beneath the route-level ceiling. G1 is defeated.**
- Witness finds it. The proof test passes on `team-a/rate-limit` and fails on the merge.

---

## IBM Bob usage

This project uses IBM Bob 2.0 as the orchestrator. Bob spawns subagents for all reasoning tasks (ledger extraction, impact analysis, proof test generation) and calls the Python runner for all deterministic steps. See `.bob/workflow.md` for the full pipeline.

**Submission:** `docs/bob-sessions/` must contain IBM Bob task session summary screenshots from each team member before submission.
