Witness
=======

**A refactor is a change that doesn't change behavior. We only ever check the first half.**

Witness takes two versions of a codebase that are _supposed_ to behave the same, and hunts for a concrete input where they don't. If it finds one, it hands you a runnable test that proves it. If it can't find one, it says nothing.

It is not a debugger. It never asks "why is this broken." It asks one question: **did behavior change — yes or no — and can you prove it?**

The problem
-----------

Refactors, dependency bumps, performance tweaks, and clean merges all make the same promise: _structure changed, behavior didn't._

Nobody verifies that promise. Teams rely on "the existing tests still pass," which is circular reasoning — those tests only cover behavior someone already thought to check. Anything outside them changes silently.

AI agents now refactor at high volume, so this gap is getting wider fast.

The rule
--------

> **Proof, or silence.**
> 
> A finding exists only if Witness can produce a test that is **GREEN on the base version and RED on the new version.**
> 
> No confidence scores. No "you may want to review this." No warnings.

Every other tool in this space outputs a list of maybes that reviewers learn to ignore. Witness outputs a test you can run yourself, or nothing at all.

That makes false positives structurally impossible.

How it works
------------

1.  **Surface** — find what's observable in _both_ versions (matching function signatures, API routes, CLI, DB writes). A probe must run unchanged against both.
    
2.  **Contract inference** — four subagents in parallel work out what callers were entitled to rely on in the old version: return shapes, nullability, ordering, boundary behavior, exceptions, side effects, and what the docs _claim_ is guaranteed.
    
3.  **Divergence candidates** — diff old contracts against new. Take the top 5.
    
4.  **Race** — five subagents in parallel, one candidate each. Every lane must emit an executable test, not prose. First lane whose test passes on base and fails on head wins.
    
5.  **Confirm** — reject flaky, tautological, or overly broad tests. Re-run 3x. Nothing proven? Say so. Don't downgrade guesses into warnings.
    
6.  **Report** — the broken contract, the witness input, the test, and the command to reproduce it.
    

Three modes, one engine
-----------------------

ModeInputQuestionrefactorbefore/after a refactor"You said this preserves behavior. Prove it."upgradesame code, new dependency version"Does our behavior change under the new version?"mergebranch A, branch B, their clean merge"Git found no conflict. Is the merged behavior still correct?"

What the master prompt is for
-----------------------------

PROMPT.md is a single kickoff goal for IBM Bob in Agent mode. You paste it once and Bob builds the whole project end to end — the .bob/ workflow and subagent definitions, the test runner and differential gate, the benchmark harness, and the dashboard.

It is written to enforce three things Bob would otherwise drift away from:

*   **No speculation.** Every phase is told to discard unproven findings rather than soften them into warnings.
    
*   **Parallel subagents, not sequential steps.** The racing is the architecture, not a performance optimization.
    
*   **Executable output.** Lanes that return prose instead of a test are failed lanes.
    

Check Bob's current subagent and workflow syntax in the hackathon guide and at bob.ibm.com/docs/ide, then correct the .bob/ paths in one pass before running it.

Evidence
--------

The benchmark runs 40 cases against a real repo: ~30 genuine agent-performed refactors, plus ~10 controls that deliberately change behavior while looking harmless (off-by-one at a boundary, a swallowed exception, changed collection ordering, a newly-possible None).

Results are reported as a confusion matrix **against the repo's own test suite as the baseline** — not just what Witness found, but what the status quo missed.

Prior art
---------

Differential test generation for refactor safety was shown to work by **SafeRefactor** (2012, Java, randomly generated tests, signature matching only). A wave of 2026 research — SemaDiff, _Foundation Models as Oracles for Refactoring Correctness_, _Partial Contracts Suffice_ — concluded that foundation models do it better.

Nobody has shipped it. Witness is that, built agentically: reasoned probing instead of random generation, parallel hypothesis racing instead of a single pass, and a hard proof gate so precision holds at 100% by construction.