"""Behavioural tests for quality-runner timeouts and output truncation.

Feature: agent-work/tasks/quality-timeouts/ (requirements QT-*).

All tests are black-box: the runner script is executed as a subprocess with a
temporary TOML config and a temporary ``--output`` path, and child commands are
``[sys.executable, "-c", ...]``. The default config and default evidence path are
never used (the default config runs pytest, which would recurse).

The harness runs the runner in its own session and kills the whole process
group if the runner does not finish within ``HARNESS_TIMEOUT`` seconds. That
turns "runner has no timeout enforcement" into a fast, explicit test failure
instead of a hung suite.
"""

from __future__ import annotations

import json
import os
import random
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# The harness uses process groups (start_new_session, os.killpg) and POSIX signals.
pytestmark = pytest.mark.skipif(os.name != "posix", reason="test harness is POSIX-only")

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".github" / "agent-scripts" / "run_quality.py"

# Upper bound on a single runner invocation. Every child that is expected to be
# killed sleeps far longer than this, so finishing within it proves the kill.
HARNESS_TIMEOUT = 8.0
# Short per-command timeout used in timeout scenarios.
SHORT = 0.5
SHORT_TOML = "0.5"
# Child sleeps much longer than any timeout or harness bound.
SLEEP_CODE = "import time; time.sleep(30)"

FIELDS = ("default_timeout_seconds", "timeout_seconds", "max_output_chars")
TIMEOUT_FIELDS = ("default_timeout_seconds", "timeout_seconds")
TRUNC_KEYS = (
    "stdout_truncated",
    "stderr_truncated",
    "stdout_original_chars",
    "stderr_original_chars",
)
BASELINE_RECORD_KEYS = {
    "name",
    "command",
    "required",
    "status",
    "exit_code",
    "duration_seconds",
    "stdout",
    "stderr",
}
BASELINE_PAYLOAD_KEYS = {
    "generated_at",
    "working_directory",
    "dry_run",
    "overall_status",
    "checks",
}
OVERALL_STATUSES = {"failed", "dry_run", "passed"}


# --------------------------------------------------------------------------- #
# Harness helpers
# --------------------------------------------------------------------------- #


def tstr(value: str) -> str:
    """Render a Python str as a TOML basic string."""
    return json.dumps(value, ensure_ascii=False)


def tarray(values: list[str]) -> str:
    return "[" + ", ".join(tstr(v) for v in values) + "]"


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def cmd(
    name: str,
    code: str | None = None,
    *,
    argv: list[str] | None = None,
    argv_raw: str | None = None,
    required: bool | None = None,
    **raw: str,
) -> dict[str, str]:
    """Build a [[quality.commands]] entry as a mapping of key -> raw TOML text."""
    entry: dict[str, str] = {"name": tstr(name)}
    if required is not None:
        entry["required"] = "true" if required else "false"
    if argv_raw is not None:
        entry["argv"] = argv_raw
    elif argv is not None:
        entry["argv"] = tarray(argv)
    elif code is not None:
        entry["argv"] = tarray(py(code))
    entry.update(raw)
    return entry


def write_config(
    tmp_path: Path,
    commands: list[dict[str, str]],
    quality: dict[str, str] | None = None,
) -> Path:
    lines = ["[quality]", f"working_directory = {tstr(str(tmp_path))}"]
    for key, value in (quality or {}).items():
        lines.append(f"{key} = {value}")
    for entry in commands:
        lines.append("")
        lines.append("[[quality.commands]]")
        for key, value in entry.items():
            lines.append(f"{key} = {value}")
    path = tmp_path / "quality.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@dataclass
class Run:
    returncode: int
    stdout: str
    stderr: str
    elapsed: float
    out_path: Path

    @property
    def evidence(self) -> dict[str, Any]:
        assert self.out_path.exists(), (
            f"evidence file not written; rc={self.returncode}\nstderr:\n{self.stderr}"
        )
        return json.loads(self.out_path.read_text(encoding="utf-8"))

    @property
    def checks(self) -> list[dict[str, Any]]:
        return self.evidence["checks"]


