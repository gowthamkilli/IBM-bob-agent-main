BUILD SPECIFICATION — "Witness"
===============================

You are building a complete, working project. This document is a specification, not a conversation. Execute it top to bottom.

0\. OPERATING RULES — non-negotiable
------------------------------------

1.  **Work in milestones M0–M8, in order.** Each milestone has a DELIVERABLE and an ACCEPTANCE TEST. Do not start a milestone until the previous one's acceptance test passes. If an acceptance test fails, fix it; do not proceed.
    
2.  **After each milestone**: run its acceptance test, write STATE.json, and post a status of at most 3 lines: milestone, acceptance result, next action.
    
3.  **Use subagents for any step marked PARALLEL.** Each subagent returns at most 800 tokens. Never let a subagent dump file contents into the main context.
    
4.  **Checkpoint everything.** If your context is compacted or the session restarts, read STATE.json and resume from the recorded milestone. Never restart from M0.
    
5.  **No placeholders.** No TODO, no pass # implement later, no mocked function that returns a hardcoded result standing in for real logic. Every milestone must actually run.
    
6.  **No secrets anywhere.** Respect .bobignore.
    

1\. WHAT YOU ARE BUILDING
-------------------------

Witness is a pre-merge gate and standing auditor that proves when code defeats the purpose of other code. It does not guess. It emits a finding only when it can produce a runnable test that demonstrates the problem.

Two entry points:

TriggerBaseHeadQuestionProof form**GATE** — a PR targets mainmainmain + this branch + other open branches touching the same surface, mergedDoes merging this defeat a guarantee main or another team already holds?differential**STANDING** — any other timenonea single refDoes this code contradict its own documented intent, or itself?contradiction / impossibility

2\. DEFINITIONS — use these exactly
-----------------------------------

**Guarantee.** A promise the system makes, evidenced somewhere in the repository. Not a behavior it happens to have. Every guarantee must carry provenance: a file:line in an ADR, spec, README, docstring, inline comment, commit message, or a test name. **A candidate guarantee with no provenance is discarded.**

**Proof forms.** A finding must be established by exactly one of:

*   differential — the test PASSES on base and FAILS on head.
    
*   contradiction — the test asserts a Purpose Ledger guarantee and FAILS on head, 3/3 runs. The code contradicts its own documentation.
    
*   impossibility — execution evidence that a branch is unreachable or a constraint set is unsatisfiable. Evidence, not argument.
    

**Verdicts.** PROVEN | DISPROVEN | INCONCLUSIVE | INVALID. INVALID means the probe errored on base — it tested something that does not exist in both versions. Never scored as a win.

**Output categories.** Witness emits these three and nothing else:

*   DEFEATED — a guarantee is broken and a proof test ships with the finding.
    
*   UNDEFENDED — a guarantee is documented, this change touches its surface, and **no test in the existing suite covers it**. This is a checkable fact about coverage, not a prediction. Cite the provenance file:line.
    
*   Silence.
    

**Forbidden output.** Confidence scores. "Consider reviewing." "This might." "Potential issue." Severity ratings on unproven items. An unprovable suspicion is discarded, never downgraded into a warning.

**Fallacy taxonomy** (STANDING candidate classes — a fallacy is a contradiction, never a code smell):

ClassProven bycontradicted-guaranteecontradiction testdefeated-enforcement — a path reaches the protected sink without the checktest reaching the sink uncheckedvacuous-guard — a condition no input satisfies, a branch no input reachesimpossibility, via coverage/executionmutually-exclusive-rules — no single input satisfies both constraintsimpossibility, via exhaustive searchdecorative-mechanism — cache never hit, retry budget never used, limit never bindingguarantee test showing the property does not holdassumption-mismatch — one component assumes ordering/idempotence another does not providesequence test

3\. TECHNOLOGY
--------------

Python 3.11. pytest. fastapi + uvicorn + sqlite3 for the sample app. Standard library subprocess and git worktree for differential execution. Dashboard is static HTML + vanilla JS reading JSON from disk. **No backend, no build step, no framework, no auth, no deployment.**

