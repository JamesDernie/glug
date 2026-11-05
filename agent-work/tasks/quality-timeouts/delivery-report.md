# Delivery report: Quality-runner timeouts and output limits

## Requirement status

Total requirements: **53**

| Status | Count |
|---|---:|
| verified | 53 |

## Traceability

| ID | Priority | Status | Description |
|---|---|---|---|
| QT-CFG-001 | high | verified | The runner accepts an optional `[quality].default_timeout_seconds` set to a positive number (TOML integer or float) and uses it as the timeout for every command that does not set its own `timeout_seconds`. |
| QT-CFG-002 | high | verified | When `[quality].default_timeout_seconds` is absent, the default timeout is 600 seconds. |
| QT-CFG-003 | high | verified | A `timeout_seconds` value on a `[[quality.commands]]` entry overrides the default timeout for that command only; other commands keep the default. |
| QT-CFG-004 | high | verified | Per-command `timeout_seconds` accepts the same value domain as `default_timeout_seconds` (positive TOML integer or float) and is subject to the same rejection rules (QT-VAL-001..004, QT-CFG-008). |
| QT-CFG-005 | high | verified | The runner accepts an optional `[quality].max_output_chars` set to a positive TOML integer. |
| QT-CFG-006 | high | verified | When `[quality].max_output_chars` is absent, the limit is 20000 characters. |
| QT-CFG-007 | medium | verified | A float value for `max_output_chars`, including an integral float such as 20000.0, is rejected: exit code 2, error naming `max_output_chars`, nothing run. |
| QT-CFG-008 | medium | verified | Non-finite floats (`inf`, `-inf`, `nan`, all valid TOML) are rejected for `default_timeout_seconds` and `timeout_seconds` with exit code 2 and an error naming the field. |
| QT-VAL-001 | critical | verified | A zero value (0 or 0.0) for `default_timeout_seconds`, `timeout_seconds` or `max_output_chars` is rejected. |
| QT-VAL-002 | critical | verified | A negative value for `default_timeout_seconds`, `timeout_seconds` or `max_output_chars` is rejected. |
| QT-VAL-003 | critical | verified | A non-numeric value (string, including numeric-looking strings such as "600"; array; inline table; TOML date/time) for `default_timeout_seconds`, `timeout_seconds` or `max_output_chars` is rejected. |
| QT-VAL-004 | critical | verified | A boolean value (`true` or `false`) for `default_timeout_seconds`, `timeout_seconds` or `max_output_chars` is rejected, even though Python's bool is a subclass of int. |
| QT-VAL-005 | critical | verified | Any invalid timeout or output setting makes the runner exit with code 2. |
| QT-VAL-006 | high | verified | The validation error message contains the name of the offending field (`default_timeout_seconds`, `timeout_seconds` or `max_output_chars`); for `timeout_seconds` it also identifies the command (by name). |
| QT-VAL-007 | low | verified | Validation errors are written to stderr with the existing `ERROR:` prefix convention. |
| QT-VAL-008 | critical | verified | All timeout and output settings, including `timeout_seconds` on every command entry, are validated before any command is executed; an invalid value on a later command prevents earlier commands from running. |
| QT-VAL-009 | medium | verified | On a validation failure of the new settings no evidence file is written, and an existing evidence file at the output path is left unchanged. |
| QT-VAL-010 | medium | verified | `argv` validation moves into the upfront validation pass: an invalid `argv` on any command makes the runner exit 2 with its existing `ERROR: <name>: argv must be a non-empty array of strings.` message before any command runs (and without writing evidence). |
| QT-TO-001 | critical | verified | A command still running when its effective timeout elapses is killed and the runner does not wait for it beyond the kill. |
| QT-TO-002 | critical | verified | A timed-out command's record has `status` equal to "timeout". |
| QT-TO-003 | high | verified | A timed-out command's record has `exit_code` equal to JSON null. |
| QT-TO-004 | high | verified | A timed-out command's record has `duration_seconds` set to the measured elapsed time (rounded to 3 decimals as for other records), which is at least the timeout used. |
| QT-TO-005 | high | verified | A timed-out command's record `stdout` and `stderr` contain the output the command produced before it was killed (subject to truncation), not empty strings. |
| QT-TO-006 | high | verified | Partial output from a timeout is always stored as a string: bytes from `subprocess.TimeoutExpired` are decoded with the same encoding text mode would use (locale preferred encoding) using `errors="replace"`, and `None` becomes an empty string. |
| QT-TO-007 | critical | verified | A timeout on a required command makes `overall_status` "failed". |
| QT-TO-008 | high | verified | When a required command times out, the runner's process exit code is 1. |
| QT-TO-009 | critical | verified | A timeout on an optional (`required = false`) command does not make `overall_status` "failed"; if nothing else fails the overall status is "passed" and the exit code is 0. |
| QT-TO-010 | critical | verified | After a command times out, the runner continues to execute the remaining commands in order and records them. |
| QT-TO-011 | medium | verified | On a timeout the console shows the command's partial stdout/stderr (untruncated, like normal output) and an `ERROR:` line on stderr stating that the command timed out and the timeout used. |
| QT-TR-001 | critical | verified | If a record's stdout is longer than `max_output_chars`, the evidence keeps only the last `max_output_chars` characters of it. |
| QT-TR-002 | high | verified | The `max_output_chars` limit is applied to stderr independently of stdout: each stream is checked and truncated on its own length. |
| QT-TR-003 | high | verified | When stdout (or stderr) is truncated, the record sets `stdout_truncated` (or `stderr_truncated`) to `true`. |
| QT-TR-004 | high | verified | When stdout (or stderr) is truncated, the record sets `stdout_original_chars` (or `stderr_original_chars`) to the length in characters of the full output before truncation. |
| QT-TR-005 | high | verified | Output whose length equals `max_output_chars` exactly is not truncated; output one character longer is truncated. |
| QT-TR-006 | medium | verified | Every check record (all statuses: passed, failed, timeout, error, dry_run) always contains `stdout_truncated`, `stderr_truncated`, `stdout_original_chars` and `stderr_original_chars`; when a stream is not truncated its flag is `false` and its original-chars value is the stored length (0 for empty output). |
| QT-TR-007 | high | verified | Console echo of command stdout/stderr is the full, untruncated output, regardless of `max_output_chars`. |
| QT-TR-008 | medium | verified | Truncation also applies to partial output in timeout records and to the stderr message stored in error records. |
| QT-TR-009 | medium | verified | Characters are counted as Python `str` code points of the decoded output (not bytes); the original-chars value is the code-point length before truncation, and truncation never splits the stored value into invalid text. |
| QT-EV-001 | high | verified | Every check record (all statuses, including error and dry_run) contains `timeout_seconds` set to the effective timeout for that command: its own `timeout_seconds` if set, else `default_timeout_seconds`, else 600. |
| QT-EV-002 | low | verified | `timeout_seconds` is recorded as the configured numeric value without type conversion (integer stays integer, float stays float; the built-in default is the integer 600). |
| QT-DR-001 | high | verified | With `--dry-run` the runner still executes no command (records keep status "dry_run"). |
| QT-DR-002 | high | verified | With `--dry-run`, invalid timeout or output settings are rejected exactly as in a real run (exit code 2, error naming the field, no evidence written). |
| QT-DR-003 | high | verified | Each dry-run record reports in `timeout_seconds` the timeout the command would use. |
| QT-COMP-001 | high | verified | A config file with none of the new keys produces the same behaviour as at the baseline commit (statuses, overall_status, exit codes, console output, existing record fields), except that each command now has a 600-second timeout. |
| QT-COMP-002 | high | verified | Existing fields of `quality-results.json` (top-level: generated_at, working_directory, dry_run, overall_status, checks; per record: name, command, required, status, exit_code, duration_seconds, stdout, stderr) keep their names and meanings; new fields are only added. |
| QT-COMP-003 | medium | verified | `overall_status` keeps exactly the values "failed", "dry_run" and "passed"; "timeout" appears only as a record status. |
| QT-COMP-004 | medium | verified | Process exit codes keep their meaning: 0 overall passed or dry-run, 1 overall failed, 2 configuration or usage error. |
| QT-COMP-005 | medium | verified | The change uses only the Python 3.11 standard library and adds no dependencies. |
| QT-OOS-001 | low | verified | Retries are out of scope: a timed-out (or failed) command is executed exactly once per run. |
| QT-OOS-002 | low | verified | Parallel execution is out of scope: commands keep running sequentially in configured order, and a timeout does not overlap with the next command. |
| QT-OOS-003 | medium | verified | Killing whole process groups is out of scope: only the direct child process is killed, and the possibility of orphaned grandchild processes is recorded as a residual risk in the task's final report. |
| QT-NFR-001 | critical | verified | Invariant: every executed command runs with a finite, positive timeout, so a non-terminating direct child cannot make the runner hang. |
| QT-NFR-002 | high | verified | Invariant: for every record, len(stdout) <= max_output_chars and len(stderr) <= max_output_chars, so per-record evidence output is bounded by 2 x max_output_chars characters. |