def run_runner(
    tmp_path: Path,
    commands: list[dict[str, str]] | None = None,
    quality: dict[str, str] | None = None,
    *,
    dry_run: bool = False,
    config_path: Path | None = None,
) -> Run:
    if config_path is None:
        assert commands is not None
        config_path = write_config(tmp_path, commands, quality)
    out_path = tmp_path / "out" / "quality-results.json"
    argv = [
        sys.executable,
        str(SCRIPT),
        "--config",
        str(config_path),
        "--output",
        str(out_path),
    ]
    if dry_run:
        argv.append("--dry-run")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"  # deterministic UTF-8 for runner decoding and child output
    start = time.monotonic()
    proc = subprocess.Popen(
        argv,
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=HARNESS_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = proc.communicate()
        pytest.fail(
            f"runner did not finish within {HARNESS_TIMEOUT}s (no timeout enforcement?);"
            f" killed it.\nstdout:\n{out[-2000:]}\nstderr:\n{err[-2000:]}"
        )
    return Run(proc.returncode, out, err, time.monotonic() - start, out_path)


def get(record: dict[str, Any], key: str) -> Any:
    assert key in record, (
        f"record {record.get('name')!r} missing {key!r}; keys={sorted(record)}"
    )
    return record[key]


def marker_code(path: Path, text: str = "ran") -> str:
    return f"open({str(path)!r}, 'w').write({text!r})"


def append_code(path: Path, text: str = "x") -> str:
    return f"open({str(path)!r}, 'a').write({text!r} + '\\n')"


def assert_rejected(run: Run, field: str, marker: Path | None = None) -> None:
    """Common assertions for a configuration rejected by upfront validation."""
    assert run.returncode == 2, (
        f"expected exit 2 for invalid {field}, got {run.returncode}\nstderr:\n{run.stderr}"
    )
    error_lines = [ln for ln in run.stderr.splitlines() if ln.startswith("ERROR:")]
    assert any(field in ln for ln in error_lines), (
        f"no 'ERROR:' line naming {field!r} on stderr:\n{run.stderr}"
    )
    if marker is not None:
        assert not marker.exists(), (
            "a command ran even though validation should have failed"
        )
    assert not run.out_path.exists(), (
        "evidence was written despite a validation failure"
    )


def invalid_setup(
    tmp_path: Path, field: str, raw: str
) -> tuple[list[dict[str, str]], dict[str, str], Path]:
    """Command 1 writes a marker; the invalid value is in [quality] or on command 2."""
    marker = tmp_path / "marker.txt"
    quality: dict[str, str] = {}
    second_extra: dict[str, str] = {}
    if field == "timeout_seconds":
        second_extra["timeout_seconds"] = raw
    else:
        quality[field] = raw
    commands = [
        cmd("cmd-alpha", marker_code(marker)),
        cmd("cmd-beta", "print('beta')", **second_extra),
    ]
    return commands, quality, marker


def assert_timed_out(record: dict[str, Any], timeout: float) -> None:
    assert get(record, "status") == "timeout", record
    assert get(record, "exit_code") is None
    duration = get(record, "duration_seconds")
    assert isinstance(duration, float)
    assert duration >= timeout - 0.002, (
        f"duration {duration} shorter than timeout {timeout}"
    )
    assert duration < HARNESS_TIMEOUT


# --------------------------------------------------------------------------- #
# Configuration: accepted values and defaults
# --------------------------------------------------------------------------- #


def test_default_timeout_integer_accepted(tmp_path: Path) -> None:
    """QT-CFG-001, QT-EV-002: integer default_timeout_seconds is accepted and recorded as int."""
    run = run_runner(
        tmp_path,
        [cmd("a", "print('a')"), cmd("b", "print('b')")],
        {"default_timeout_seconds": "5"},
    )
    assert run.returncode == 0, run.stderr
    for rec in run.checks:
        assert rec["status"] == "passed"
        value = get(rec, "timeout_seconds")
        assert value == 5 and type(value) is int


def test_default_timeout_float_accepted(tmp_path: Path) -> None:
    """QT-CFG-001, QT-EV-002: float default_timeout_seconds is accepted and recorded as float."""
    run = run_runner(
        tmp_path, [cmd("a", "print('a')")], {"default_timeout_seconds": "2.5"}
    )
    assert run.returncode == 0, run.stderr
    value = get(run.checks[0], "timeout_seconds")
    assert value == 2.5 and type(value) is float


def test_default_timeout_applies_to_commands(tmp_path: Path) -> None:
    """QT-CFG-001, QT-NFR-001: the default timeout is enforced on commands without an override."""
    run = run_runner(
        tmp_path, [cmd("sleepy", SLEEP_CODE)], {"default_timeout_seconds": SHORT_TOML}
    )
    rec = run.checks[0]
    assert_timed_out(rec, SHORT)
    assert get(rec, "timeout_seconds") == SHORT


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry_run"])
def test_default_timeout_is_600_when_omitted(tmp_path: Path, dry_run: bool) -> None:
    """QT-CFG-002, QT-EV-002: with no timeout keys every record has timeout_seconds == 600 (int)."""
    run = run_runner(
        tmp_path, [cmd("a", "print('a')"), cmd("b", "print('b')")], dry_run=dry_run
    )
    assert run.returncode == 0, run.stderr
    for rec in run.checks:
        value = get(rec, "timeout_seconds")
        assert value == 600 and type(value) is int
    assert '"timeout_seconds": 600,' in run.out_path.read_text(encoding="utf-8")


def test_per_command_timeout_overrides_default(tmp_path: Path) -> None:
    """QT-CFG-003: a short per-command override kills only that command; others use the default."""
    run = run_runner(
        tmp_path,
        [
            cmd("short", SLEEP_CODE, timeout_seconds=SHORT_TOML),
            cmd("uses-default", "import time; time.sleep(1.0); print('done')"),
        ],
        {"default_timeout_seconds": "10"},
    )
    short, default = run.checks
    assert_timed_out(short, SHORT)
    assert get(short, "timeout_seconds") == SHORT
    assert default["status"] == "passed", default
    assert get(default, "timeout_seconds") == 10


def test_override_does_not_leak_to_other_commands(tmp_path: Path) -> None:
    """QT-CFG-003: a long override applies to its command only; the short default still applies."""
    run = run_runner(
        tmp_path,
        [
            cmd(
                "long-override",
                "import time; time.sleep(1.0); print('ok')",
                timeout_seconds="10",
            ),
            cmd("default-short", SLEEP_CODE),
        ],
        {"default_timeout_seconds": SHORT_TOML},
    )
    long_rec, short_rec = run.checks
    assert long_rec["status"] == "passed", long_rec
    assert get(long_rec, "timeout_seconds") == 10
    assert_timed_out(short_rec, SHORT)
    assert get(short_rec, "timeout_seconds") == SHORT


@pytest.mark.parametrize(
    ("raw", "accepted"),
    [
        ("1", True),
        ("1.5", True),
        ("0", False),
        ("-1", False),
        ("0.0", False),
        ('"5"', False),
        ("true", False),
        ("false", False),
        ("[1]", False),
    ],
)
def test_command_timeout_value_domain(tmp_path: Path, raw: str, accepted: bool) -> None:
    """QT-CFG-004: per-command timeout_seconds accepts positive int/float and rejects the rest."""
    commands, quality, marker = invalid_setup(tmp_path, "timeout_seconds", raw)
    run = run_runner(tmp_path, commands, quality)
    if accepted:
        assert run.returncode == 0, run.stderr
        assert marker.exists()
        assert get(run.checks[1], "timeout_seconds") == json.loads(raw)
    else:
        assert_rejected(run, "timeout_seconds", marker)


@pytest.mark.parametrize("limit", [1, 10])
def test_max_output_chars_positive_integer_accepted(tmp_path: Path, limit: int) -> None:
    """QT-CFG-005: a positive integer max_output_chars is accepted and applied."""
    run = run_runner(
        tmp_path,
        [cmd("loud", "import sys; sys.stdout.write('q' * 40)")],
        {"max_output_chars": str(limit)},
    )
    assert run.returncode == 0, run.stderr
    rec = run.checks[0]
    assert rec["stdout"] == "q" * limit
    assert get(rec, "stdout_truncated") is True
    assert get(rec, "stdout_original_chars") == 40


def test_max_output_chars_default_20000(tmp_path: Path) -> None:
    """QT-CFG-006, QT-TR-005: default limit is 20000; exactly 20000 kept, 20001 truncated."""
    run = run_runner(
        tmp_path,
        [
            cmd("exact", "import sys; sys.stdout.write('z' * 20000)"),
            cmd("over", "import sys; sys.stdout.write('A' + 'z' * 20000)"),
        ],
    )
    assert run.returncode == 0, run.stderr
    exact, over = run.checks
    assert exact["stdout"] == "z" * 20000
    assert get(exact, "stdout_truncated") is False
    assert get(exact, "stdout_original_chars") == 20000
    assert over["stdout"] == "z" * 20000
    assert get(over, "stdout_truncated") is True
    assert get(over, "stdout_original_chars") == 20001


@pytest.mark.parametrize("raw", ["20000.0", "1.5"])
def test_max_output_chars_float_rejected(tmp_path: Path, raw: str) -> None:
    """QT-CFG-007, QT-VAL-005, QT-VAL-008, QT-VAL-009: float max_output_chars is rejected."""
    commands, quality, marker = invalid_setup(tmp_path, "max_output_chars", raw)
    assert_rejected(run_runner(tmp_path, commands, quality), "max_output_chars", marker)


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "+inf"])
@pytest.mark.parametrize("field", TIMEOUT_FIELDS)
def test_non_finite_timeouts_rejected(tmp_path: Path, field: str, raw: str) -> None:
    """QT-CFG-008: inf/-inf/nan timeouts are rejected with exit 2 and nothing run."""
    commands, quality, marker = invalid_setup(tmp_path, field, raw)
    assert_rejected(run_runner(tmp_path, commands, quality), field, marker)


