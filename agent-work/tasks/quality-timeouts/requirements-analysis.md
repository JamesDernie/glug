# Requirements analysis: quality-runner timeouts and output limits

Design: `agent-work/tasks/quality-timeouts/design.md` (copy of `agent-work/designs/quality-timeouts.md`). Baseline: `4020eaa`. Manifest: `requirements.json` (53 requirements: 36 explicit, 9 inferred, 8 assumption).

## 1. Scope summary

Change `.github/agent-scripts/run_quality.py` so that:
- every command runs with a timeout (`[quality].default_timeout_seconds`, default 600, overridable per command with `timeout_seconds`);
- a timed-out command is killed and recorded with status `timeout`, and the runner carries on;
- each of the `stdout` and `stderr` evidence fields is limited to the last `max_output_chars` characters (default 20000), with truncation flags and original lengths;
- bad values for the new settings stop the runner with exit 2 before anything runs, in both real and `--dry-run` mode.

Affected components: `run_quality.py` (config parsing, run loop, record building), the `.github/agent-quality.toml` schema (new optional keys, no file change required), and the `agent-work/quality-results.json` format (fields added only). No other script reads `quality-results.json` at baseline, apart from agents and humans.

Out of scope: retries (QT-OOS-001), parallel execution (QT-OOS-002) and process-group killing (QT-OOS-003, residual risk).

## 2. Explicit requirements

| Area | IDs |
|---|---|
| Configuration and defaults | QT-CFG-001, QT-CFG-002, QT-CFG-003, QT-CFG-005, QT-CFG-006 |
| Validation | QT-VAL-001 (zero), QT-VAL-002 (negative), QT-VAL-003 (non-numeric), QT-VAL-004 (boolean), QT-VAL-005 (exit 2), QT-VAL-006 (field named), QT-VAL-008 (before running anything) |
| Timeout | QT-TO-001 (kill), QT-TO-002 (status), QT-TO-003 (exit_code null), QT-TO-004 (duration), QT-TO-005 (partial output), QT-TO-007 (required -> failed), QT-TO-009 (optional -> no effect), QT-TO-010 (continue) |
| Truncation | QT-TR-001 (keep tail), QT-TR-002 (per stream), QT-TR-003 (flags), QT-TR-004 (original length), QT-TR-005 ("longer than" boundary), QT-TR-007 (console not truncated) |
| Evidence / dry-run | QT-EV-001, QT-DR-001, QT-DR-002, QT-DR-003 |
| Compatibility | QT-COMP-001, QT-COMP-002 |
| Out of scope | QT-OOS-001, QT-OOS-002, QT-OOS-003 |
| Purpose (NFR) | QT-NFR-001 |

## 3. Invariants (testable)

- I-1 (QT-NFR-001): every executed command has a finite timeout greater than 0. The runner never waits on a direct child for longer than its timeout plus the kill/reap time.
- I-2 (QT-NFR-002): for every record, `len(stdout) <= N` and `len(stderr) <= N`; the stored value is a suffix of the original; `*_truncated == (original_len > N)`; `*_original_chars == original_len`.
- I-3 (QT-VAL-008, QT-VAL-009): an invalid new setting means no child process is started and no evidence file is written.
- I-4 (QT-TO-002/003): `status == "timeout"` implies `exit_code is None` and `duration_seconds` is not null.
- I-5 (QT-TO-007/009, QT-COMP-003): `overall_status == "failed"` exactly when some required record has status `failed`, `error` or `timeout`. `overall_status` is always one of `failed`, `dry_run` or `passed`.
- I-6 (QT-EV-001): every record has `timeout_seconds` equal to the command's override if it has one, otherwise the default.
- I-7 (QT-TO-010, QT-OOS-001/002): there is one record per configured command, in config order, and each command runs at most once.

## 4. Non-functional requirements

- Reliability: QT-NFR-001, QT-TO-006 (decoding partial output must never crash the runner).
- Size/performance: QT-NFR-002. Note: the full output is still held in memory before truncation (see R-3).
- Observability: QT-VAL-007, QT-TO-011, QT-TR-007.
- Operations/compatibility: QT-COMP-001..005. Stdlib only, Python 3.11.

## 5. Ambiguities and contradictions

Each item gives a recommended resolution, which the manifest currently encodes. A human should confirm each one before implementation.

