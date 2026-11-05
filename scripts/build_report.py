#!/usr/bin/env python3
"""Build a concise Markdown delivery report from task artifacts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    args = parser.parse_args()
    task = args.task_dir
    manifest_path = task / "requirements.json"
    if not manifest_path.exists():
        parser.error(f"Missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    requirements = manifest.get("requirements", [])
    counts = {}
    for req in requirements:
        status = req.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    lines = [
        f"# Delivery report: {manifest.get('feature', task.name)}",
        "",
        "## Requirement status",
        "",
        f"Total requirements: **{len(requirements)}**",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"| {status} | {count} |")

    lines += ["", "## Traceability", "", "| ID | Priority | Status | Description |", "|---|---|---|---|"]
    for req in requirements:
        description = str(req.get("description", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {req.get('id','')} | {req.get('priority','')} | {req.get('status','')} | {description} |")

    quality_path = Path("agent-work/quality-results.json")
    if quality_path.exists():
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        lines += ["", "## Configured quality checks", "", f"Overall status: **{quality.get('overall_status', 'unknown')}**", ""]
        lines += ["| Check | Required | Status | Exit code |", "|---|---:|---|---:|"]
        for check in quality.get("checks", []):
            lines.append(f"| {check.get('name')} | {check.get('required')} | {check.get('status')} | {check.get('exit_code')} |")
    else:
        lines += ["", "## Configured quality checks", "", "No `agent-work/quality-results.json` found. Checks have not been evidenced by this report."]

    lines += [
        "",
        "## Review and residual risks",
        "",
        "Complete this section manually or have the coordinator populate it with validated review findings and unverified areas.",
        "",
        "## Human decision",
        "",
        "- [ ] Approved for merge",
        "- [ ] Changes requested",
        "",
        "> This report summarizes recorded artifacts. It does not independently prove correctness or authorize merging.",
        "",
    ]
    output = task / "delivery-report.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
