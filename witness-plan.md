# Witness — Implementation Plan

## Top-Level Overview

**Goal:** Build "Witness" — a pre-merge gate and standing code auditor that proves (with a runnable test) when code defeats the purpose of other code.

**Scope:** Implement all 9 milestones (M0–M8) as specified in `richtext_converted_to_markdown (5).md`. The TypeScript files (`src/`) remain untouched — they are the IBM Bob agent config layer.

**Architecture split (per DECISIONS.md D2):**
- **Bob = orchestrator** — spawns subagents (ledger, impact×3, lane×5), calls `python -m runner.cli` for deterministic steps
- **Python = deterministic engine** — worktrees, test execution, ranking, confirm gate, reporting; zero LLM calls
- **dashboard/ = static replay** — reads stored JSON, zero agent calls at demo time

**Constraint:** Work in milestone order M0→M8. Do not start a milestone until the previous acceptance test passes. After each milestone: run acceptance test, write STATE.json, post ≤3-line status.

---

## Sub-Task 1 — M0: Scaffold

**Intent:** Create the full directory tree from spec §4, implement `runner/schemas.py` (all data contracts from spec §5), and wire `runner/cli.py` with four no-op subcommands.

**Expected Outcomes:**
- All directories and stub files exist exactly as in spec §4
- `runner/schemas.py` defines `Guarantee`, `Candidate`, `LaneResult`, `Run` as dataclasses matching spec §5 field-for-field
- `python -m runner.cli --help` exits 0 and lists: `gate`, `standing`, `bench`, `replay`
- `STATE.json` written: `{"milestone": "M0", "status": "passed", "next": "M1"}`

**Todo List:**
- [ ] Create all directories: `.bob/agents/`, `runner/`, `sample-repo/`, `dashboard/data/`, `bench/cases/`, `docs/bob-sessions/`
- [ ] Write `.bob/workflow.md` — full Witness pipeline narrative (Bob reads this to orient itself)
- [ ] Write `.bob/agents/ledger-agent.md`, `callers-agent.md`, `contract-agent.md`, `intent-agent.md`, `lane-agent.md` — subagent instruction prompts
- [ ] Write `runner/__init__.py`
- [ ] Write `runner/schemas.py` — all 4 dataclasses exactly per spec §5
- [ ] Write `runner/cli.py` — argparse with 4 subcommands (gate, standing, bench, replay), all no-op stubs
- [ ] Write `runner/worktrees.py`, `runner/execute.py`, `runner/ledger.py`, `runner/impact.py`, `runner/candidates.py`, `runner/race.py`, `runner/confirm.py`, `runner/report.py`, `runner/bench.py` — empty stubs with module docstrings
- [ ] Write `dashboard/index.html`, `dashboard/app.js`, `dashboard/style.css` — empty stubs
- [ ] Write `METRICS.md` — header row only
- [ ] Write `STATE.json` — initial `{"milestone": "M0", "status": "in-progress", "next": "M0"}`
- [ ] Run acceptance test: `python -m runner.cli --help`
- [ ] Update `STATE.json` to M0 passed

**Relevant Context:**
- Spec §4: exact directory tree
- Spec §5: exact data contracts
- Spec §6: CLI contract (gate/standing/bench/replay subcommands)
- `DECISIONS.md` D1: `.bob/workflow.md` is a narrative skill doc, not an executable

**Status:** [ ] pending

---

## Sub-Task 2 — M1: Sample app on main

**Intent:** Create `sample-repo/` as a real git repository with FastAPI order service, ADRs, docstrings, planted defects, and a green pytest suite on `main`.

**Expected Outcomes:**
- `sample-repo/` is a real git repo (`git init`, at least 3 commits with meaningful messages)
- `pytest` inside `sample-repo/` is green on `main`
- Modules present: `app/api.py`, `app/orders.py`, `app/gateway.py`, `app/cache.py`, `app/db.py`, `tests/`, `docs/ADR-001..004.md`
- G1 restated as count-based: "a single order request results in at most one gateway charge call" — no wall-clock timing anywhere (see DECISIONS.md D6)
- G1–G4 guarantees each stated in an ADR AND a docstring; G1, G3, G4 deliberately have no test coverage
- Planted: one vacuous-guard in `orders.py`, one contradicted-guarantee (docstring promises non-null, path can return None)
- `STATE.json` updated: M1 passed