HUGE_INT = "9" * 400  # valid TOML integer; too large to convert to float


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry_run"])
@pytest.mark.parametrize("raw", ["1000000.5", "1e7", "1e300", "9223372036854775807", HUGE_INT])
@pytest.mark.parametrize("field", TIMEOUT_FIELDS)
def test_oversized_timeouts_rejected(
    tmp_path: Path, field: str, raw: str, dry_run: bool
) -> None:
    """QT-CFG-008, QT-VAL-005, QT-DR-002 (REV-001): timeouts above the maximum are rejected
    up front (exit 2, nothing run) rather than crashing with OverflowError mid-run."""
    commands, quality, marker = invalid_setup(tmp_path, field, raw)
    assert_rejected(run_runner(tmp_path, commands, quality, dry_run=dry_run), field, marker)


@pytest.mark.parametrize("field", TIMEOUT_FIELDS)
def test_maximum_timeout_accepted(tmp_path: Path, field: str) -> None:
    """REV-001 boundary: the documented maximum (1000000 seconds) is accepted."""
    commands, quality, _marker = invalid_setup(tmp_path, field, "1000000")
    run = run_runner(tmp_path, commands, quality)
    assert run.returncode == 0, run.stderr
    assert get(run.checks[1], "timeout_seconds") == 1_000_000


def test_timeout_partial_output_newlines_translated(tmp_path: Path) -> None:
    """QT-TO-006 (REV-002): partial output of a timed-out command gets the same newline
    translation as text-mode output of a completed command."""
    code = (
        "import sys, time\n"
        "sys.stdout.write('a\\r\\nb\\rc'); sys.stdout.flush()\n"
        "time.sleep(30)\n"
    )
    run = run_runner(tmp_path, [cmd("crlf", code, timeout_seconds=SHORT_TOML)])
    rec = run.checks[0]
    assert_timed_out(rec, SHORT)
    assert get(rec, "stdout") == "a\nb\nc"
    assert get(rec, "stdout_original_chars") == 5


def _load_runner_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_quality_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        (b"", ""),
        (b"plain\n", "plain\n"),
        (b"a\r\nb\rc", "a\nb\nc"),
        ("already text\n", "already text\n"),
    ],
    ids=["none", "empty-bytes", "bytes", "crlf-bytes", "str-passthrough"],
)
def test_coerce_timeout_output(raw: Any, expected: str) -> None:
    """QT-TO-006 (REV-004): unit test of partial-output normalisation (None/bytes/str)."""
    assert _load_runner_module().decode_partial(raw) == expected


def test_coerce_timeout_output_invalid_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """QT-TO-006 (REV-004): bytes are decoded with the locale encoding used by text=True,
    replacing undecodable sequences instead of raising."""
    module = _load_runner_module()
    monkeypatch.setattr(module.locale, "getpreferredencoding", lambda _do_setlocale: "utf-8")
    assert module.decode_partial(b"ok\xff") == "ok�"
    monkeypatch.setattr(module.locale, "getpreferredencoding", lambda _do_setlocale: "latin-1")
    assert module.decode_partial(b"caf\xe9") == "caf\xe9"


# --------------------------------------------------------------------------- #
# Validation: rejection matrix
# --------------------------------------------------------------------------- #


def _cases(
    values_all: list[str], values_timeouts_only: list[str]
) -> list[tuple[str, str]]:
    cases = [(f, v) for f in FIELDS for v in values_all]
    cases += [(f, v) for f in TIMEOUT_FIELDS for v in values_timeouts_only]
    return cases


@pytest.mark.parametrize(("field", "raw"), _cases(["0"], ["0.0"]))
def test_zero_rejected(tmp_path: Path, field: str, raw: str) -> None:
    """QT-VAL-001, QT-VAL-005, QT-VAL-008, QT-VAL-009: zero is rejected."""
    commands, quality, marker = invalid_setup(tmp_path, field, raw)
    assert_rejected(run_runner(tmp_path, commands, quality), field, marker)


@pytest.mark.parametrize(("field", "raw"), _cases(["-1"], ["-0.5"]))
def test_negative_rejected(tmp_path: Path, field: str, raw: str) -> None:
    """QT-VAL-002, QT-VAL-005, QT-VAL-008, QT-VAL-009: negative values are rejected."""
    commands, quality, marker = invalid_setup(tmp_path, field, raw)
    assert_rejected(run_runner(tmp_path, commands, quality), field, marker)


@pytest.mark.parametrize(
    ("field", "raw"),
    _cases(['"600"', '"abc"', "[600]", "{ a = 1 }", "1979-05-27", "07:32:00"], []),
)
def test_non_numeric_rejected(tmp_path: Path, field: str, raw: str) -> None:
    """QT-VAL-003, QT-VAL-005: strings, arrays, inline tables and dates/times are rejected."""
    commands, quality, marker = invalid_setup(tmp_path, field, raw)
    assert_rejected(run_runner(tmp_path, commands, quality), field, marker)


@pytest.mark.parametrize(("field", "raw"), _cases(["true", "false"], []))
def test_boolean_rejected(tmp_path: Path, field: str, raw: str) -> None:
    """QT-VAL-004, QT-VAL-005: booleans are rejected even though bool subclasses int."""
    commands, quality, marker = invalid_setup(tmp_path, field, raw)
    assert_rejected(run_runner(tmp_path, commands, quality), field, marker)


@pytest.mark.parametrize("field", FIELDS)
def test_validation_error_names_field(tmp_path: Path, field: str) -> None:
    """QT-VAL-006: the error names the field; for timeout_seconds it also names the command."""
    commands, quality, marker = invalid_setup(tmp_path, field, "0")
    run = run_runner(tmp_path, commands, quality)
    assert_rejected(run, field, marker)
    if field == "timeout_seconds":
        line = next(ln for ln in run.stderr.splitlines() if field in ln)
        assert "cmd-beta" in line, f"command name missing from error line: {line!r}"
        assert "cmd-alpha" not in line


