# pyqt6_learning_studio/tests/test_code_runner.py
"""Testovi za izvršavanje koda u zasebnom procesu: izlaz, greške, vreme, unos, ograničenja."""

from __future__ import annotations

import tempfile
from pathlib import Path

from config.settings import RunnerLimits
from core.code_runner import RunStatus
from tests.conftest import run_code


def test_successful_run_captures_stdout(qt_app):
    result = run_code('print("Zdravo, svete!")\nprint(2 + 3)\n')
    assert result.status is RunStatus.SUCCESS
    assert result.exit_code == 0
    assert result.stdout == "Zdravo, svete!\n5\n"
    assert result.stderr == ""


def test_unicode_output(qt_app):
    result = run_code('print("Čćžšđ ČĆŽŠĐ")\n')
    assert result.stdout.strip() == "Čćžšđ ČĆŽŠĐ"


def test_runtime_error_is_reported_with_user_line(qt_app):
    result = run_code('print("pre")\nPrint("greska")\n')
    assert result.status is RunStatus.ERROR
    assert result.stdout == "pre\n"
    assert 'File "main.py", line 2' in result.stderr
    assert "NameError" in result.stderr
    # Interni okviri pomoćnog skripta ne smeju biti prikazani korisniku.
    assert "_pls_bootstrap" not in result.stderr
    assert "_pls_main" not in result.stderr


def test_syntax_error_prevents_execution(qt_app):
    result = run_code('print("ovo se ne izvrsava")\nprint("nezatvoren)\n')
    assert result.status is RunStatus.ERROR
    assert result.stdout == ""
    assert "SyntaxError" in result.stderr
    assert 'line 2' in result.stderr


def test_timeout_stops_infinite_loop(qt_app):
    result = run_code("while True:\n    pass\n", limits=RunnerLimits(timeout_ms=700, kill_grace_ms=500))
    assert result.status is RunStatus.TIMEOUT
    assert result.duration_s < 3


def test_output_limit(qt_app):
    result = run_code(
        "while True:\n    print('x' * 100)\n",
        limits=RunnerLimits(timeout_ms=10_000, max_output_chars=5_000, kill_grace_ms=500),
    )
    assert result.status is RunStatus.OUTPUT_LIMIT
    assert len(result.stdout) + len(result.stderr) <= 5_000


def test_preset_stdin_for_checking(qt_app):
    code = 'ime = input("Ime: ")\nprint("Zdravo,", ime)\n'
    result = run_code(code, stdin="Ana")
    assert result.status is RunStatus.SUCCESS
    assert result.stdout == "Ime: Zdravo, Ana\n"
    assert "PLS_INPUT" not in result.stderr


def test_missing_stdin_raises_eof(qt_app):
    result = run_code('input("Broj: ")\n', stdin="")
    assert result.status is RunStatus.ERROR
    assert "EOFError" in result.stderr


def test_interactive_input_and_paused_timer(qt_app):
    """Vreme čekanja na unos se ne računa u vremensko ograničenje."""
    from PyQt6.QtCore import QTimer

    events: list[str] = []

    def attach(runner):
        def on_request():
            events.append("request")
            # Odgovor stiže tek posle 900 ms — duže od ograničenja od 600 ms.
            QTimer.singleShot(900, lambda: runner.send_input("Marko"))

        runner.input_requested.connect(on_request)

    result = run_code(
        'ime = input("Ime: ")\nprint("Zdravo,", ime)\n',
        stdin=None,
        limits=RunnerLimits(timeout_ms=600, kill_grace_ms=500),
        on_runner=attach,
    )
    assert events == ["request"]
    assert result.status is RunStatus.SUCCESS
    assert result.stdout.endswith("Zdravo, Marko\n")


def test_stop_request(qt_app):
    from PyQt6.QtCore import QTimer

    def attach(runner):
        runner.started.connect(lambda: QTimer.singleShot(300, runner.stop))

    result = run_code(
        "import time\nwhile True:\n    time.sleep(0.05)\n",
        limits=RunnerLimits(timeout_ms=10_000, kill_grace_ms=500),
        on_runner=attach,
    )
    assert result.status is RunStatus.STOPPED


def test_temporary_directory_is_removed(qt_app):
    before = set(Path(tempfile.gettempdir()).glob("pls_run_*"))
    run_code('print("ok")\n')
    after = set(Path(tempfile.gettempdir()).glob("pls_run_*"))
    assert after <= before


def test_exit_code_from_sys_exit(qt_app):
    result = run_code("import sys\nprint('kraj')\nsys.exit(3)\n")
    assert result.status is RunStatus.ERROR
    assert result.exit_code == 3
    assert result.stdout == "kraj\n"


def test_sentinel_never_leaks_into_output(qt_app):
    code = 'a = input("A? ")\nb = input("B? ")\nprint(a + b)\n'
    result = run_code(code, stdin="x\ny")
    assert result.stdout == "A? B? xy\n"
    assert "\x1e" not in result.stdout and "\x1e" not in result.stderr


def test_prompt_and_preset_input_arrive_in_order(qt_app):
    """Pitanje, pa unos — redosled u prikazu mora biti tačan."""
    events: list[str] = []

    def attach(runner):
        runner.stdout_received.connect(lambda t: events.append("out:" + t))
        runner.preset_input_used.connect(lambda t: events.append("in:" + t))

    run_code('x = input("Broj: ")\nprint("dobio", x)\n', stdin="5", on_runner=attach)
    joined = "".join(e.split(":", 1)[1] if e.startswith("out:") else f"[{e[3:]}]" for e in events)
    assert joined == "Broj: [5]dobio 5\n"


def test_split_sentinel_is_reassembled(qt_app):
    """Signal za unos podeljen na dva dela i dalje se prepoznaje."""
    from core.code_runner import INPUT_SENTINEL, CodeRunner

    runner = CodeRunner()
    runner._reset_state()
    runner._interactive = True
    out: list[str] = []
    requests: list[int] = []
    runner.stdout_received.connect(out.append)
    runner.input_requested.connect(lambda: requests.append(1))
    half = len(INPUT_SENTINEL) // 2
    runner._process_stdout_text("Ime: " + INPUT_SENTINEL[:half])
    runner._process_stdout_text(INPUT_SENTINEL[half:] + "kraj")
    runner._process_stdout_text("", final=True)
    assert "".join(out) == "Ime: kraj"
    assert requests == [1]
    runner._pause_clock()
