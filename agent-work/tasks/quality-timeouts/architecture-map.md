# Architecture map: quality-runner timeouts and output truncation

Source: Codebase Researcher subagent (read-only), 2026-11-05. Facts are cited as file:line against baseline 4020eaa. Items marked **(inference)** are the researcher's reasoning.

## 1. Affected areas

| Component | Role | Relationship |
|---|---|---|
| `.github/agent-scripts/run_quality.py` | Reads the TOML config, runs commands in sequence, prints output, writes JSON evidence | Primary target |
| `.github/agent-quality.toml` | `[quality]` holds `working_directory`; `[[quality.commands]]` holds `name`, `required`, `argv` | Input; its comments document behaviour |
| `agent-work/quality-results.json` | Evidence output (gitignored by suggestion, `.gitignore.agent-work:4`) | Output |
| `.github/agent-scripts/build_report.py` | Reads the evidence file and renders a Markdown table | Only code consumer |
| `.github/agents/feature-builder.agent.md:94` | Stage 7 invocation | Invocation only |
| `README.md:29, :84, :86-90, :95` | Install (`--dry-run`), Python requirement, runner description | Docs |

Data flow: TOML → `main()` → per-command record dicts → payload → `json.dumps` to `--output`. `build_report.py:41` reads the hard-coded default path.

## 2. run_quality.py structure and conventions

- A single `main() -> int` (`:13-95`) and a `raise SystemExit(main())` guard (`:97-98`). No helpers or module constants. argparse reads `sys.argv`.
- CLI: `--config`, `--dry-run`, `--output`. All three are cwd-relative.
- Validation:
  - A config read or parse error prints `ERROR reading config: …` and returns 2 (`:20-24`).
  - `quality` is not type-checked (`:26`).
  - `working_directory` resolves against the process cwd (`:27`).
  - An empty `commands` list returns 2 (`:28-31`).
  - **argv is validated inside the run loop** (`:39-41`). Earlier commands have already run, and no evidence is written.
  - `required = bool(...)` is loose (`:38`).
- Record key order: `name, command, required, status, exit_code, duration_seconds, stdout, stderr` (`:44-53`).
- Check statuses: `not_run` (initial, never emitted), `dry_run`, `passed`, `failed`, `error` (FileNotFoundError).
- Overall status: `failed` if a required command failed or errored, otherwise `dry_run` or `passed` (`:88`).
- Exit codes: 0 means ok or dry-run, 1 means a required check failed, 2 means a config or validation error.
- Console: a header on stdout (also printed in dry-run). Child stdout and stderr are echoed in full after completion, not streamed. Errors go to stderr with an `ERROR:` prefix. A footer prints status and the evidence path.
- Only `FileNotFoundError` is caught. Other OSErrors escape as tracebacks (pre-existing).
- Duration uses `time.monotonic()`, rounded to 3 dp.
- Analogous patterns:
  - `validate_requirements.py:39-86`: upfront `validate()` returns `list[str]`.
  - `validate_requirements.py:10-13`: module constant sets.
  - Small pure helpers next to `main()`.

## 3. Consumers of quality-results.json

- `build_report.py:41-49` is the only code consumer. It reads `overall_status`, and per check `name/required/status/exit_code`, through `.get()` and renders them verbatim.
  - It enumerates no statuses. `timeout` renders as-is and `exit_code: null` renders as `None` (the same already happens for `error`/`dry_run`).
  - It ignores extra fields.
- No other code parses the JSON. `overall_status` vocabulary is unchanged.

## 4. Docs to update

- `.github/agent-quality.toml:1-3` header comments: new keys, defaults, timeout semantics.
- `README.md:86-90` Quality runner section: timeouts, the `timeout` status, truncation, new fields.
- `README.md:95` Safety: residual risk that grandchild processes are not killed.
- `README.md:84`: no change (Python 3.11+, stdlib only).

## 5. Version and dependency policy

- `tomllib` requires 3.11+. `README.md:84` says stdlib only, with no package installation needed. The venv is CPython 3.11.4.
- There is no pyproject, pytest.ini, conftest or ruff config in the repo. Ruff rules I0/UP/SIM are active from a source the researcher could not locate.

## 6. Test location and import strategy

- There are no tests. Baseline pytest exits 5.
- pytest's default `norecursedirs` includes `.*`, so tests under `.github/` are not collected.
- **Recommended location:** top-level `tests/test_run_quality.py`.
- **Approach:** black-box subprocess.
  - Run `[sys.executable, SCRIPT, --config tmp, --output tmp]` with `cwd=tmp_path`.
  - Child commands are `[sys.executable, "-c", ...]`.
  - Use importlib for pure-helper tests where useful.
- **Hygiene:**
  - Never use the default config, which would recurse into pytest.
  - Always write `--output` under `tmp_path`.
  - Flush partial output in timeout children.
  - Use generous timing bounds.

## 7. subprocess timeout pitfalls (CPython 3.11)

- On POSIX, `TimeoutExpired.stdout/.stderr` are **bytes even with text=True, or None**. On Windows they may be `str`. Normalise: None → "", bytes → decode with `errors="replace"`, str unchanged.
- `kill()` sends SIGKILL to the direct child only, so grandchildren are orphaned (process-group kill is out of scope).
- A grandchild that holds the pipe can produce a timeout even though the direct child exited.
- Windows may hang on the post-kill communicate (CPython limitation).
- `bool` is a subclass of `int`, so reject it first.
- TOML permits `inf`/`nan`. `nan > 0` is False. `inf` passes `> 0` but may overflow the select timeout **(inference)**, so reject non-finite values.
- Truncation by `s[-n:]` counts code points, and `*_original_chars = len(full)`.

## 8. Undocumented conventions

- Script layout: shebang, docstring used as the argparse description, `from __future__ import annotations`, `main() -> int`.
- `ERROR:` messages go to stderr, and exit 2 means bad input.
- Every record has all keys with None/"" defaults. New keys should go into the initial dict **(inference)**.
- JSON is written with `indent=2`, a trailing newline, UTF-8.

## Recommendations (researcher)

1. Add an upfront validation pass (argv plus all new numeric settings) before any command runs.
2. Keep the change within `run_quality.py` using small pure helpers.
3. Catch `TimeoutExpired`: normalise its output, echo it untruncated, fail only if the command is required, and continue.
4. Add `timeout_seconds` to every record, including dry-run.
5. Reject bool and non-finite values.
6. Put tests in `tests/test_run_quality.py`, run by subprocess.
7. Update the toml comments and README.
8. Record the residual risks.

## Risks (researcher)

- R1: The design says invalid values are handled "matches how a bad argv is handled today", but argv is validated mid-loop.
- R2: Exit-2 paths write no evidence, so stale evidence is possible.
- R3: The 600 s default may fail long suites.
- R4: The bytes/None type of timeout output must be tested with real timeouts.
- R5: Orphaned grandchildren.
- R6: Recursion and clobbering in tests.
- R7: Flaky timing.
- R8: A top-level `tests/` dir is not part of what consumers copy.
- R9: Ruff rules from an unknown source.
- R10: Pre-existing unhandled exceptions.

## Open questions raised

1. Truncation fields: always present, or only when truncated?
2. Reject `inf`?
3. Move argv validation upfront?
4. Test location?
5. Change build_report?
6. `main(argv=None)`?
7. A console message on timeout?