@pytest.mark.parametrize("field", FIELDS)
def test_validation_error_on_stderr(tmp_path: Path, field: str) -> None:
    """QT-VAL-007: the validation error is on stderr with the ERROR: prefix, not on stdout."""
    commands, quality, _ = invalid_setup(tmp_path, field, "-1")
    run = run_runner(tmp_path, commands, quality)
    assert run.returncode == 2
    assert any(
        ln.startswith("ERROR:") and field in ln for ln in run.stderr.splitlines()
    ), run.stderr
    assert field not in run.stdout


@pytest.mark.parametrize(
    ("field", "raw"),
    [
        ("timeout_seconds", "0"),
        ("default_timeout_seconds", "0"),
        ("max_output_chars", "0"),
    ],
)
def test_invalid_later_command_timeout_runs_nothing(
    tmp_path: Path, field: str, raw: str
) -> None:
    """QT-VAL-008: an invalid setting (on a later command or in [quality]) means nothing runs."""
    marker = tmp_path / "marker.txt"
    marker2 = tmp_path / "marker2.txt"
    quality = {} if field == "timeout_seconds" else {field: raw}
    third_extra = {"timeout_seconds": raw} if field == "timeout_seconds" else {}
    commands = [
        cmd("first", marker_code(marker)),
        cmd("second", marker_code(marker2)),
        cmd("third", "print('third')", **third_extra),
    ]
    run = run_runner(tmp_path, commands, quality)
    assert_rejected(run, field, marker)
    assert not marker2.exists()
    assert "== first ==" not in run.stdout


@pytest.mark.parametrize("field", FIELDS)
def test_validation_failure_writes_no_evidence(tmp_path: Path, field: str) -> None:
    """QT-VAL-009: no evidence is written and a pre-existing evidence file is left unchanged."""
    commands, quality, marker = invalid_setup(tmp_path, field, "0")
    out_path = tmp_path / "out" / "quality-results.json"
    out_path.parent.mkdir(parents=True)
    sentinel = '{"sentinel": "previous evidence"}\n'
    out_path.write_text(sentinel, encoding="utf-8")
    before = out_path.stat().st_mtime_ns
    run = run_runner(tmp_path, commands, quality)
    assert run.returncode == 2, run.stderr
    assert out_path.read_text(encoding="utf-8") == sentinel
    assert out_path.stat().st_mtime_ns == before
    assert not marker.exists()
    # Without a pre-existing file, none is created.
    out_path.unlink()
    run = run_runner(tmp_path, commands, quality)
    assert_rejected(run, field, marker)


@pytest.mark.parametrize(
    "argv_raw",
    [None, "[]", '"python"', '["python", 1]'],
    ids=["missing", "empty", "string", "non-string-item"],
)
def test_invalid_later_argv_runs_nothing(tmp_path: Path, argv_raw: str | None) -> None:
    """QT-VAL-010 (D-001): a bad argv on a later command stops the run before anything executes."""
    marker = tmp_path / "marker.txt"
    bad = {"name": tstr("cmd-bad")}
    if argv_raw is not None:
        bad["argv"] = argv_raw
    run = run_runner(tmp_path, [cmd("first", marker_code(marker)), bad])
    assert run.returncode == 2
    assert (
        "ERROR: cmd-bad: argv must be a non-empty array of strings."
        in run.stderr.splitlines()
    )
    assert not marker.exists(), "earlier command ran before argv validation"
    assert not run.out_path.exists()


# --------------------------------------------------------------------------- #
# Timeout behaviour
# --------------------------------------------------------------------------- #


def test_timed_out_command_is_killed(tmp_path: Path) -> None:
    """QT-TO-001: the timed-out child is killed and the runner does not wait for it."""
    pid_file = tmp_path / "child.pid"
    code = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(30)"
    run = run_runner(tmp_path, [cmd("sleepy", code, timeout_seconds=SHORT_TOML)])
    assert run.elapsed < HARNESS_TIMEOUT
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 3
    alive = True
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            alive = False
            break
        time.sleep(0.05)
    assert not alive, f"child pid {pid} still alive after the runner finished"
    assert run.checks[0]["status"] == "timeout"


def test_timeout_record_status(tmp_path: Path) -> None:
    """QT-TO-002: timed-out record has status 'timeout'."""
    run = run_runner(tmp_path, [cmd("sleepy", SLEEP_CODE, timeout_seconds=SHORT_TOML)])
    assert get(run.checks[0], "status") == "timeout"


def test_timeout_record_exit_code_null(tmp_path: Path) -> None:
    """QT-TO-003: timed-out record has exit_code null (not the kill signal's return code)."""
    run = run_runner(tmp_path, [cmd("sleepy", SLEEP_CODE, timeout_seconds=SHORT_TOML)])
    assert run.checks[0]["status"] == "timeout"
    assert run.checks[0]["exit_code"] is None
    assert re.search(r'"exit_code": null', run.out_path.read_text(encoding="utf-8"))


def test_timeout_record_duration(tmp_path: Path) -> None:
    """QT-TO-004: duration is measured, >= the timeout, well below the child's sleep, 3 dp."""
    run = run_runner(tmp_path, [cmd("sleepy", SLEEP_CODE, timeout_seconds=SHORT_TOML)])
    rec = run.checks[0]
    assert_timed_out(rec, SHORT)
    assert round(rec["duration_seconds"], 3) == rec["duration_seconds"]


PARTIAL_CODE = (
    "import sys, time; "
    "print('BEFORE' + '-OUT', flush=True); "
    "print('BEFORE' + '-ERR', file=sys.stderr, flush=True); "
    "time.sleep(30)"
)


def test_timeout_record_keeps_partial_output(tmp_path: Path) -> None:
    """QT-TO-005, QT-TO-006: partial output before the kill is kept as str (not "b'...'")."""
    run = run_runner(
        tmp_path, [cmd("partial", PARTIAL_CODE, timeout_seconds=SHORT_TOML)]
    )
    rec = run.checks[0]
    assert rec["status"] == "timeout"
    assert isinstance(rec["stdout"], str) and isinstance(rec["stderr"], str)
    assert rec["stdout"] == "BEFORE-OUT\n"
    assert rec["stderr"] == "BEFORE-ERR\n"