**Todo List:**
- [ ] `git init sample-repo && cd sample-repo`
- [ ] Write `app/db.py` — sqlite3 setup
- [ ] Write `app/gateway.py` — payment gateway stub (no rate limiter yet); G1 docstring uses count form: "at most one charge call per order request"
- [ ] Write `app/cache.py` — in-memory catalog cache; docstring for G4
- [ ] Write `app/orders.py` — create/validate order logic; docstring for G2 and G3; plant vacuous-guard and contradicted-guarantee
- [ ] Write `app/api.py` — FastAPI routes wiring the above
- [ ] Write `docs/ADR-001.md` through `docs/ADR-004.md` — one ADR per guarantee G1–G4 with file:line provenance; G1 ADR uses count form (not rate form)
- [ ] Write `tests/test_orders.py` — covers G2 (idempotency); does NOT cover G1, G3, G4
- [ ] Write `tests/test_api.py` — basic route tests
- [ ] Write `requirements.txt` — fastapi, uvicorn, pytest, httpx
- [ ] `git add -A && git commit -m "feat: initial order service with ADRs"`
- [ ] Additional meaningful commits (at least 2 more)
- [ ] Run `pytest` inside `sample-repo/` — must be green
- [ ] Update `STATE.json` M1 passed

**Relevant Context:**
- Spec §7: exact module list, guarantee table (G1–G4), planted defects
- Guarantee coverage: G2 = yes, G1/G3/G4 = no test on main
- Keep total under ~400 lines

**Status:** [ ] pending

---

## Sub-Task 3 — M2: The branches

**Intent:** Create three branches demonstrating the cross-team scenario: each branch green alone, the G1-defeating merge has zero textual conflict and a green suite — but actually defeats G1 at runtime.

**Expected Outcomes:**
- `team-a/rate-limit` branch: enforces G1 at the **route layer** in `app/api.py` + new `app/limiter.py`; does NOT touch `app/gateway.py`; green alone
- `team-b/retry` branch: adds retry-with-backoff **inside `app/gateway.py`** below the limiter; does NOT touch `app/api.py` or `app/limiter.py`; green alone
- `git merge team-b/retry` into `team-a/rate-limit`: **zero textual conflict** (different files), merged suite green — but retries multiply actual gateway calls beneath the route-level ceiling, defeating G1
- `team-c/bulk-endpoint` branch: POST `/orders/bulk` that writes orders directly, bypassing `validate_order()`, defeating G3
- All 4 SHAs recorded in `DECISIONS.md`
- `STATE.json` updated: M2 passed

**Todo List:**
- [ ] `git checkout -b team-a/rate-limit` — add `app/limiter.py` (call counter per order); wire counter into `app/api.py` POST /orders route only; do NOT touch `app/gateway.py`; update ADR-002; commit
- [ ] `git checkout main && git checkout -b team-b/retry` — add retry-with-backoff loop **inside `app/gateway.py`** `charge()` function only; do NOT touch `app/api.py` or `app/limiter.py`; commit
- [ ] Verify each branch green: `pytest` passes on each alone
- [ ] `git checkout team-a/rate-limit && git merge team-b/retry` — **must report zero conflicts** (different files modified); if conflict, fix the sample not the runner
- [ ] Verify merged suite still green; confirm G1 defeat: counter sees 1 call but gateway internally retries N times
- [ ] `git checkout main && git checkout -b team-c/bulk-endpoint` — add `POST /orders/bulk` route in `api.py` that calls `db` directly without `validate_order()`; commit
- [ ] Record all 4 SHAs in `DECISIONS.md`
- [ ] Update `STATE.json` M2 passed

**Relevant Context:**
- DECISIONS.md D8: different-file layering is the key — FATAL if both branches touch the same function
- Spec §7: "git merge produces zero textual conflict and a fully green test suite — but the retries route around the limiter"
- Critical: if merged suite goes red, fix the sample — not the runner (spec §8 M2)
- team-c defeats G3 for the benchmark

**Status:** [ ] pending

---

## Sub-Task 4 — M3: Differential execution harness

**Intent:** Implement `worktrees.py` and `execute.py` — the highest-risk piece. Prove the harness correctly classifies base=PASS, head=FAIL for the G1 scenario.