## Configured quality checks

Overall status: **passed**

| Check | Required | Status | Exit code |
|---|---:|---|---:|
| unit-and-integration-tests | True | passed | 0 |
| lint | False | failed | 1 |

## Review and residual risks

Independent review: two passes (Code Reviewer subagent). No critical or high findings.

- REV-001 (medium): oversized timeouts crashed the runner mid-run. **Fixed**: values above 1000000 s are now rejected (D-008).
- REV-002 (low): newlines were not translated in timeout output. **Fixed**.
- REV-003 (low): the Windows hang risk was not documented. **Fixed**.
- REV-004 (low): test gaps. **Fixed**. The legacy expectations are still hand-written from 4020eaa rather than produced by running the baseline script.
- REV-005 (low): an unspecified console line in dry-run output. **Removed**.
- REV-007 (low): the docs gave the maximum for only one timeout field. **Fixed**.
- REV-006 (info, pre-existing): a non-table command entry or undecodable output from a completed command crashes the runner with exit 1. **Accepted as a follow-up**.

Residual risks and unverified areas:

- Only the direct child is killed on timeout. Grandchildren can keep running. On Windows, a grandchild that holds the pipe can still make the runner wait (out of scope by design).
- Configs without a timeout now get a 600 s default, so suites that run longer than 10 minutes will start timing out.
- Output still buffered in the child at kill time is lost. Full output is held in memory before truncation.
- The tests are POSIX-only. Windows is NOT RUN.
- Optional lint fails only on the 5 findings that predate this change. New code adds none.

## Human decision

- [ ] Approved for merge
- [ ] Changes requested

> This report summarizes recorded artifacts. It does not independently prove correctness or authorize merging.