def test_timeout_partial_output_undecodable_bytes(tmp_path: Path) -> None:
    """QT-TO-006: undecodable partial bytes are decoded with errors='replace' into a str."""
    code = (
        "import sys, time; "
        "sys.stdout.buffer.write(b'OK' + bytes([0xff, 0xfe]) + b'|' + bytes([0xe2, 0x82])); "
        "sys.stdout.buffer.flush(); time.sleep(30)"
    )
    run = run_runner(tmp_path, [cmd("bytes", code, timeout_seconds=SHORT_TOML)])
    rec = run.checks[0]
    assert rec["status"] == "timeout"
    out = rec["stdout"]
    assert isinstance(out, str)
    assert not out.startswith("b'")
    assert out.startswith("OK")
    assert "|" in out
    assert (
        "�" in out
    )  # runner is forced to UTF-8 (PYTHONUTF8=1), so replace yields U+FFFD


def test_timeout_without_output_records_empty_strings(tmp_path: Path) -> None:
    """QT-TO-006: when the child wrote nothing (None from TimeoutExpired) fields are ''."""
    run = run_runner(tmp_path, [cmd("silent", SLEEP_CODE, timeout_seconds=SHORT_TOML)])
    rec = run.checks[0]
    assert rec["status"] == "timeout"
    assert rec["stdout"] == "" and rec["stderr"] == ""
    assert get(rec, "stdout_original_chars") == 0
    assert get(rec, "stderr_original_chars") == 0


def test_required_timeout_fails_overall(tmp_path: Path) -> None:
    """QT-TO-007, QT-COMP-003: a required timeout makes overall_status 'failed'."""
    run = run_runner(
        tmp_path,
        [
            cmd("ok", "print('ok')"),
            cmd("sleepy", SLEEP_CODE, required=True, timeout_seconds=SHORT_TOML),
        ],
    )
    assert run.evidence["overall_status"] == "failed"
    assert [c["status"] for c in run.checks] == ["passed", "timeout"]


def test_default_required_timeout_fails_overall(tmp_path: Path) -> None:
    """QT-TO-007: 'required' omitted defaults to true, so the timeout fails the run."""
    run = run_runner(tmp_path, [cmd("sleepy", SLEEP_CODE, timeout_seconds=SHORT_TOML)])
    assert run.checks[0]["required"] is True
    assert run.checks[0]["status"] == "timeout"
    assert run.evidence["overall_status"] == "failed"
    assert run.returncode == 1


def test_required_timeout_exit_code_1(tmp_path: Path) -> None:
    """QT-TO-008, QT-COMP-004: required timeout gives process exit code 1."""
    run = run_runner(
        tmp_path, [cmd("sleepy", SLEEP_CODE, required=True, timeout_seconds=SHORT_TOML)]
    )
    assert run.returncode == 1
    assert run.checks[0]["status"] == "timeout"


def test_optional_timeout_does_not_fail_overall(tmp_path: Path) -> None:
    """QT-TO-009, QT-COMP-004: an optional timeout leaves overall 'passed' and exit 0."""
    run = run_runner(
        tmp_path,
        [
            cmd("sleepy", SLEEP_CODE, required=False, timeout_seconds=SHORT_TOML),
            cmd("ok", "print('ok')", required=True),
        ],
    )
    assert [c["status"] for c in run.checks] == ["timeout", "passed"]
    assert run.evidence["overall_status"] == "passed"
    assert run.returncode == 0


def test_runner_continues_after_timeout(tmp_path: Path) -> None:
    """QT-TO-010: after a timeout the remaining commands still run, in order."""
    marker = tmp_path / "after.txt"
    run = run_runner(
        tmp_path,
        [
            cmd("one", "print('one')"),
            cmd("two", SLEEP_CODE, timeout_seconds=SHORT_TOML),
            cmd("three", marker_code(marker)),
        ],
    )
    assert [c["name"] for c in run.checks] == ["one", "two", "three"]
    assert [c["status"] for c in run.checks] == ["passed", "timeout", "passed"]
    assert marker.exists()
    assert run.returncode == 1


def test_timeout_console_output(tmp_path: Path) -> None:
    """QT-TO-011: console shows partial output and an ERROR: timeout line with name and timeout."""
    run = run_runner(
        tmp_path, [cmd("partial-cmd", PARTIAL_CODE, timeout_seconds=SHORT_TOML)]
    )
    assert "BEFORE-OUT" in run.stdout
    assert "BEFORE-ERR" in run.stderr
    lines = [
        ln
        for ln in run.stderr.splitlines()
        if ln.startswith("ERROR:")
        and "partial-cmd" in ln
        and re.search(r"time[d ]?\s*out", ln, re.IGNORECASE)
    ]
    assert lines, f"no ERROR: timeout line for partial-cmd on stderr:\n{run.stderr}"
    assert any("0.5" in ln for ln in lines), f"timeout value not stated: {lines}"


def test_runner_does_not_hang_on_unresponsive_child(tmp_path: Path) -> None:
    """QT-NFR-001: a child that ignores SIGTERM and loops forever is still stopped."""
    code = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('ready', flush=True)\n"
        "while True:\n"
        "    time.sleep(0.1)\n"
    )
    run = run_runner(tmp_path, [cmd("stubborn", code, timeout_seconds=SHORT_TOML)])
    assert run.elapsed < HARNESS_TIMEOUT
    assert_timed_out(run.checks[0], SHORT)


# --------------------------------------------------------------------------- #
# Output truncation
# --------------------------------------------------------------------------- #


def test_stdout_truncated_keeps_tail(tmp_path: Path) -> None:
    """QT-TR-001, QT-TR-003, QT-TR-004: the last N chars are kept, flag true, original length."""
    code = "import sys; sys.stdout.write('HE' + 'AD' + 'x' * 50 + '0123456789')"
    run = run_runner(tmp_path, [cmd("loud", code)], {"max_output_chars": "10"})
    rec = run.checks[0]
    assert rec["stdout"] == "0123456789"
    assert get(rec, "stdout_truncated") is True
    assert get(rec, "stdout_original_chars") == 64