**Expected Outcomes:**
- `worktrees.py`: creates `.wt/base` and `.wt/head` via `git worktree add`; tears them down cleanly; never runs `git checkout/stash/reset` on main tree
- `execute.py`: copies one test file into a worktree, runs pytest, returns `PASS | FAIL | ERROR`; import/collection error = ERROR (never FAIL); hard 120s timeout → INCONCLUSIVE
- Hand-written test asserting G1 call ceiling: runs base=`team-a/rate-limit` → PASS, head=merge → FAIL
- `STATE.json` updated: M3 passed

**Todo List:**
- [ ] Implement `runner/worktrees.py` — `create(repo, ref, slot)` → path; `teardown(path)`; uses `subprocess` + `git worktree add`
- [ ] Implement `runner/execute.py` — `run_test(worktree_path, test_file_content, test_filename)` → `{"result": PASS|FAIL|ERROR|INCONCLUSIVE, "stderr_excerpt": str, "elapsed_s": float}`
- [ ] Handle tri-state: exit 0 = PASS, exit 1 = FAIL, collection/import error in stderr = ERROR, timeout = INCONCLUSIVE
- [ ] Share one venv for third-party deps only — **never `pip install -e .`** the sample app; `cwd=worktree_path` so `import app` resolves locally; clear `PYTHONPATH` before each run (DECISIONS.md D7)
- [ ] Implement harness self-check: write a calibration test asserting a constant that differs between base and head; run it through the harness; if both sides return the same result → print "HARNESS ISOLATION FAILURE" and halt; do not proceed to M4
- [ ] Write `tests/test_g1_ceiling.py` (hand-written) — mock `gateway.charge`, submit one order, assert mock called exactly once; **no wall-clock timing** (DECISIONS.md D6)
- [ ] Run harness: base=`team-a/rate-limit`, head=merge SHA → must report `base=PASS, head=FAIL`
- [ ] Update `STATE.json` M3 passed

**Relevant Context:**
- Spec §8 M3: "Nothing downstream works until this does"
- Must use `git worktree add`, never `git checkout` on main tree
- 120s hard kill; timeout → INCONCLUSIVE
- DECISIONS.md D7: `cwd=worktree_path` + clear `PYTHONPATH` + never install app — **FATAL if skipped**
- DECISIONS.md D6: G1 proof test is mock-counted, not timing-based
- DECISIONS.md D3: test file content comes as text, runner writes it to disk

**Status:** [ ] pending

---

## Sub-Task 5 — M4: Purpose Ledger

**Intent:** Implement `runner/ledger.py` and `.bob/agents/ledger-agent.md`. The ledger agent extracts guarantees from ADRs, docstrings, inline comments, commit messages, and test names. Python persists and validates the output.

**Expected Outcomes:**
- Running against `main` recovers G1–G4 with correct `provenance` file:line
- G1, G3, G4 correctly have `covered_by_test: null`; G2 correctly has `covered_by_test` pointing to the test
- Any candidate without provenance is discarded (not persisted)
- `runner/ledger.py` has `parse_ledger_agent_output(text) -> list[Guarantee]` and `save_ledger(path, guarantees)`
- `STATE.json` updated: M4 passed

**Todo List:**
- [ ] Write `.bob/agents/ledger-agent.md` — instruction prompt: scan ADRs, docstrings, inline comments, commit messages, test names; output structured JSON per Guarantee schema; require provenance file:line; discard anything without provenance
- [ ] Implement `runner/ledger.py` — parse agent text output, validate required fields, populate `covered_by_test` by matching against test file contents, persist to `dashboard/data/ledger.json`
- [ ] Wire `witness standing --ref HEAD` to invoke ledger step in `cli.py`
- [ ] Run acceptance test: ledger against `main` produces G1–G4 with correct provenance and coverage flags
- [ ] Update `STATE.json` M4 passed

**Relevant Context:**
- Spec §8 M4: "a test called test_duplicate_submit_creates_one_record is a written-down guarantee"
- `DECISIONS.md` D3: agent returns structured text, Python parses it
- Guarantee schema: `id, statement, why, provenance, enforced_at, covered_by_test, surface`

**Status:** [ ] pending

---

## Sub-Task 6 — M5: Impact analysis and candidate ranking

**Intent:** Implement `runner/impact.py` and `runner/candidates.py` plus three agent prompt files. Three impact agents run concurrently (parallel `spawn_subagent` calls). Python ranks and selects top 5 candidates.

