#!/usr/bin/env python3
"""Run configured quality commands and save machine-readable evidence."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(".github/agent-quality.toml"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("agent-work/quality-results.json"))
    args = parser.parse_args()

    try:
        config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"ERROR reading config: {exc}", file=sys.stderr)
        return 2

    quality = config.get("quality", {})
    cwd = Path(quality.get("working_directory", ".")).resolve()
    commands = quality.get("commands", [])
    if not commands:
        print("ERROR: no [[quality.commands]] configured.", file=sys.stderr)
        return 2

    results = []
    overall_failed = False
    for item in commands:
        name = item.get("name", "unnamed")
        argv = item.get("argv")
        required = bool(item.get("required", True))
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            print(f"ERROR: {name}: argv must be a non-empty array of strings.", file=sys.stderr)
            return 2

        print(f"\n== {name} ==\n$ {' '.join(argv)}")
        record = {
            "name": name,
            "command": argv,
            "required": required,
            "status": "not_run",
            "exit_code": None,
            "duration_seconds": None,
            "stdout": "",
            "stderr": "",
        }
        if args.dry_run:
            record["status"] = "dry_run"
            results.append(record)
            continue

        start = time.monotonic()
        try:
            completed = subprocess.run(
                argv, cwd=cwd, text=True, capture_output=True, check=False
            )
            record["exit_code"] = completed.returncode
            record["stdout"] = completed.stdout
            record["stderr"] = completed.stderr
            record["duration_seconds"] = round(time.monotonic() - start, 3)
            record["status"] = "passed" if completed.returncode == 0 else "failed"
            if completed.stdout:
                print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
            if completed.stderr:
                print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
            if completed.returncode != 0 and required:
                overall_failed = True
        except FileNotFoundError as exc:
            record["status"] = "error"
            record["stderr"] = str(exc)
            record["duration_seconds"] = round(time.monotonic() - start, 3)
            if required:
                overall_failed = True
            print(f"ERROR: {exc}", file=sys.stderr)
        results.append(record)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "working_directory": str(cwd),
        "dry_run": args.dry_run,
        "overall_status": "failed" if overall_failed else ("dry_run" if args.dry_run else "passed"),
        "checks": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nQuality status: {payload['overall_status']}")
    print(f"Evidence: {args.output}")
    return 1 if overall_failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