@pytest.mark.parametrize("long_stream", ["stderr", "stdout"])
def test_streams_truncated_independently(tmp_path: Path, long_stream: str) -> None:
    """QT-TR-002, QT-TR-003: each stream is truncated on its own length."""
    short_stream = "stdout" if long_stream == "stderr" else "stderr"
    long_text = "".join(chr(ord("a") + i % 26) for i in range(30))
    code = f"import sys; sys.{long_stream}.write({long_text!r}); sys.{short_stream}.write('short')"
    run = run_runner(tmp_path, [cmd("mixed", code)], {"max_output_chars": "10"})
    rec = run.checks[0]
    assert rec[long_stream] == long_text[-10:]
    assert get(rec, f"{long_stream}_truncated") is True
    assert get(rec, f"{long_stream}_original_chars") == 30
    assert rec[short_stream] == "short"
    assert get(rec, f"{short_stream}_truncated") is False
    assert get(rec, f"{short_stream}_original_chars") == 5


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
@pytest.mark.parametrize("length", [10, 11])
def test_truncation_boundary(tmp_path: Path, stream: str, length: int) -> None:
    """QT-TR-005: exactly N chars is not truncated; N+1 is truncated to the last N."""
    text = "".join(str(i % 10) for i in range(length))
    text = "S" + text[1:]
    code = f"import sys; sys.{stream}.write({text!r})"
    run = run_runner(tmp_path, [cmd("edge", code)], {"max_output_chars": "10"})
    rec = run.checks[0]
    assert get(rec, f"{stream}_original_chars") == length
    if length == 10:
        assert rec[stream] == text
        assert get(rec, f"{stream}_truncated") is False
    else:
        assert rec[stream] == text[-10:]
        assert not rec[stream].startswith("S")
        assert get(rec, f"{stream}_truncated") is True


def _assert_trunc_fields_untruncated(rec: dict[str, Any]) -> None:
    for key in TRUNC_KEYS:
        get(rec, key)
    for stream in ("stdout", "stderr"):
        assert rec[f"{stream}_truncated"] is False, rec
        assert rec[f"{stream}_original_chars"] == len(rec[stream]), rec


def test_truncation_fields_present_on_all_records(tmp_path: Path) -> None:
    """QT-TR-006 (D-003): all four truncation fields are on every record of every status."""
    missing = tmp_path / "no-such-executable"
    run = run_runner(
        tmp_path,
        [
            cmd("passes", "print('hi')"),
            cmd(
                "fails",
                "import sys; sys.stderr.write('bad'); sys.exit(3)",
                required=False,
            ),
            cmd("errors", argv=[str(missing)], required=False),
            cmd(
                "times-out",
                "print('p', flush=True); import time; time.sleep(30)",
                required=False,
                timeout_seconds=SHORT_TOML,
            ),
        ],
    )
    statuses = [c["status"] for c in run.checks]
    assert statuses == ["passed", "failed", "error", "timeout"]
    for rec in run.checks:
        _assert_trunc_fields_untruncated(rec)
    assert run.checks[0]["stdout_original_chars"] == 3
    assert run.checks[3]["stdout_original_chars"] == 2

    dry = run_runner(tmp_path, [cmd("passes", "print('hi')")], dry_run=True)
    rec = dry.checks[0]
    assert rec["status"] == "dry_run"
    _assert_trunc_fields_untruncated(rec)
    assert rec["stdout_original_chars"] == 0 and rec["stderr_original_chars"] == 0


def test_console_output_not_truncated(tmp_path: Path) -> None:
    """QT-TR-007: the console echo is the full output even when evidence is truncated."""
    code = (
        "import sys; sys.stdout.write('HE' + 'AD' + 'y' * 60 + '\\n'); "
        "sys.stderr.write('ER' + 'RHEAD' + 'w' * 60 + '\\n')"
    )
    run = run_runner(tmp_path, [cmd("loud", code)], {"max_output_chars": "10"})
    full_out = "HEAD" + "y" * 60
    full_err = "ERRHEAD" + "w" * 60
    assert full_out in run.stdout
    assert full_err in run.stderr
    rec = run.checks[0]
    assert len(rec["stdout"]) == 10 and len(rec["stderr"]) == 10


def test_timeout_partial_output_truncated(tmp_path: Path) -> None:
    """QT-TR-008: truncation also applies to partial output of a timed-out command."""
    code = (
        "import sys, time; sys.stdout.write('P' + 'p' * 89 + '0123456789'); "
        "sys.stdout.flush(); time.sleep(30)"
    )
    run = run_runner(
        tmp_path,
        [cmd("partial", code, timeout_seconds=SHORT_TOML)],
        {"max_output_chars": "10"},
    )
    rec = run.checks[0]
    assert rec["status"] == "timeout"
    assert rec["stdout"] == "0123456789"
    assert get(rec, "stdout_truncated") is True
    assert get(rec, "stdout_original_chars") == 100


def test_error_record_stderr_truncated(tmp_path: Path) -> None:
    """QT-TR-008: truncation applies to the stderr message stored in error records."""
    missing = tmp_path / ("no-such-executable-" + "m" * 40)
    run = run_runner(
        tmp_path, [cmd("errors", argv=[str(missing)])], {"max_output_chars": "10"}
    )
    rec = run.checks[0]
    assert rec["status"] == "error"
    assert len(rec["stderr"]) == 10
    assert get(rec, "stderr_truncated") is True
    original = get(rec, "stderr_original_chars")
    assert original > 10
    # The console still shows the full, untruncated message (QT-TR-007).
    assert str(missing) in run.stderr
    assert rec["stderr"] in run.stderr


def test_truncation_counts_code_points(tmp_path: Path) -> None:
    """QT-TR-009: characters are str code points, not bytes."""
    code = "import sys; sys.stdout.write('a\\u00e9\\u20ac\\U0001F600b')"
    run = run_runner(tmp_path, [cmd("unicode", code)], {"max_output_chars": "3"})
    rec = run.checks[0]
    assert rec["stdout"] == "€\U0001f600b"
    assert get(rec, "stdout_original_chars") == 5
    assert get(rec, "stdout_truncated") is True


def test_truncation_property(tmp_path: Path) -> None:
    """QT-NFR-002, QT-TR-001..005: stored len <= N, equals tail of original, flags consistent.

    Property-style: stdlib random with a fixed seed generates limits and outputs
    (lengths around and above N, including non-ASCII code points).
    """
    rng = random.Random(20261105)
    alphabet = "abcXYZ019 -_é€\U0001f600\n"
    for trial in range(4):
        limit = rng.randint(1, 12)
        lengths = [
            0,
            1,
            max(limit - 1, 0),
            limit,
            limit + 1,
            2 * limit,
            rng.randint(0, 3 * limit),
        ]
        cases = []
        for n in lengths:
            out = "".join(rng.choice(alphabet) for _ in range(n))
            err = "".join(
                rng.choice(alphabet) for _ in range(rng.randint(0, 3 * limit))
            )
            cases.append((out, err))
        commands = [
            cmd(
                f"case-{i}",
                f"import sys; sys.stdout.write({o!r}); sys.stderr.write({e!r})",
            )
            for i, (o, e) in enumerate(cases)
        ]
        trial_dir = tmp_path / f"trial-{trial}"
        trial_dir.mkdir()
        run = run_runner(trial_dir, commands, {"max_output_chars": str(limit)})
        assert run.returncode == 0, run.stderr
        for (out, err), rec in zip(cases, run.checks, strict=True):
            for stream, original in (("stdout", out), ("stderr", err)):
                stored = rec[stream]
                ctx = f"trial={trial} N={limit} {rec['name']} {stream} original={original!r}"
                assert len(stored) <= limit, ctx
                assert stored == original[-limit:], ctx
                assert original.endswith(stored), ctx
                assert get(rec, f"{stream}_truncated") is (len(original) > limit), ctx
                assert get(rec, f"{stream}_original_chars") == len(original), ctx