**Expected Outcomes:**
- On the merge (team-a + team-b), top-ranked candidate is the G1 ceiling defeat
- On `standing --ref main`, the planted vacuous guard appears in top 5
- `runner/impact.py` orchestrates agent output parsing, `runner/candidates.py` implements ranking formula
- GATE rank: `unguarded_call_sites × (1 if uncovered else 0.3)`
- STANDING rank: `blast_radius × (1 if uncovered else 0.3)`
- `STATE.json` updated: M5 passed

**Todo List:**
- [ ] Write `.bob/agents/callers-agent.md` — transitive callers up to 3 hops, flag unguarded call sites
- [ ] Write `.bob/agents/contract-agent.md` — extract mechanical guarantees: nullability, ordering, idempotence, exceptions, return shape, side effects
- [ ] Write `.bob/agents/intent-agent.md` — match changed surface to ledger guarantees; identify bypass/weaken/multiply patterns; GATE mode: does branch B defeat a guarantee branch A introduces?
- [ ] Implement `runner/impact.py` — `parse_callers(text)`, `parse_contract(text)`, `parse_intent(text)` → intermediate dicts
- [ ] Implement `runner/candidates.py` — `rank_candidates(impact_data, ledger, mode) -> list[Candidate]` top 5
- [ ] Wire into `cli.py` gate and standing subcommands
- [ ] Run acceptance test: merge → G1 tops the list; `standing main` → vacuous guard in top 5
- [ ] Update `STATE.json` M5 passed

**Relevant Context:**
- Spec §8 M5: "PARALLEL — use subagents for any step marked PARALLEL"
- Three agents concurrently = three `spawn_subagent` calls in one Bob turn
- Candidate schema: `id, claim, guarantee_id, fallacy_class, proof_form, test_style, rank_score`

**Status:** [ ] pending

---

## Sub-Task 7 — M6: Race and confirm

**Intent:** Implement `runner/race.py` and `runner/confirm.py`. Five lane agents run concurrently, each returning test source text. Python writes test files, runs them, validates verdicts.

**Expected Outcomes:**
- `witness gate --base main --head team-a/rate-limit --with team-b/retry` returns exactly one PROVEN lane
- The PROVEN test passes on `team-a/rate-limit` and fails on the merge when run by hand
- confirm.py rejects: flaky tests, tautologies (`assert False`), import errors, wrong failure signature, over-broad tests
- Zero PROVEN after round 1 → one round-2 race seeded by death_notes; still zero → proceed to M7 with nothing as DEFEATED
- Each lane result flushed to `dashboard/data/run-<id>.json` incrementally
- `STATE.json` updated: M6 passed

**Todo List:**
- [ ] Write `.bob/agents/lane-agent.md` — instruction prompt: write one executable pytest test; return full D3 block (`LANE_ID`, `CANDIDATE_ID`, `PROOF_FORM`, `EXPECTED_FAILURE`, `DEATH_NOTE`, `TEST_SOURCE_START...END`); never modify application source; use only shared surface; output cap is 2000 tokens (not 800)
- [ ] Implement `runner/race.py` — parse lane agent summaries (per D3 protocol), write test files to tmp, invoke `execute.py` on both worktrees, collect `LaneResult` objects, flush each to JSON incrementally
- [ ] Implement `runner/confirm.py` — rejection gates: tautology, import error, signature mismatch, flake (3× re-run), over-broad; survivors re-run 3×; classify PROVEN/DISPROVEN/INCONCLUSIVE/INVALID
- [ ] Wire round-2 race: if zero PROVEN, collect death_notes, spawn second lane race with those as seeds
- [ ] Wire into `cli.py` gate subcommand
- [ ] Run acceptance test: gate command → exactly one PROVEN; verify test manually
- [ ] Update `STATE.json` M6 passed

**Relevant Context:**
- Spec §8 M6: "A failing test with no guarantee behind it is just a failing test. Discard it."
- DECISIONS.md D3 (updated): lane agent returns full block: `LANE_ID`, `CANDIDATE_ID`, `PROOF_FORM`, `EXPECTED_FAILURE`, `DEATH_NOTE`, `TEST_SOURCE_START...END`; all 5 fields required; missing any = INVALID
- Lane agent output cap: 2000 tokens (not 800)
- PROVEN (GATE): base=PASS and head=FAIL, failure matches declared signature
- Each lane result flushed incrementally — not at end of run

**Status:** [ ] pending

---

## Sub-Task 8 — M7: Report and dashboard

**Intent:** Implement `runner/report.py` and the static dashboard. Report produces PR-comment markdown. Dashboard replays stored runs offline with realistic timing.