4\. REPOSITORY LAYOUT — create exactly this
-------------------------------------------

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   .bob/  workflow.md                 the Witness pipeline as a Bob workflow  agents/    ledger-agent.md    callers-agent.md    contract-agent.md    intent-agent.md    lane-agent.mdrunner/  __init__.py  cli.py                      entry point: witness gate|standing|bench|replay  worktrees.py                M3 — create/tear down base & head worktrees  execute.py                  M3 — run one test file against one worktree  ledger.py                   M4 — build the Purpose Ledger  impact.py                   M5 — invoke the three impact subagents  candidates.py               M5 — rank and select top 5  race.py                     M6 — spawn lanes, collect results  confirm.py                  M6 — the gate  report.py                   M7 — markdown report  bench.py                    M8 — benchmark harness  schemas.py                  dataclasses for every contract in section 5sample-repo/                  a real git repo, committed, with branchesdashboard/  index.html  app.js  style.css  data/                       run-*.json, written by the runnerbench/  cases/                      one directory per benchmark case  RESULTS.mddocs/  bob-sessions/               task session screenshots go hereREADME.mdDECISIONS.mdMETRICS.mdSTATE.json.bobignore.gitignore   `

5\. DATA CONTRACTS — implement in runner/schemas.py, do not deviate
-------------------------------------------------------------------

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   Guarantee = {  "id": str,                      # "G1"  "statement": str,               # "at most 5 calls/sec to the payment gateway"  "why": str,                     # "the gateway rate-limits us and bills overage"  "provenance": [str],            # ["docs/ADR-002.md:14", "app/limiter.py:8"]  "enforced_at": [str],           # ["app/limiter.py:22"]  "covered_by_test": str | None,  # "tests/test_limits.py::test_call_ceiling"  "surface": [str],               # ["app.gateway.charge", "POST /orders"]}  Candidate = {  "id": str,                      # "C3"  "claim": str,                   # one sentence, falsifiable  "guarantee_id": str | None,  "fallacy_class": str | None,    # from the taxonomy, STANDING only  "proof_form": str,              # differential | contradiction | impossibility  "test_style": str,              # equivalence | guarantee  "rank_score": float,}  LaneResult = {  "lane_id": str,  "candidate_id": str,  "test_path": str,  "expected_failure": {"exception": str | None, "assert_substring": str},  "base_result": str | None,      # PASS | FAIL | ERROR | None (standing mode)  "head_result": str,             # PASS | FAIL | ERROR  "verdict": str,                 # PROVEN | DISPROVEN | INCONCLUSIVE | INVALID  "stderr_excerpt": str,          # <= 400 chars  "elapsed_s": float,  "death_note": str,              # one line, why it died; seeds round 2}  Run = {  "run_id": str,  "mode": str,                    # gate | standing  "base_sha": str | None,  "head_sha": str,  "branches": [str],  "ledger": [Guarantee],  "candidates": [Candidate],  "lanes": [LaneResult],  "findings": {"defeated": [...], "undefended": [...], "disproven": [...]},  "metrics": {"wall_clock_s": float, "lanes_run": int, "rounds": int,              "human_actions": int},}   `

6\. CLI CONTRACT
----------------

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`witness gate     --repo --base main --head [--with ...]witness standing --repo --ref HEADwitness bench    --repo witness replay   --run` 

Every command writes dashboard/data/run-.json incrementally — each lane result is flushed to disk the moment it lands, not at the end.

7\. THE SAMPLE APP — build this, do not go looking for one
----------------------------------------------------------

sample-repo/ is a real git repository you create and commit. It is a small order service. Keep it under ~400 lines. It must have a passing pytest suite on main.

**Modules:** app/api.py (FastAPI routes), app/orders.py (create/validate), app/gateway.py (payment calls), app/cache.py (catalog cache), app/db.py (sqlite), tests/, docs/ADR-001..004.md.

**Documented guarantees on main** — each stated in an ADR _and_ a docstring, and some deliberately left without test coverage:

idguaranteecovered by a test on main?G1at most 5 calls/sec reach the payment gateway**no** — leave uncoveredG2the same idempotency key creates exactly one orderyesG3every order write passes through validate\_order()**no** — leave uncoveredG4catalog reads are served from cache; DB hit rate < 20% once warm**no** — leave uncovered

**Planted STANDING-mode defects on main** (so standing mode has something real to find on day one):

*   a vacuous-guard in orders.py: a validation branch an earlier condition makes unreachable.
    