# --------------------------------------------------------------------------- #
# Evidence and dry-run
# --------------------------------------------------------------------------- #


def test_timeout_seconds_recorded_on_every_record(tmp_path: Path) -> None:
    """QT-EV-001: every record (passed, failed, error, timeout) has the effective timeout."""
    missing = tmp_path / "no-such-executable"
    run = run_runner(
        tmp_path,
        [
            cmd("passes", "print('ok')", timeout_seconds="3"),
            cmd("fails", "import sys; sys.exit(1)", required=False),
            cmd("errors", argv=[str(missing)], required=False, timeout_seconds="4.5"),
            cmd("times-out", SLEEP_CODE, required=False, timeout_seconds=SHORT_TOML),
        ],
        {"default_timeout_seconds": "7"},
    )
    assert [c["status"] for c in run.checks] == ["passed", "failed", "error", "timeout"]
    assert [get(c, "timeout_seconds") for c in run.checks] == [3, 7, 4.5, SHORT]


def test_timeout_seconds_type_preserved(tmp_path: Path) -> None:
    """QT-EV-002: 600 default stays an int in JSON; a float override stays a float."""
    run = run_runner(
        tmp_path,
        [
            cmd("default", "print('a')"),
            cmd("float", "print('b')", timeout_seconds="2.5"),
        ],
    )
    text = run.out_path.read_text(encoding="utf-8")
    assert '"timeout_seconds": 600,' in text
    assert '"timeout_seconds": 600.0' not in text
    assert '"timeout_seconds": 2.5,' in text
    first, second = run.checks
    assert type(get(first, "timeout_seconds")) is int
    assert type(get(second, "timeout_seconds")) is float


def test_dry_run_runs_nothing(tmp_path: Path) -> None:
    """QT-DR-001: --dry-run executes no command; all records are 'dry_run'."""
    marker = tmp_path / "marker.txt"
    run = run_runner(
        tmp_path,
        [
            cmd("writes", marker_code(marker)),
            cmd("sleeps", SLEEP_CODE, timeout_seconds="1"),
        ],
        {"default_timeout_seconds": "2"},
        dry_run=True,
    )
    assert run.returncode == 0, run.stderr
    assert not marker.exists()
    assert [c["status"] for c in run.checks] == ["dry_run", "dry_run"]
    assert run.evidence["overall_status"] == "dry_run"
    assert run.elapsed < HARNESS_TIMEOUT


@pytest.mark.parametrize(
    ("field", "raw"),
    [
        ("default_timeout_seconds", "0"),
        ("default_timeout_seconds", "nan"),
        ("timeout_seconds", "true"),
        ("timeout_seconds", "-1"),
        ("max_output_chars", "1.5"),
        ("max_output_chars", '"10"'),
    ],
)
def test_dry_run_validates_settings(tmp_path: Path, field: str, raw: str) -> None:
    """QT-DR-002: invalid settings are rejected in --dry-run exactly as in a real run."""
    commands, quality, marker = invalid_setup(tmp_path, field, raw)
    run = run_runner(tmp_path, commands, quality, dry_run=True)
    assert_rejected(run, field, marker)


def test_dry_run_validates_argv(tmp_path: Path) -> None:
    """QT-DR-002, QT-VAL-010: an invalid argv is also rejected in --dry-run (exit 2, no evidence)."""
    run = run_runner(
        tmp_path,
        [cmd("ok", "print('ok')"), {"name": tstr("cmd-bad"), "argv": "[]"}],
        dry_run=True,
    )
    assert run.returncode == 2
    assert "ERROR: cmd-bad: argv must be a non-empty array of strings." in run.stderr
    assert not run.out_path.exists()


def test_dry_run_reports_timeout(tmp_path: Path) -> None:
    """QT-DR-003: dry-run records report the timeout each command would use."""
    run = run_runner(
        tmp_path,
        [
            cmd("override", "print('a')", timeout_seconds="5"),
            cmd("default", "print('b')"),
        ],
        {"default_timeout_seconds": "30"},
        dry_run=True,
    )
    assert run.returncode == 0, run.stderr
    assert [c["status"] for c in run.checks] == ["dry_run", "dry_run"]
    assert [get(c, "timeout_seconds") for c in run.checks] == [5, 30]


# --------------------------------------------------------------------------- #
# Compatibility with legacy configs
# --------------------------------------------------------------------------- #


def _legacy_scenario(name: str, tmp_path: Path) -> tuple[Run, dict[str, Any]]:
    """Return (run, expected) for a legacy config with none of the new keys.

    Expected values are the behaviour of the baseline script at 4020eaa.
    """
    missing = tmp_path / "no-such-executable"
    if name == "pass":
        run = run_runner(tmp_path, [cmd("only", "print('hello')")])
        return run, {
            "rc": 0,
            "overall": "passed",
            "records": [
                {"status": "passed", "exit_code": 0, "stdout": "hello\n", "stderr": ""}
            ],
        }
    if name == "required_fail":
        code = "import sys; print('o'); sys.stderr.write('e\\n'); sys.exit(3)"
        run = run_runner(tmp_path, [cmd("only", code, required=True)])
        return run, {
            "rc": 1,
            "overall": "failed",
            "records": [
                {"status": "failed", "exit_code": 3, "stdout": "o\n", "stderr": "e\n"}
            ],
        }
    if name == "optional_fail":
        code = "import sys; sys.exit(4)"
        run = run_runner(
            tmp_path, [cmd("opt", code, required=False), cmd("ok", "print('ok')")]
        )
        return run, {
            "rc": 0,
            "overall": "passed",
            "records": [
                {"status": "failed", "exit_code": 4, "required": False},
                {"status": "passed", "exit_code": 0, "required": True},
            ],
        }
    if name == "missing_executable":
        run = run_runner(tmp_path, [cmd("only", argv=[str(missing)])])
        return run, {
            "rc": 1,
            "overall": "failed",
            "records": [{"status": "error", "exit_code": None, "stdout": ""}],
        }
    if name == "dry_run":
        run = run_runner(tmp_path, [cmd("only", "print('hello')")], dry_run=True)
        return run, {
            "rc": 0,
            "overall": "dry_run",
            "records": [
                {
                    "status": "dry_run",
                    "exit_code": None,
                    "duration_seconds": None,
                    "stdout": "",
                    "stderr": "",
                }
            ],
        }
    if name == "no_commands":
        run = run_runner(tmp_path, [])
        return run, {
            "rc": 2,
            "stderr_line": "ERROR: no [[quality.commands]] configured.",
        }
    if name == "bad_argv":
        run = run_runner(tmp_path, [{"name": tstr("only"), "argv": "[]"}])
        return run, {
            "rc": 2,
            "stderr_line": "ERROR: only: argv must be a non-empty array of strings.",
        }
    if name == "unreadable_config":
        run = run_runner(tmp_path, config_path=tmp_path / "does-not-exist.toml")
        return run, {"rc": 2, "stderr_prefix": "ERROR reading config:"}
    raise AssertionError(name)


