# Implementation plan

## Scope and outcome

Add per-command timeouts and evidence output truncation to `.github/agent-scripts/run_quality.py`. All settings, including argv, are validated before anything runs. Add the repo's first test suite (`tests/test_run_quality.py`) and update the docs.

## Dependencies and sequencing

| Step | Requirements | Changes | Tests | Verification | Status |
|---|---|---|---|---|---|
| 1. Test design | All QT-* | `tests/test_run_quality.py` (Test Engineer). Black-box subprocess runs with temp config and output, child commands via `sys.executable -c`. | Acceptance, negative, boundary and property tests from requirements.json | Run against baseline. New-behaviour tests should fail for the intended reason. | planned |
| 2. Upfront validation | QT-CFG-001..008, QT-VAL-001..010, QT-DR-002 | `run_quality.py`: `_positive_number()`/`_positive_int()` helpers. A validation pass over `[quality]` and every command (argv, timeout_seconds) before the loop. Exit 2 with `ERROR: <field>` on stderr. No evidence written. | Validation tests | `pytest tests -k valid` | planned |
| 3. Timeout | QT-TO-001..011, QT-EV-001/002, QT-DR-001/003, QT-NFR-001 | `subprocess.run(timeout=...)`. Catch `TimeoutExpired`, decode partial output (bytes/None/str), record status `timeout`, print an ERROR line, apply required/optional semantics, continue. Add `timeout_seconds` to every record. | Timeout tests | `pytest tests -k timeout` | planned |
| 4. Truncation | QT-TR-001..009, QT-NFR-002 | `_truncate(text, limit)` returns `(kept, truncated, original_len)`. Applied to every record's stdout and stderr after the console echo. | Truncation and property tests | `pytest tests -k trunc` | planned |
| 5. Compatibility | QT-COMP-001..005, QT-OOS-* | Keep existing keys, statuses, exit codes and stdlib only. | Legacy-config regression test | Full `pytest tests` | planned |
| 6. Docs | — | `agent-quality.toml` header comments and `README.md` Quality runner and Safety sections | — | Manual read | planned |
| 7. Review and final verification | All | Code Reviewer, then fixes, then `run_quality.py` plus a manifest update and report | — | `run_quality.py`, `validate_requirements.py`, `build_report.py` | planned |

Steps 2–4 all edit `run_quality.py`, so they run sequentially in the main session. Step 1 (tests only) is delegated and runs before implementation.

## Risks and rollback

- 600 s default may time out long existing suites. Document it prominently.
- `TimeoutExpired` output is bytes/None on POSIX. Cover it with real-process tests, not mocks.
- Grandchildren are not killed (out of scope), so they can orphan or hold a pipe open. Recorded as a residual risk.
- Timing tests could be flaky. Use timeout ≤1 s against sleep ≥20 s, with generous bounds.
- Tests must never use the default config (recursion) or the default output path.
- Rollback: revert the `run_quality.py` diff. The new evidence fields are additive.

## Explicitly out of scope

Retries, parallel execution, process-group kill, a per-command `max_output_chars`, `build_report.py` changes, and pre-existing lint findings and unhandled OSErrors.
