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
SOURCE_KINDS = {"explicit", "inferred", "assumption"}
_QUOTE_CHARS = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"})


def normalise(text: str) -> str:
    """Collapse whitespace, unify typographic quotes/dashes and casefold for quote matching."""
    return " ".join(text.translate(_QUOTE_CHARS).split()).casefold()


def validate_source(prefix: str, source: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(source, dict):
        return [f"{prefix}.source must be an object with kind and ref."]
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        errors.append(f"{prefix}.source.kind must be one of {sorted(SOURCE_KINDS)}.")
    if not isinstance(source.get("ref"), str) or not source["ref"].strip():
        errors.append(f"{prefix}.source.ref must name the design section it derives from.")
    if kind == "explicit":
        if not isinstance(source.get("quote"), str) or not source["quote"].strip():
            errors.append(f"{prefix}.source.quote is required when kind is 'explicit'.")
    elif kind in {"inferred", "assumption"}:
        if not isinstance(source.get("rationale"), str) or not source["rationale"].strip():
            errors.append(f"{prefix}.source.rationale is required when kind is '{kind}'.")
    return errors

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
        errors.extend(validate_source(prefix, req.get("source")))
        if req.get("status") == "verified":
            methods = verification if isinstance(verification, list) else []
            if not any(isinstance(v, dict) and v.get("evidence") for v in methods):
                errors.append(f"{prefix} is marked verified but has no evidence.")
    return errors

def check_quotes(data: dict, design_text: str) -> list[str]:
    """Return errors for explicit quotes that do not appear in the design document."""
    haystack = normalise(design_text)
    errors: list[str] = []
    for index, req in enumerate(data.get("requirements", [])):
        source = req.get("source") if isinstance(req, dict) else None
        if not isinstance(source, dict) or source.get("kind") != "explicit":
            continue
        quote = source.get("quote")
        if isinstance(quote, str) and quote.strip() and normalise(quote) not in haystack:
            rid = req.get("id", f"requirements[{index}]")
            errors.append(f"{rid}: source.quote not found in design document: {quote!r}")
    return errors


def resolve_design(manifest: Path, data: object, override: Path | None) -> Path | None:
    if override is not None:
        return override
    if not isinstance(data, dict) or not isinstance(data.get("design_document"), str) or not data["design_document"].strip():
        return None
    ref = Path(data["design_document"])
    for candidate in (manifest.parent / ref, ref):
        if candidate.is_file():
            return candidate
    return ref


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--design", type=Path, help="Design document to check explicit quotes against (default: the manifest's design_document, resolved relative to the manifest, then the working directory).")
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    quote_status = "NOT RUN: no design_document in manifest and no --design given"
    design = resolve_design(args.manifest, data, args.design)
    if design is not None:
        try:
            design_text = design.read_text(encoding="utf-8")
        except OSError as exc:
            quote_status = f"NOT RUN: cannot read design document {design} ({exc.strerror})"
        else:
            quote_errors = check_quotes(data, design_text) if isinstance(data, dict) else []
            errors.extend(quote_errors)
            quote_status = "FAIL" if quote_errors else f"PASS against {design}"
    if errors:
        print("REQUIREMENTS INVALID")
        for error in errors:
            print(f"- {error}")
        print(f"Quote check: {quote_status}")
        return 1
    requirements = data["requirements"]
    counts: dict[str, int] = {}
    for req in requirements:
        counts[req["status"]] = counts.get(req["status"], 0) + 1
    print(f"REQUIREMENTS VALID: {len(requirements)} requirements")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    kinds: dict[str, int] = {}
    for req in requirements:
        kinds[req["source"]["kind"]] = kinds.get(req["source"]["kind"], 0) + 1
    print("Sources: " + ", ".join(f"{kind} {count}" for kind, count in sorted(kinds.items())))
    needs_signoff = [req["id"] for req in requirements if req["source"]["kind"] != "explicit"]
    if needs_signoff:
        print("Needs human sign-off (inferred/assumption): " + ", ".join(needs_signoff))
    print(f"Quote check: {quote_status}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
