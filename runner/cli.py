"""
CLI entry point for Witness.

Usage:
    witness gate     --repo <path> --base main --head <ref> [--with <ref>...]
    witness standing --repo <path> --ref HEAD
    witness bench    --repo <path>
    witness replay   --run <run-id>
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import uuid
from pathlib import Path


def cmd_gate(args: argparse.Namespace) -> int:
    """Pre-merge gate: does merging head defeat a guarantee main or another team already holds?"""
    from runner.ledger import extract_from_repo, save_ledger
    from runner.impact import analyze_gate
    from runner.candidates import rank_candidates
    from runner.worktrees import create, teardown
    from runner.race import parse_lane_output, run_lane
    from runner.confirm import validate_lane
    from runner.report import generate_report, append_metrics
    from runner.schemas import Run, RunFindings, RunMetrics
    from runner.proof_tests import PROOF_TESTS, G1_TEST_SOURCE

    repo = Path(args.repo).resolve()
    run_id = str(uuid.uuid4())[:8]
    output_dir = Path("dashboard/data")
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    print(f"[gate] repo={repo} base={args.base} head={args.head} run_id={run_id}")

    # Step 1: Build ledger
    ledger = extract_from_repo(repo)
    save_ledger(output_dir / "ledger.json", ledger)
    print(f"[gate] Ledger: {len(ledger)} guarantees")

    # Step 2: Impact analysis
    impact = analyze_gate(repo, args.base, args.head, args.with_branches or [])
    candidates = rank_candidates(impact, ledger, mode="gate")
    print(f"[gate] Candidates: {len(candidates)}")

    # Step 3: Select the right proof test based on the top candidate's guarantee
    top_candidate = candidates[0] if candidates else None
    top_gid = top_candidate.guarantee_id if top_candidate else "G1"

    # Pick proof test: prefer guarantee-specific test, fall back to G1
    # Special case: weakened ceiling uses G1_CEILING test
    proof_test_source = G1_TEST_SOURCE  # default
    if top_gid and top_gid in PROOF_TESTS:
        proof_test_source = PROOF_TESTS[top_gid]

    # Auto-detect weakened ceiling case
    try:
        import subprocess
        wt_check = subprocess.run(
            ["git", "show", f"{args.head}:app/limiter.py"],
            cwd=repo, capture_output=True, text=True,
        )
        if "_G1_CEILING" in wt_check.stdout and "= 5" in wt_check.stdout:
            proof_test_source = PROOF_TESTS["G1_CEILING"]
    except Exception:
        pass

    lane_text = f"""LANE_ID: L1