- A-1 Contradiction: argv timing vs "before running anything" (QT-VAL-010, QT-VAL-008). The design says the new validation "matches how a bad argv is handled today". At baseline, though, argv is validated inside the run loop, so commands before a bad argv have already run. The new settings must be validated up front (explicit). Options: (a) leave argv validation where it is (smallest change, fully backwards-compatible, but the two checks behave differently); (b) also move argv validation up front (consistent, but an observable change for configs with a bad argv later in the list). **Recommendation: (a)**, as encoded in QT-VAL-010. Record the decision in `decisions.md`. If (b) is chosen, invert the regression test.
- A-2 Integral floats for `max_output_chars` (QT-CFG-007). The design says "positive integer" but does not say whether `20000.0` is accepted. **Recommendation: reject all floats.**
- A-3 Floats for `timeout_seconds` (QT-CFG-004). Only `default_timeout_seconds` has a type ("positive number"). **Recommendation: per-command `timeout_seconds` uses the same domain (int or float).**
- A-4 Non-finite timeouts (QT-CFG-008). TOML allows `inf`/`nan`. A naive `> 0` check rejects `nan` but accepts `inf`, which would turn the timeout off. **Recommendation: reject non-finite values.**
- A-5 Truncation fields when nothing is truncated (QT-TR-006). The design only defines the values when truncation happens. **Recommendation: always include all four fields on every record (`false` and the actual length).** The alternative is to leave them out unless truncated.
- A-6 Partial output on timeout is bytes or None (QT-TO-006). `subprocess.TimeoutExpired.stdout`/`.stderr` are bytes even with `text=True`, and may be `None`. On POSIX, `subprocess.run` fills them before re-raising; on Windows they come from a second `communicate()`. **Recommendation: decode with the locale preferred encoding and `errors="replace"`; turn `None` into `""`.** Alternative: run `Popen` directly and read the output yourself. That is more code, and the result is the same.
- A-7 Which records get the new fields (QT-EV-001, QT-TR-006, QT-TR-008). "Each check record" is read as covering every status, including `error` (missing executable) and `dry_run`. Truncation also applies to timeout partial output and to error-record stderr (inferred: the evidence-size goal requires it).
- A-8 Tension: "keep their meanings" (QT-COMP-002). `stdout`/`stderr` can now hold only the tail of the output, and `status` gets a new value, `timeout`. Treat both as additive and documented. Consumers that check `status` against a fixed set of values may need updating. Human acknowledgement needed.
- A-9 Console output on timeout (QT-TO-011). Not specified. **Recommendation: print the partial output untruncated, plus an `ERROR:` line on stderr giving the command name and timeout.**
- A-10 What counts as a character (QT-TR-009). **Recommendation: Python str code points after decoding.**
- A-11 `timeout_seconds` value type in evidence (QT-EV-002). **Recommendation: write the configured value unchanged (600 stays an int).**
- A-12 Error message detail (QT-VAL-006 note, QT-VAL-007). The message names the field and, for per-command errors, the command. It goes to stderr with the `ERROR:` prefix (inferred from the argv convention).
- A-13 Evidence on validation failure (QT-VAL-009). Inferred from the argv path: nothing is written, and an existing evidence file is not overwritten.
- A-14 Exit codes (QT-TO-008, QT-COMP-004). Inferred: a required timeout gives exit 1, an optional-only timeout gives exit 0, and invalid settings give exit 2.
- A-15 `overall_status` values (QT-COMP-003). Inferred: no new overall value is added.
- A-16 Not in the manifest, noted for completeness: there is no per-command `max_output_chars` in the design (assume none). Unknown keys stay ignored, as today. `default_timeout_seconds` is validated even when every command overrides it, because the rule covers any value that is present. If several fields are invalid, report at least the first; the order is unspecified.

## 6. Proposed acceptance-test strategy

- Most tests are integration tests that run `run_quality.py` as a subprocess (`sys.executable`). Each test writes its own temporary TOML config and `--output` path, and uses small `python -c` children (sleep, print N chars, write marker/counter/PID files, ignore SIGTERM). Use sub-second timeouts (0.3 to 0.5 s) with generous upper bounds (< 10 s) so the tests are not flaky.
- Validation is tested with a parametrised matrix: {`default_timeout_seconds`, `timeout_seconds`, `max_output_chars`} x {0, 0.0, -1, "600", true, false, [1], inf, nan, 20000.0 (max_output_chars only)}. Each case asserts exit code == 2, the field name appears in stderr, the marker file is absent, and no evidence file is written. Run the matrix again with `--dry-run`.
- Boundary cases: N and N+1 characters; empty output; a multi-byte tail; partial output that cannot be decoded.
- Regression: compare against the baseline script (`git show 4020eaa:.github/agent-scripts/run_quality.py`) on legacy configs, ignoring `generated_at` and `duration_seconds` and the new fields.
- Property test (stdlib `random`, seeded) for the truncation invariant I-2. If truncation is a pure helper, also unit-test it.
- Mutation checks to demonstrate: `>` changed to `>=` in the truncation check (QT-TR-005); head kept instead of tail (QT-TR-001); the bool check removed (QT-VAL-004, which `true` catches); validation done inside the loop (QT-VAL-008); an optional timeout setting overall failed (QT-TO-009).
- Review-only checks: QT-COMP-005, QT-OOS-003 and part of QT-NFR-001.

## 7. Risks and assumptions

Assumptions needing sign-off: QT-CFG-007, QT-CFG-008, QT-VAL-010, QT-TO-006, QT-TO-011, QT-TR-006, QT-TR-009, QT-EV-002.
Inferred requirements needing sign-off: QT-CFG-004, QT-VAL-007, QT-VAL-009, QT-TO-008, QT-TR-008, QT-COMP-003, QT-COMP-004, QT-COMP-005, QT-NFR-002.

Risks:
- R-1 (residual, by design, QT-OOS-003): only the direct child is killed. Grandchildren (for example, pytest workers or tools started by a wrapper script) can outlive the runner. On Windows, a grandchild holding the pipes can block the second `communicate()` inside `subprocess.run`, so QT-NFR-001 cannot be fully guaranteed there.
- R-2: SIGKILL gives the child no chance to flush, so output it buffered but had not yet written is lost. Only output that was already written to the pipe appears in the evidence (QT-TO-005 tests must use `flush=True`).
- R-3: capture is still unbounded in memory. A child that writes gigabytes before timing out can exhaust memory before truncation. The design caps only the evidence size.
- R-4: timing-based tests can be flaky on slow CI. Use wide margins.
- R-5: consumers that check record `status` against a fixed set of values will see the new value `timeout` (A-8).
- R-6: the 600-second default applies to existing configs. Legitimately long suites (more than 10 minutes) will start timing out and need `default_timeout_seconds` or `timeout_seconds` raised. This is an intended behaviour change (QT-COMP-001) and should be mentioned in release notes.
