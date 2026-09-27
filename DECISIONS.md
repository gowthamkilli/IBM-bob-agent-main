# DECISIONS

## D1 — Bob subagent and workflow capabilities (verified against bob.ibm.com/docs/ide)

**Source:** IBM Bob documentation, verified 2026-09.

### Subagent types
Bob exposes exactly **two** subagent types via `spawn_subagent`:

| Type | Model | Tools | Can write files? |
|------|-------|-------|-----------------|
| `explore` | lighter model | read-only | **No** |
| `general` | default model | full (read + write + execute + MCP) | **Yes** |

**Implication for Witness:** Lane agents and impact agents must use type `general` because they must produce executable test files. `explore` cannot write.

### Subagents vs. subtasks
| Concept | Tool | Visible in UI | Returns to parent |
|---------|------|--------------|-------------------|
| Subagent | `spawn_subagent` | No (silent background) | Summary text only |
| Subtask | `start_subtask` | Yes (own breadcrumb + thread) | Interactive |

**Implication:** A subagent returns **text only** — it cannot directly hand back a file path the parent reads. The lane agent must **return the test source as text** in its summary; the Python runner (`runner/race.py`) writes that text to disk. This is the "one extra hop" the spec anticipated.

Subagents can write files to disk via their `edit` tool group when type=`general`. However, because subagents run in an isolated context and their output back to the parent is a text summary (≤800 tokens per spec), the safest and most reliable pattern is: **lane agent returns test source text → Python runner writes the file**. This avoids races between concurrent subagents writing to the same path.

### .bob/workflow.md
Bob does not have a native "workflow file" runner that executes `.bob/workflow.md` as code. `.bob/workflow.md` is a **skill-style instruction document** that Bob reads at task start to orient itself. It is not executed line-by-line by a runtime engine.

**Implication:** `.bob/workflow.md` is authoritative narrative — the Witness pipeline described in full — but the actual orchestration happens inside a Bob Agent-mode session that reads the file and drives the milestones step by step. Bob IS the orchestrator; `.bob/agents/*.md` are the per-agent instruction prompts Bob injects when spawning each subagent.

### Parallelism
Bob can spawn multiple `spawn_subagent` calls **in a single assistant turn** (parallel tool calls). This is how M5 (three impact agents concurrently) and M6 (five lane agents concurrently) are implemented. There is no separate parallel primitive; parallel = multiple `spawn_subagent` calls in one turn.

### Modes and subagent restrictions
- **Agent mode**: may spawn `explore` and `general` subagents. Has `Execute` tool access (can run `python -m runner.cli ...`).
- **Plan mode**: may spawn `explore` and `general` subagents. No `Execute` — cannot run Python directly.

**Implication:** The Bob session that drives Witness must run in **Agent mode** so it can both spawn subagents and invoke `python -m runner.cli` for the deterministic steps.

---

## D2 — Architecture split (confirmed)

**Bob (Agent mode, orchestrator):**
- Reads `.bob/workflow.md` for the full pipeline spec
- Spawns `ledger-agent` (M4), `callers-agent` + `contract-agent` + `intent-agent` in parallel (M5), `lane-agent ×5` in parallel (M6)
- Calls `python -m runner.cli` for all deterministic steps: worktree creation, test execution, confirm gate, report generation, replay, bench
- Updates `STATE.json` after each milestone

**Python (`runner/`, fully deterministic, zero LLM calls):**
- `worktrees.py` — `git worktree add/remove`
- `execute.py` — copy test file into worktree, run pytest, return PASS/FAIL/ERROR, 120s timeout, tri-state
- `ledger.py` — persist Guarantee objects from ledger-agent output to JSON/disk
- `impact.py` — persist Candidate objects from impact-agent output
- `candidates.py` — rank and select top 5
- `race.py` — receive test source text from lane-agent summaries, write test files, invoke execute.py per lane per side
- `confirm.py` — flake/tautology/signature gate, 3× re-runs
- `report.py` — markdown report + METRICS.md
- `bench.py` — benchmark harness
- `cli.py` — CLI entry point wiring all of the above

**dashboard/ (static, zero backend):**
- Reads `dashboard/data/run-*.json` written incrementally by the runner
- `witness replay` serves the stored run for offline demos at zero agent cost

---

## D3 — Lane agent test-source handoff protocol

Lane agents have a 2000-token output cap (not 800 — the entire payload is test source). Impact agents (ledger/callers/contract/intent) remain at 800.

Each lane agent returns exactly this block:
```
LANE_ID: <lane id, e.g. L1>
CANDIDATE_ID: <candidate id, e.g. C1>
PROOF_FORM: differential | contradiction | impossibility
EXPECTED_FAILURE: <exception class or assert substring>
DEATH_NOTE: <one line — why this test would fail to prove, if it does>
TEST_SOURCE_START
<full test file content>
TEST_SOURCE_END
```
`runner/race.py` parses this format, writes the file to a temp path, then invokes `execute.py` on both worktrees. All five fields above (`LANE_ID`, `CANDIDATE_ID`, `PROOF_FORM`, `EXPECTED_FAILURE`, `DEATH_NOTE`) are required — a lane missing any of them is immediately classified INVALID.

---

## D4 — Scope cut order (per spec §9)

If forced to cut scope:
1. Benchmark table B (real git history cases) — cut first
2. team-c/bulk-endpoint case
3. Round-2 race (seeded by death_notes)
4. Suggested-test generation
5. STANDING mode