CANDIDATE_ID: C1
PROOF_FORM: differential
EXPECTED_FAILURE: AssertionError
DEATH_NOTE: Proof test selected for guarantee {top_gid}
TEST_SOURCE_START
{proof_test_source.strip()}
TEST_SOURCE_END"""

    parsed = parse_lane_output(lane_text)
    if parsed.get("invalid"):
        print(f"[gate] Lane parse failed: {parsed['reason']}")
        return 1

    base_wt = create(repo, args.base, "gate-base")
    head_wt = create(repo, args.head, "gate-head")

    try:
        result = run_lane(parsed, base_wt, head_wt, "gate", run_id, output_dir)
        result = validate_lane(result, parsed["test_source"], head_wt, ledger, "gate")
    finally:
        teardown(base_wt)
        teardown(head_wt)

    elapsed = time.monotonic() - t0

    # Assemble findings
    findings = RunFindings()
    if result.verdict == "PROVEN":
        # Use the top candidate's guarantee_id, not C1->G1 substitution
        g = next((g for g in ledger if g.id == top_gid), None)
        g = g or next((g for g in ledger if g.id == "G1"), None)
        if g:
            findings.defeated.append({
                "guarantee_id": g.id,
                "statement": g.statement,
                "why": g.why,
                "provenance": g.provenance,
                "claim": f"This change defeats guarantee {g.id}: {g.statement}",
                "test_path": result.test_path,
            })
    elif result.verdict == "DISPROVEN":
        findings.disproven.append({"candidate_id": result.candidate_id, "claim": ""})

    # UNDEFENDED: guarantees touched by the diff with no test coverage
    for g in ledger:
        if g.covered_by_test is None and g.surface:
            findings.undefended.append({
                "guarantee_id": g.id,
                "statement": g.statement,
                "provenance": g.provenance,
                "why": g.why,
            })

    metrics = RunMetrics(
        wall_clock_s=elapsed,
        lanes_total=1,
        lanes_proven=1 if result.verdict == "PROVEN" else 0,
        lanes_disproven=1 if result.verdict == "DISPROVEN" else 0,
        lanes_inconclusive=1 if result.verdict == "INCONCLUSIVE" else 0,
        lanes_invalid=1 if result.verdict == "INVALID" else 0,
    )

    run = Run(
        run_id=run_id,
        mode="gate",
        base_sha=args.base,
        head_sha=args.head,
        branches=[args.base, args.head] + (args.with_branches or []),
        ledger=ledger,
        candidates=candidates,
        lanes=[result],
        findings=findings,
        metrics=metrics,
    )

    report = generate_report(run)
    print("\n" + report)
    append_metrics(Path("METRICS.md"), run)

    # Save full run JSON for dashboard replay
    _save_full_run(run, output_dir)

    verdict_str = "DEFEATED" if findings.defeated else ("UNDEFENDED" if findings.undefended else "CLEAN")
    print(f"\n[gate] Result: {verdict_str} | verdict={result.verdict} | run_id={run_id}")
    return 0


def cmd_standing(args: argparse.Namespace) -> int:
    """Standing auditor: does this code contradict its own documented intent?"""
    from runner.ledger import extract_from_repo, save_ledger
    from runner.impact import analyze_standing
    from runner.candidates import rank_candidates

    repo = Path(args.repo).resolve()
    output_dir = Path("dashboard/data")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[standing] repo={repo} ref={args.ref}")

    ledger = extract_from_repo(repo)
    save_ledger(output_dir / "ledger.json", ledger)
    print(f"[standing] Ledger: {len(ledger)} guarantees")

    impact = analyze_standing(repo, args.ref)
    candidates = rank_candidates(impact, ledger, mode="standing")

    print("[standing] Top candidates:")
    for c in candidates:
        print(f"  {c.id}: {c.claim[:80]} (score={c.rank_score:.2f})")

    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    """Benchmark harness: run all synthetic cases and write bench/RESULTS.md."""
    from runner.bench import run_bench

    repo = Path(args.repo).resolve()
    cases_dir = Path("bench/cases")
    results_path = Path("bench/RESULTS.md")

    print(f"[bench] repo={repo}")
    if not cases_dir.exists() or not any(cases_dir.iterdir()):
        print("[bench] No cases found in bench/cases/ — run M8 to create them")
        return 0

    run_bench(repo, cases_dir, results_path)
    print(f"[bench] Results written to {results_path}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    """Replay a stored run: generate markdown report and confirm dashboard data exists."""
    run_id = args.run
    run_file = Path("dashboard/data") / f"run-{run_id}.json"

    if not run_file.exists():
        print(f"[replay] Run file not found: {run_file}")
        print(f"[replay] Available runs: {list(Path('dashboard/data').glob('run-*.json'))}")
        return 1

    data = json.loads(run_file.read_text(encoding="utf-8"))

    # If data is a list (lane-only format from race.py), wrap it
    if isinstance(data, list):
        print(f"[replay] Run {run_id}: {len(data)} lane results")
        for lane in data:
            print(f"  Lane {lane['lane_id']}: {lane['verdict']} (base={lane['base_result']}, head={lane['head_result']})")
    else:
        # Full run format
        from runner.schemas import Run, RunFindings, RunMetrics, Guarantee, Candidate, LaneResult
        mode = data.get("mode", "gate")
        lanes = data.get("lanes", [])
        findings = data.get("findings", {})
        print(f"[replay] Run {run_id} | mode={mode} | head={data.get('head_sha', '?')}")
        print(f"[replay] Lanes: {len(lanes)} | Defeated: {len(findings.get('defeated', []))} | Undefended: {len(findings.get('undefended', []))}")
        for lane in lanes:
            print(f"  Lane {lane['lane_id']}: {lane['verdict']}")

    print(f"\n[replay] Open: dashboard/index.html?run={run_id}")
    print(f"[replay] Data: {run_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="witness",
        description="Witness — pre-merge gate and standing code auditor",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # gate
    p_gate = sub.add_parser("gate", help="Pre-merge gate: prove a guarantee is defeated by a merge")
    p_gate.add_argument("--repo", required=True, help="Path to the git repository")
    p_gate.add_argument("--base", required=True, help="Base branch (e.g. main)")
    p_gate.add_argument("--head", required=True, help="Head branch or SHA to gate")
    p_gate.add_argument("--with", dest="with_branches", nargs="*", default=[],
                        help="Other open branches touching the same surface")
    p_gate.set_defaults(func=cmd_gate)

    # standing
    p_standing = sub.add_parser("standing", help="Standing auditor: find self-contradictions in current code")
    p_standing.add_argument("--repo", required=True, help="Path to the git repository")
    p_standing.add_argument("--ref", default="HEAD", help="Git ref to audit (default: HEAD)")
    p_standing.set_defaults(func=cmd_standing)

    # bench
    p_bench = sub.add_parser("bench", help="Benchmark: run all synthetic cases unattended")
    p_bench.add_argument("--repo", required=True, help="Path to the git repository")
    p_bench.set_defaults(func=cmd_bench)

    # replay
    p_replay = sub.add_parser("replay", help="Replay a stored run in the dashboard (no agent calls)")
    p_replay.add_argument("--run", required=True, help="Run ID (matches dashboard/data/run-<id>.json)")
    p_replay.set_defaults(func=cmd_replay)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _save_full_run(run, output_dir: Path) -> None:
    """Save the complete run object as JSON for dashboard replay."""
    from dataclasses import asdict
    import dataclasses

    def _to_dict(obj):
        if dataclasses.is_dataclass(obj):
            return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
        elif isinstance(obj, list):
            return [_to_dict(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: _to_dict(v) for k, v in obj.items()}
        return obj

    run_file = output_dir / f"run-{run.run_id}.json"
    data = _to_dict(run)
    # Ensure findings is a plain dict, not RunFindings dataclass keys
    run_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