**Expected Outcomes:**
- `report.py` emits: DEFEATED section (guarantee, provenance, what defeats it, test, reproduction command), UNDEFENDED section (guarantee, provenance, "no test covers this"), DISPROVEN section (one line each)
- `METRICS.md` appended with run metrics
- `dashboard/index.html` + `app.js` + `style.css`: shows Purpose Ledger with coverage, branches, 5 lanes streaming with verdicts, winner's base=GREEN/head=RED split, benchmark table
- `witness replay --run <id>` renders a completed run with realistic timing, zero agent calls, zero network
- Readable at 1080p from across a room (large text, clear layout)
- `STATE.json` updated: M7 passed

**Todo List:**
- [ ] Implement `runner/report.py` — `generate_report(run: Run) -> str` producing markdown; append to `METRICS.md`
- [ ] Implement `witness replay` subcommand in `cli.py` — reads `dashboard/data/run-<id>.json`, serves index.html locally or writes replay data
- [ ] Write `dashboard/index.html` — semantic sections: ledger, branches, lanes, split view, benchmark
- [ ] Write `dashboard/app.js` — reads run JSON from `dashboard/data/`, replays lane results with simulated timing, no backend/network calls
- [ ] Write `dashboard/style.css` — large readable fonts, clear verdict colors (green/red/grey), 1080p legible
- [ ] Test replay offline: open dashboard with stored JSON, verify all sections render, verify zero network requests
- [ ] Update `STATE.json` M7 passed

**Relevant Context:**
- Spec §8 M7: "demos replay, they never re-run live"
- Dashboard must work with `file://` protocol (no backend, no build step, no framework)
- UNDEFENDED: checkable fact about coverage, not a prediction — cite provenance file:line

**Status:** [ ] pending

---

## Sub-Task 9 — M8: Benchmark

**Intent:** Implement `runner/bench.py` and 6 synthetic benchmark cases. Run unattended and write `bench/RESULTS.md` with one filled row per case.

**Expected Outcomes:**
- **6 synthetic cases** in `bench/cases/` (not 10–15), reusing `sample-repo/` surface
- Each case: (i) green alone, (ii) zero textual conflict on merge, (iii) defeats a documented guarantee
- Cases vary the mechanism across 6 distinct types (see DECISIONS.md D9)
- `witness bench --repo sample-repo` runs all cases unattended and writes `bench/RESULTS.md`
- `RESULTS.md` columns: `case | guarantee | green alone? | textual conflict? | existing suite caught it? | Witness verdict | proof test`
- Synthetic and real tables never blended; precision stated as 100% by construction with justification
- `STATE.json` updated: M8 passed

**Todo List:**
- [ ] Design **6** synthetic branch-pair scenarios (per DECISIONS.md D9): retry/limiter, write-through/cache, bulk-route/validator, idempotency-key/dedup, sort-removal/ordering, weakened-ceiling/ADR
- [ ] Create each case as branch pairs in `sample-repo/` with commits
- [ ] Write `bench/cases/<case-name>/meta.json` — guarantee, branch names, expected verdict
- [ ] Implement `runner/bench.py` — iterate cases, run `witness gate` per case, collect verdict, write `bench/RESULTS.md`
- [ ] Verify: `witness bench` runs unattended, fills every row, reports misses honestly
- [ ] Update `STATE.json` M8 passed, write final `METRICS.md`

**Relevant Context:**
- Spec §8 M8: "Never tune the engine per case. State that precision is 100% by construction and justify it with the proof gate."
- DECISIONS.md D9: 6 cases, vary mechanism, reuse same surface
- Table B (real git history cases) is the first scope-cut item per DECISIONS.md D4 — omit unless time allows
- Never blend synthetic and real tables

**Status:** [ ] pending

---

## Definition of Done (per spec §10)

- [ ] `witness gate --base main --head team-a/rate-limit --with team-b/retry` proves G1 defeated
- [ ] `witness standing --ref main` finds the planted vacuous guard with a cited guarantee
- [ ] `witness bench` fills `bench/RESULTS.md` for all 6 synthetic cases
- [ ] `witness replay` renders a stored run offline
- [ ] `README.md`, `DECISIONS.md`, `METRICS.md` are current
- [ ] No finding lacks a runnable test or a cited provenance file:line
- [ ] `docs/bob-sessions/` contains task session summary screenshots from each team member (submission requirement)