*   a contradicted-guarantee: a docstring promising a non-null return on a path that can return None.
    

**Branches — the cross-team case.** Neither branch is wrong. The merge is.

*   team-a/rate-limit — _introduces_ the rate limiter enforcing G1. Adds ADR-002. Green alone.
    
*   team-b/retry — adds retry-with-backoff around gateway failures. Sensible on its own; at the time it was written no limiter existed. Green alone.
    
*   git merge of the two produces **zero textual conflict** and a **fully green test suite** — but the retries route around the limiter, so more than 5 calls per second reach the gateway. **G1 is defeated by the combination and by neither branch alone.** This is the demo.
    

Add a second pair for the benchmark: team-c/bulk-endpoint (a POST /orders/bulk route that writes orders directly) defeating **G3**, since it never calls validate\_order().

8\. MILESTONES
--------------

### M0 — Scaffold

**Deliverable:** the full tree from section 4, runner/schemas.py implementing section 5, runner/cli.py parsing section 6 (subcommands may no-op). **Acceptance:** python -m runner.cli --help exits 0 and lists all four subcommands.

### M1 — Sample app on main

**Deliverable:** sample-repo/ as specified in section 7, committed to main, with ADRs, docstrings, the two planted defects, and a pytest suite. **Acceptance:** pytest inside sample-repo/ is green, and git log on main shows at least 3 commits with meaningful messages.

### M2 — The branches

**Deliverable:** team-a/rate-limit, team-b/retry, team-c/bulk-endpoint. **Acceptance:** each branch is green under pytest **alone**; git merge team-b/retry into team-a/rate-limit reports **no conflict** and the merged suite is **also green**. Record all four SHAs in DECISIONS.md. If the merge is green and the guarantee is genuinely defeated, M2 passes. **If the merged suite goes red, the sample is wrong — fix the sample, not the runner.**

### M3 — Differential execution harness ← _highest-risk piece; prove it here_

**Deliverable:** worktrees.py and execute.py. Create .wt/base and .wt/head via git worktree add. **Never** run git checkout, stash, or reset on the main tree. Copy one test file into both worktrees and run it in each. Return tri-state PASS | FAIL | ERROR per side — an import or collection error is ERROR, never FAIL. Hard 120s timeout per execution; on timeout kill the process and return INCONCLUSIVE. **Acceptance:** hand-write one test asserting the G1 call ceiling. Run it through the harness with base = team-a/rate-limit and head = the merge. It must report base=PASS, head=FAIL. **Nothing downstream works until this does.**

### M4 — Purpose Ledger

**Deliverable:** ledger.py + .bob/agents/ledger-agent.md. Extract guarantees from ADRs, docstrings, inline comments, commit messages, config constants, and **test names** — a test called test\_duplicate\_submit\_creates\_one\_record is a written-down guarantee. Populate covered\_by\_test by matching guarantees to the existing suite. Discard anything without provenance. **Acceptance:** running against main recovers G1–G4 with correct provenance file:line, and correctly marks G1, G3 and G4 as covered\_by\_test: null.

### M5 — Impact and candidates _(PARALLEL)_

**Deliverable:** impact.py invoking three subagents concurrently, each capped at 800 tokens:

*   callers-agent — transitive callers of changed symbols, up to 3 hops; flag call sites with no null/shape/exception guard.
    
*   contract-agent — what the old code guaranteed mechanically: nullability, ordering, idempotence, exceptions raised, return shape, side effects.
    
*   intent-agent — for every ledger guarantee whose surface this change touches, does the change **bypass** the enforcement point, **weaken** it, or **multiply** the work it was limiting? In GATE mode also: does branch B defeat a guarantee branch A _introduces_?
    

Then candidates.py ranks and selects the top 5, distinct and non-overlapping. GATE rank = unguarded\_call\_sites × (1 if uncovered else 0.3). STANDING rank = blast\_radius × (1 if uncovered else 0.3), walking the fallacy taxonomy. **Acceptance:** on the merge, the top-ranked candidate is the G1 ceiling defeat. On standing --ref main, the planted vacuous guard appears in the top 5.

### M6 — Race and confirm _(PARALLEL)_

**Deliverable:** race.py spawning 5 lane subagents concurrently, one candidate each. Every lane must:

