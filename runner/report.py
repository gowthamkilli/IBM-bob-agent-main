"""
report.py — generate the PR-comment-shaped markdown report and append to METRICS.md.

Output categories (spec §2):
    DEFEATED  — a guarantee is broken; a proof test ships with the finding
    UNDEFENDED — a guarantee is documented, this change touches its surface,
                 and no test in the existing suite covers it
    Silence

Forbidden: confidence scores, "consider reviewing", "this might", severity
ratings on unproven items.
"""
from __future__ import annotations
import datetime
from pathlib import Path

from runner.schemas import Run, Guarantee, LaneResult


def generate_report(run: Run) -> str:
    """Generate a markdown report from a completed Run."""
    lines: list[str] = []
    lines.append("## Witness Report\n")
    lines.append(f"**Mode:** {run.mode}  ")
    lines.append(f"**Head:** `{run.head_sha}`  ")
    if run.base_sha:
        lines.append(f"**Base:** `{run.base_sha}`  ")
    lines.append(f"**Branches:** {', '.join(f'`{b}`' for b in run.branches)}  ")
    lines.append("")

    # DEFEATED
    defeated = run.findings.defeated
    if defeated:
        lines.append("### [DEFEATED]\n")
        for f in defeated:
            lines.append(f"**Guarantee {f['guarantee_id']}:** {f['statement']}")
            lines.append(f"- **Where stated:** {', '.join(f['provenance'])}")
            lines.append(f"- **Why it exists:** {f['why']}")
            lines.append(f"- **What defeats it:** {f['claim']}")
            lines.append(f"- **Proof test:** `{f['test_path']}`")
            lines.append(f"- **Reproduce:** `python -m pytest {f['test_path']} -x`")
            lines.append("")
    else:
        lines.append("### [OK] No guarantees defeated.\n")

    # UNDEFENDED
    undefended = run.findings.undefended
    if undefended:
        lines.append("### [UNDEFENDED]\n")
        lines.append("_These guarantees are documented, this change touches their surface,")
        lines.append("and no test in the existing suite covers them._\n")
        for f in undefended:
            lines.append(f"**Guarantee {f['guarantee_id']}:** {f['statement']}")
            lines.append(f"- **Provenance:** {', '.join(f['provenance'])}")
            lines.append(f"- No test in this suite covers this guarantee.")
            lines.append("")

    # DISPROVEN (trust-building — one line each)
    disproven = run.findings.disproven
    if disproven:
        lines.append("### [DISPROVEN] (checked and did not hold)\n")
        for f in disproven:
            lines.append(f"- {f.get('claim', f.get('candidate_id', '?'))}")
        lines.append("")

    # Metrics
    m = run.metrics
    lines.append("---")
    lines.append(f"_Wall clock: {m.wall_clock_s:.1f}s | "
                 f"Lanes: {m.lanes_total} total, "
                 f"{m.lanes_proven} proven, "
                 f"{m.lanes_disproven} disproven, "
                 f"{m.lanes_inconclusive} inconclusive, "
                 f"{m.lanes_invalid} invalid_")

    return "\n".join(lines)


def append_metrics(metrics_path: str | Path, run: Run) -> None:
    """Append a metrics row to METRICS.md."""
    metrics_path = Path(metrics_path)
    m = run.metrics
    ts = datetime.datetime.utcnow().isoformat(timespec="seconds")

    row = (
        f"| {run.run_id} | {run.mode} | {run.head_sha[:8]} | "
        f"{m.wall_clock_s:.1f}s | {m.lanes_proven}/{m.lanes_total} | "
        f"{len(run.findings.defeated)} | {len(run.findings.undefended)} | {ts} |"
    )

    if not metrics_path.exists():
        header = (
            "| run_id | mode | head | wall_clock | proven/total | "
            "defeated | undefended | timestamp |\n"
            "|--------|------|------|-----------|-------------|---------|-----------|-----------|"
        )
        metrics_path.write_text(header + "\n" + row + "\n", encoding="utf-8")
    else:
        with metrics_path.open("a", encoding="utf-8") as f:
            f.write(row + "\n")
