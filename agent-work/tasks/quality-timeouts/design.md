# Quality-runner timeouts and output limits

## 1. Purpose

`run_quality.py` must never hang indefinitely, and the evidence file must stay a manageable size.

## 2. Configuration

- `[quality]` may set `default_timeout_seconds` (positive number). If omitted, it defaults to 600.
- Each `[[quality.commands]]` entry may set `timeout_seconds`, which overrides the default for that command.
- `[quality]` may set `max_output_chars` (positive integer, default 20000). It applies separately to stdout and to stderr.
- Zero, negative, non-numeric or boolean values make the runner stop before running anything, with exit code 2 and an error message naming the offending field. This matches how a bad `argv` is handled today.

## 3. Timeout behaviour

- A command that runs past its timeout is killed. Its record gets `status: "timeout"`, `exit_code: null`, its measured `duration_seconds`, and whatever output it produced before being killed.
- A timeout on a required command makes the overall result `failed`. A timeout on an optional command does not.
- The runner carries on with the remaining commands after a timeout.

## 4. Output truncation

- If stdout or stderr is longer than `max_output_chars`, the evidence keeps the **last** `max_output_chars` characters, sets `stdout_truncated` / `stderr_truncated` to `true`, and records the original length in `stdout_original_chars` / `stderr_original_chars`.
- The console output is not truncated.

## 5. Evidence

- Each check record gains `timeout_seconds` (the value actually used).
- `--dry-run` still runs nothing, but it does validate the timeout and output settings and reports the timeout each command would use.

## 6. Compatibility

- Existing config files with none of the new keys behave as before, except for the 600-second default timeout.
- Existing fields in `quality-results.json` keep their names and meanings.

## 7. Out of scope

- Retries.
- Running commands in parallel.
- Killing whole process groups (record this as a residual risk).