*   emit an **executable** test — prose is a failed lane;
    
*   use only the shared surface (symbols whose signatures exist and match in both refs), so the same file runs unchanged on each side;
    
*   declare expected\_failure **before** running;
    
*   **never modify application source** — tests only.
    

PROVEN requires:

*   GATE: base=PASS and head=FAIL, failure matching the declared signature.
    
*   STANDING: head=FAIL 3/3 runs, matching the signature, **and** a cited ledger guarantee the failure contradicts. _A failing test with no guarantee behind it is just a failing test. Discard it._
    

confirm.py rejects flaky tests, tautologies (assert False), failures on import/collection error, failures whose signature does not match, and tests so broad any change would fail them. Re-run survivors 3×. Zero PROVEN → **one** round-2 race seeded by every death\_note. Still zero → proceed to M7 and report nothing as DEFEATED. **Acceptance:** witness gate --base main --head team-a/rate-limit --with team-b/retry returns exactly one PROVEN lane, and the test it emitted passes on team-a/rate-limit and fails on the merge when run by hand.

### M7 — Report and dashboard

**Deliverable:** report.py producing a PR-comment-shaped markdown report: DEFEATED (guarantee, where it is stated, why it exists, what defeats it, the test, the exact command to reproduce), UNDEFENDED (guarantee, provenance, "no test in this suite covers this"), DISPROVEN (one line each — this builds trust). Append metrics to METRICS.md.

dashboard/ is one static page showing: the Purpose Ledger with coverage status, the branches and their clean merge, the 5 lanes streaming with verdicts, the winner's base=GREEN / head=RED split view, and the benchmark table. It must **replay a stored run from dashboard/data/ with realistic timing and zero agent calls** — demos replay, they never re-run live. **Acceptance:** witness replay --run  renders a completed run in the browser with no network access and no agent invocation. Readable at 1080p from across a room.

### M8 — Benchmark

**Deliverable:** bench.py and bench/cases/. Two **separately reported** tables:

*   **A — synthetic:** 10–15 injected cross-team conflicts. Each is a branch pair that (i) is green alone, (ii) merges with zero textual conflict, (iii) together defeats a documented guarantee. Vary the mechanism: retry defeating a limiter, write-through defeating a cache, a new route bypassing a validator, a regenerated idempotency key defeating dedup, a sort removed upstream of code assuming order.
    
*   **B — real:** 2–3 cases from public git history, only if time allows.
    

**Never blend the tables. Never imply a synthetic case is historical.**

bench/RESULTS.md, per case: | case | guarantee | green alone? | textual conflict? | existing suite caught it? | Witness verdict | proof test |

Report misses honestly. Do not tune the engine per case. State that precision is **100% by construction** and justify it with the proof gate. **Acceptance:** witness bench runs every case unattended and writes RESULTS.md with a filled row per case.

9\. FAILURE HANDLING
--------------------

*   Acceptance test fails → fix it within that milestone. Never move on.
    
*   A subagent returns prose where a test was required → that lane is DISPROVEN, not retried indefinitely. Maximum 1 retry per lane.
    
*   A lane hangs → 120s hard kill, INCONCLUSIVE, the race continues.
    
*   Context compacted → read STATE.json, resume at the recorded milestone.
    
*   **If forced to cut scope, cut in this order:** benchmark table B → team-c case → round-2 race → suggested-test generation → STANDING mode. **Never cut the race or the proof gate.** They are the product.
    

10\. DEFINITION OF DONE
-----------------------

1.  witness gate --base main --head team-a/rate-limit --with team-b/retry runs unattended and proves G1 is defeated by the combination.
    
2.  witness standing --ref main finds the planted vacuous guard, citing a ledger guarantee.
    
3.  witness bench fills bench/RESULTS.md for every synthetic case.
    
4.  witness replay renders a stored run offline.
    
5.  README.md, DECISIONS.md, METRICS.md are current.
    
6.  No finding anywhere in the output lacks a runnable test or a cited provenance file:line.
    

11\. FIRST ACTION
-----------------

Confirm Bob's current subagent and workflow syntax against the hackathon guide and bob.ibm.com/docs/ide, write what you find into DECISIONS.md, and use that syntax for every file under .bob/.

Then begin **M0**. Work through to **M8** without stopping to ask me anything.