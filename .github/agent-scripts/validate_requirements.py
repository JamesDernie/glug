#!/usr/bin/env python3
"""Validate a feature requirements manifest using only the Python standard library."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

STATUSES = {"planned", "test_written", "implemented", "verified", "blocked", "deferred"}
PRIORITIES = {"critical", "high", "medium", "low"}
ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]+$")

def validate(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Root must be a JSON object."]
    if not isinstance(data.get("feature"), str) or not data["feature"].strip():
        errors.append("'feature' must be a non-empty string.")
    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        return errors + ["'requirements' must be a non-empty array."]
    seen: set[str] = set()
    for index, req in enumerate(requirements):
        prefix = f"requirements[{index}]"
        if not isinstance(req, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        rid = req.get("id")
        if not isinstance(rid, str) or not ID_RE.match(rid):
            errors.append(f"{prefix}.id must be uppercase and stable (e.g. DATA-001).")
        elif rid in seen:
            errors.append(f"Duplicate requirement id: {rid}")
        else:
            seen.add(rid)
        if not isinstance(req.get("description"), str) or not req["description"].strip():
            errors.append(f"{prefix}.description must be non-empty.")
        if req.get("priority") not in PRIORITIES:
            errors.append(f"{prefix}.priority must be one of {sorted(PRIORITIES)}.")
        if req.get("status") not in STATUSES:
            errors.append(f"{prefix}.status must be one of {sorted(STATUSES)}.")
        verification = req.get("verification")
        if not isinstance(verification, list) or not verification:
            errors.append(f"{prefix}.verification must contain at least one verification method.")
        else:
            for v_index, item in enumerate(verification):
                if not isinstance(item, dict):
                    errors.append(f"{prefix}.verification[{v_index}] must be an object.")
                    continue
                for field in ("type", "description"):
                    if not isinstance(item.get(field), str) or not item[field].strip():
                        errors.append(f"{prefix}.verification[{v_index}].{field} must be non-empty.")
                for field in ("test_ids", "evidence"):
                    if field in item and not isinstance(item[field], list):
                        errors.append(f"{prefix}.verification[{v_index}].{field} must be an array.")
        if req.get("status") == "verified":
            methods = verification if isinstance(verification, list) else []
            if not any(isinstance(v, dict) and v.get("evidence") for v in methods):
                errors.append(f"{prefix} is marked verified but has no evidence.")
    return errors

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        print("REQUIREMENTS INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    requirements = data["requirements"]
    counts: dict[str, int] = {}
    for req in requirements:
        counts[req["status"]] = counts.get(req["status"], 0) + 1
    print(f"REQUIREMENTS VALID: {len(requirements)} requirements")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