Never cut: the race, the proof gate. They are the product.

---

## D5 — STATE.json checkpoint protocol

After every milestone acceptance test passes, write:
```json
{
  "milestone": "M3",
  "status": "passed",
  "next": "M4",
  "notes": "..."
}
```
On session restart, read STATE.json and resume at `next`. Never restart from M0.

---

## D6 — G1 guarantee restatement (count-based, not rate-based)

**Original (timing-based, flaky):** "at most 5 calls/sec to the payment gateway"
**Corrected (count-based, deterministic):** "a single order request results in at most one gateway charge call"

**Why:** Wall-clock timing in a proof test is inherently flaky. `confirm.py` is designed to reject flaky tests. A timing-based hero case could be thrown out by the gate it is supposed to demonstrate. The count-based restatement is mock-counted, deterministic, and reads just as clearly.

All ADRs, docstrings, and test assertions must use the count-based form. The rate-based form must not appear anywhere in test code.

---

## D7 — Worktree import isolation (critical — FATAL if wrong)

**Problem:** If `pip install -e .` is run for the sample app, both worktrees import the same installed copy. Base and head produce identical results. Nothing is ever PROVEN. The gate is broken and the most likely "fix" is silently loosening it.

**Rule:** Never install the sample app itself. Share one venv for third-party deps only (fastapi, uvicorn, pytest, httpx). Run pytest with `cwd` set to the worktree directory so `import app` resolves from that worktree's `app/` directory.

**Harness self-check (required in M3):** Before running any real candidate, run a calibration test:
- Write a one-line test that asserts a constant that differs between base and head (e.g., a version string or a function return value that the two branches deliberately differ on).
- Run it through the harness: must return `base=PASS, head=FAIL`.
- If both sides return the same result, the harness is broken — raise a hard error, print "HARNESS ISOLATION FAILURE", and halt. Do not proceed to M4.

**Implementation in `execute.py`:**
```python
env = os.environ.copy()
env.pop("PYTHONPATH", None)  # never leak caller's path
result = subprocess.run(
    ["python", "-m", "pytest", test_file, "-x", "--tb=short"],
    cwd=worktree_path,          # ← app/ resolves from here
    env=env,
    timeout=120,
    capture_output=True,
)
```

---

## D8 — Sample app branch layering (critical — FATAL if wrong)

**Problem:** If both team-a and team-b modify `gateway.charge()` in `app/gateway.py`, git will textually conflict. The entire premise ("clean merge, green CI, broken system") collapses.

**Fix — different files, different layers:**
- `team-a/rate-limit`: enforces G1 at the **route layer** in `app/api.py` + new `app/limiter.py`. Does not touch `app/gateway.py`.
- `team-b/retry`: adds retry-with-backoff **inside `app/gateway.py`**, below the limiter enforcement point.

**Why this defeats G1:** The ceiling counts requests at the route (one call in → one charge call out). Retries multiply actual gateway calls from within `gateway.charge()` underneath the ceiling. The route-level counter never sees the retries. The guarantee is defeated and the merge is textually clean.

**Verification before M2 passes:** `git merge team-b/retry` into `team-a/rate-limit` must report zero conflicts. If it conflicts, the sample is wrong — fix the sample.

---

## D9 — M8 benchmark scope

6 synthetic cases only (not 10–15). Vary the mechanism, reuse the same `sample-repo/` surface:
1. retry defeating a route-level limiter (the demo case, re-run as bench case)
2. write-through defeating a cache guarantee
3. new bulk route bypassing a validator
4. regenerated idempotency key defeating dedup
5. sort removed upstream of code assuming order
6. a second limiter weakened to a higher ceiling than the original ADR states

Never blend synthetic and real tables. No real-history cases unless there is time after all 6 synthetic cases pass.

---

## D10 — Branch SHAs (M2, rebuilt session 2)

| Branch | SHA |
|--------|-----|
| `main` | `e8a72c45faf17bf6c78e2bf9f03ac079baeca313` |
| `team-a/rate-limit` (pre-merge) | `6d6a58e` (a8f842d after pycache cleanup) |
| `team-a/rate-limit` (after merge with team-b) | `2ce4314d4df182cdc4570ac7f15e861d83caa647` |
| `team-b/retry` | `4a06272dc7c937463480c309bdd05e6496a904b4` |
| `team-c/bulk-endpoint` | `ca2d65fa16f13e3bd46bb2c995b4284ae693789b` |

**Benchmark branches:**
| `bench/write-through-defeats-cache` | `d7e2fd0` |
| `bench/regenerated-idempotency-defeats-dedup` | `b02b37d` |
| `bench/weakened-ceiling-defeats-g1` | `7f81439` |
| `bench/unchecked-fast-path-defeats-g3` | `4b8b238` |

**Verification (session 2):**
- `team-a/rate-limit` alone: 14 passed ✓
- `team-b/retry` alone: 14 passed ✓
- Merge of team-b into team-a: zero textual conflict ✓, 14 passed ✓
- G1 defeat: harness run confirms base=PASS (pre-merge), head=FAIL (post-merge) ✓
- `team-c/bulk-endpoint` alone: 14 passed ✓
- All 6 benchmark cases: PROVEN ✓
- `witness gate --base 6d6a58e --head team-a/rate-limit --with team-b/retry`: DEFEATED | PROVEN ✓
