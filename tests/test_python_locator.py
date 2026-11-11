# pyqt6_learning_studio/tests/test_python_locator.py
"""Testovi izbora Python interpretera i „ugrađenog“ režima spakovane aplikacije."""

from __future__ import annotations

import sys
from pathlib import Path

from config.settings import PROJECT_ROOT, RunnerLimits
from core import python_locator
from core.code_runner import RunStatus
from core.error_explainer import explain_error
from core.python_locator import SELF_RUN_FLAG, Interpreter, locate_python
from models.exercise import CheckCriteria, TestCase
from tests.conftest import run_code

# Ovako spakovana aplikacija pokreće korisnikov kod kada na sistemu nema Pythona:
# „main --pls-run _pls_bootstrap.py“ (ovde: python main.py --pls-run ...).
EMBEDDED = Interpreter(sys.executable, (str(PROJECT_ROOT / "main.py"), SELF_RUN_FLAG), "test", embedded=True)


def test_source_mode_uses_current_python():
    assert locate_python().program == sys.executable


def test_custom_path(tmp_path: Path):
    fake = tmp_path / "python-moj"
    fake.write_text("")
    assert locate_python(str(fake)).program == str(fake)
    wrong = locate_python(str(tmp_path / "nepostoji"))
    assert wrong.program == sys.executable
    assert "ne postoji" in wrong.description


def test_frozen_prefers_system_python(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(python_locator.shutil, "which", lambda name: "/usr/bin/python3" if name == "python3" else None)
    interpreter = locate_python()
    assert interpreter.program == "/usr/bin/python3" and not interpreter.embedded


def test_frozen_without_system_python_uses_embedded(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(python_locator.shutil, "which", lambda name: None)
    interpreter = locate_python()
    assert interpreter.embedded and interpreter.args == (SELF_RUN_FLAG,)


def _run_embedded(code: str, stdin: str | None = "", **kwargs):
    def attach(runner):
        runner.set_interpreter(EMBEDDED)
    return run_code(code, stdin=stdin, on_runner=attach, **kwargs)


def test_embedded_mode_output_and_input(qt_app):
    result = _run_embedded('ime = input("Ime: ")\nprint("Zdravo,", ime)\nprint("Čćžšđ")\n', stdin="Ana")
    assert result.status is RunStatus.SUCCESS, result.stderr
    assert result.stdout == "Ime: Zdravo, Ana\nČćžšđ\n"


def test_embedded_mode_errors(qt_app):
    result = _run_embedded('print("pre")\nPrint("x")\n')
    assert result.status is RunStatus.ERROR
    info = explain_error(result.stderr)
    assert info.exc_type == "NameError" and info.line == 2


def test_embedded_mode_exit_code_and_timeout(qt_app):
    assert _run_embedded("import sys\nsys.exit(4)\n").exit_code == 4
    result = _run_embedded("while True:\n    pass\n", limits=RunnerLimits(timeout_ms=1500, kill_grace_ms=300))
    assert result.status is RunStatus.TIMEOUT


def test_embedded_mode_gui_check(qt_app):
    code = (
        "import sys\nfrom PyQt6.QtWidgets import QApplication, QWidget\n"
        "app = QApplication(sys.argv)\np = QWidget()\np.setWindowTitle('Test')\np.show()\nsys.exit(app.exec())\n"
    )
    criteria = CheckCriteria(cases=(TestCase(gui_script="print('naslov:', glavni().windowTitle())",
                                             output_contains=("naslov: Test",)),))
    from core.check_session import CheckSession
    from core.code_runner import CodeRunner
    from PyQt6.QtCore import QEventLoop, QTimer

    runner = CodeRunner(interpreter=EMBEDDED)
    session = CheckSession(runner)
    out = []
    loop = QEventLoop()
    session.finished.connect(lambda report, results: (out.append(report), loop.quit()))
    session.start(code, criteria)
    QTimer.singleShot(30_000, loop.quit)
    loop.exec()
    assert out and out[0].passed, [(i.message, i.detail) for i in out[0].items]


def test_failed_start_message_mentions_settings(qt_app):
    def attach(runner):
        runner.set_interpreter(Interpreter("/nepostoji/python", (), "x"))
    result = run_code('print(1)\n', on_runner=attach)
    assert result.status is RunStatus.FAILED_TO_START
    assert "Podešavanja" in result.message