LEGACY_SCENARIOS = [
    "pass",
    "required_fail",
    "optional_fail",
    "missing_executable",
    "dry_run",
    "no_commands",
    "bad_argv",
    "unreadable_config",
]


@pytest.mark.parametrize("scenario", LEGACY_SCENARIOS)
def test_legacy_config_behaviour_unchanged(tmp_path: Path, scenario: str) -> None:
    """QT-COMP-001, QT-COMP-004: legacy configs keep baseline exit codes, statuses and fields."""
    run, expected = _legacy_scenario(scenario, tmp_path)
    assert run.returncode == expected["rc"], run.stderr
    if "records" not in expected:
        assert not run.out_path.exists()
        if "stderr_line" in expected:
            assert expected["stderr_line"] in run.stderr.splitlines()
        if "stderr_prefix" in expected:
            assert run.stderr.startswith(expected["stderr_prefix"])
        return
    payload = run.evidence
    assert payload["overall_status"] == expected["overall"]
    assert payload["dry_run"] is (scenario == "dry_run")
    assert payload["working_directory"] == str(tmp_path.resolve())
    assert len(payload["checks"]) == len(expected["records"])
    for rec, exp in zip(payload["checks"], expected["records"], strict=True):
        for key, value in exp.items():
            assert rec[key] == value, f"{key}: {rec[key]!r} != {value!r}"
        assert rec["command"][0] in (
            sys.executable,
            str(tmp_path / "no-such-executable"),
        )
        if rec["status"] in ("passed", "failed", "error"):
            assert isinstance(rec["duration_seconds"], float)
        # Only additive change: the 600 s default timeout.
        assert get(rec, "timeout_seconds") == 600
        assert "== " + rec["name"] + " ==" in run.stdout
    assert f"Quality status: {expected['overall']}" in run.stdout
    assert f"Evidence: {run.out_path}" in run.stdout


def test_existing_evidence_fields_preserved(tmp_path: Path) -> None:
    """QT-COMP-002: baseline payload and record keys are still present with the same types."""
    missing = tmp_path / "no-such-executable"
    run = run_runner(
        tmp_path,
        [
            cmd("passes", "print('ok')"),
            cmd("fails", "import sys; sys.exit(2)", required=False),
            cmd("errors", argv=[str(missing)], required=False),
        ],
    )
    payload = run.evidence
    assert BASELINE_PAYLOAD_KEYS <= set(payload)
    assert isinstance(payload["generated_at"], str)
    assert isinstance(payload["working_directory"], str)
    assert payload["dry_run"] is False
    assert isinstance(payload["checks"], list)
    for rec in payload["checks"]:
        assert BASELINE_RECORD_KEYS <= set(rec), sorted(BASELINE_RECORD_KEYS - set(rec))
        assert isinstance(rec["name"], str)
        assert isinstance(rec["command"], list)
        assert isinstance(rec["required"], bool)
        assert rec["status"] in {"passed", "failed", "error"}
        assert rec["exit_code"] is None or isinstance(rec["exit_code"], int)
        assert isinstance(rec["duration_seconds"], float)
        assert isinstance(rec["stdout"], str) and isinstance(rec["stderr"], str)


def test_overall_status_values_unchanged(tmp_path: Path) -> None:
    """QT-COMP-003: 'timeout' appears only as a record status, never as overall_status."""
    req = tmp_path / "required"
    opt = tmp_path / "optional"
    req.mkdir()
    opt.mkdir()
    required_run = run_runner(req, [cmd("t", SLEEP_CODE, timeout_seconds=SHORT_TOML)])
    optional_run = run_runner(
        opt, [cmd("t", SLEEP_CODE, required=False, timeout_seconds=SHORT_TOML)]
    )
    for run, expected in ((required_run, "failed"), (optional_run, "passed")):
        assert run.checks[0]["status"] == "timeout"
        assert run.evidence["overall_status"] in OVERALL_STATUSES
        assert run.evidence["overall_status"] == expected


# --------------------------------------------------------------------------- #
# Out-of-scope guarantees
# --------------------------------------------------------------------------- #


def test_timed_out_command_not_retried(tmp_path: Path) -> None:
    """QT-OOS-001: a timed-out command runs exactly once (no retries)."""
    counter = tmp_path / "counter.txt"
    code = append_code(counter, "start") + "; import time; time.sleep(30)"
    run = run_runner(tmp_path, [cmd("once", code, timeout_seconds=SHORT_TOML)])
    assert run.checks[0]["status"] == "timeout"
    assert counter.read_text().splitlines() == ["start"]


def test_commands_run_sequentially(tmp_path: Path) -> None:
    """QT-OOS-002: commands run in order; the next starts only after a timeout kill completes."""
    log = tmp_path / "times.txt"

    def stamp(label: str) -> str:
        return f"import time; open({str(log)!r}, 'a').write({label!r} + ' ' + repr(time.time()) + '\\n')"

    run = run_runner(
        tmp_path,
        [
            cmd(
                "t1",
                stamp("t1-start") + "; time.sleep(30)",
                required=False,
                timeout_seconds=SHORT_TOML,
            ),
            cmd("t2", stamp("t2-start")),
            cmd("t3", "import time; time.sleep(0.3); " + stamp("t3-end")),
            cmd("t4", stamp("t4-start")),
        ],
    )
    assert [c["status"] for c in run.checks] == [
        "timeout",
        "passed",
        "passed",
        "passed",
    ]
    lines = [ln.split() for ln in log.read_text().splitlines()]
    stamps = {label: float(value) for label, value in lines}
    assert list(stamps) == ["t1-start", "t2-start", "t3-end", "t4-start"]
    assert stamps["t2-start"] - stamps["t1-start"] >= SHORT - 0.05
    assert stamps["t4-start"] >= stamps["t3-end"]
