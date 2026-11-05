#!/usr/bin/env python3
"""Run configured quality commands and save machine-readable evidence."""
from __future__ import annotations
import argparse
import json
import locale
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_MAX_OUTPUT_CHARS = 20000
# Larger timeouts overflow the OS poll timeout (INT_MAX milliseconds, about 24.8 days).
MAX_TIMEOUT_SECONDS = 1_000_000


def positive_number_error(field: str, value: object) -> str | None:
    """Return an error message unless 0 < value <= MAX_TIMEOUT_SECONDS (bool is rejected)."""
    # Chained comparison rejects nan and inf, and never converts huge ints to float.
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < value <= MAX_TIMEOUT_SECONDS
    ):
        return (
            f"{field} must be a positive number no greater than {MAX_TIMEOUT_SECONDS},"
            f" got {value!r}."
        )
    return None


def positive_int_error(field: str, value: object) -> str | None:
    """Return an error message unless value is an integer > 0 (bool is rejected)."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return f"{field} must be a positive integer, got {value!r}."
    return None


def validate(quality: dict, commands: list) -> list[str]:
    """Check every setting before anything runs; return error messages (empty if valid)."""
    errors = []
    if "default_timeout_seconds" in quality:
        error = positive_number_error(
            "quality.default_timeout_seconds", quality["default_timeout_seconds"]
        )
        if error:
            errors.append(error)
    if "max_output_chars" in quality:
        error = positive_int_error("quality.max_output_chars", quality["max_output_chars"])
        if error:
            errors.append(error)
    for item in commands:
        name = item.get("name", "unnamed")
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            errors.append(f"{name}: argv must be a non-empty array of strings.")
        if "timeout_seconds" in item:
            error = positive_number_error("timeout_seconds", item["timeout_seconds"])
            if error:
                errors.append(f"{name}: {error}")
    return errors


def decode_partial(output: bytes | str | None) -> str:
    """Normalise output captured before a timeout; POSIX gives bytes or None even with text=True.

    Bytes are decoded and newline-translated the way text=True would, but with errors="replace"
    because a killed child may stop mid-character.
    """
    if output is None:
        return ""
    if isinstance(output, bytes):
        text = output.decode(locale.getpreferredencoding(False), errors="replace")
        return text.replace("\r\n", "\n").replace("\r", "\n")
    return output


def truncate(text: str, limit: int) -> tuple[str, bool, int]:
    """Keep the last `limit` characters; return (kept, truncated, original_length)."""
    original = len(text)
    if original > limit:
        return text[-limit:], True, original
    return text, False, original


def echo(stdout: str, stderr: str) -> None:
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")


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

    errors = validate(quality, commands)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    default_timeout = quality.get("default_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    max_output_chars = quality.get("max_output_chars", DEFAULT_MAX_OUTPUT_CHARS)

    results = []
    overall_failed = False
    for item in commands:
        name = item.get("name", "unnamed")
        argv = item["argv"]
        required = bool(item.get("required", True))
        timeout = item.get("timeout_seconds", default_timeout)

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
            "timeout_seconds": timeout,
        }
        if args.dry_run:
            record["status"] = "dry_run"
        else:
            start = time.monotonic()
            try:
                completed = subprocess.run(
                    argv, cwd=cwd, text=True, capture_output=True, check=False, timeout=timeout
                )
                record["exit_code"] = completed.returncode
                record["stdout"] = completed.stdout
                record["stderr"] = completed.stderr
                record["duration_seconds"] = round(time.monotonic() - start, 3)
                record["status"] = "passed" if completed.returncode == 0 else "failed"
                echo(completed.stdout, completed.stderr)
                if completed.returncode != 0 and required:
                    overall_failed = True
            except subprocess.TimeoutExpired as exc:
                # subprocess.run has already killed the direct child (not its process group).
                record["duration_seconds"] = round(time.monotonic() - start, 3)
                record["status"] = "timeout"
                record["stdout"] = decode_partial(exc.stdout)
                record["stderr"] = decode_partial(exc.stderr)
                echo(record["stdout"], record["stderr"])
                print(f"ERROR: {name}: timed out after {timeout} seconds; killed.", file=sys.stderr)
                if required:
                    overall_failed = True
            except FileNotFoundError as exc:
                record["status"] = "error"
                record["stderr"] = str(exc)
                record["duration_seconds"] = round(time.monotonic() - start, 3)
                if required:
                    overall_failed = True
                print(f"ERROR: {exc}", file=sys.stderr)

        # Truncate evidence only; the console has already shown the full output.
        for stream in ("stdout", "stderr"):
            kept, truncated, original = truncate(record[stream], max_output_chars)
            record[stream] = kept
            record[f"{stream}_truncated"] = truncated
            record[f"{stream}_original_chars"] = original
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
