# pyqt6_learning_studio/tests/test_gui_checks.py
"""Testovi provere PyQt6 programa (bez prikaza na ekranu) i ponašanja programa sa prozorom."""

from __future__ import annotations

from config.settings import RunnerLimits
from core.code_runner import RunStatus, uses_pyqt
from core.error_explainer import explain_error
from models.exercise import CheckCriteria, TestCase
from tests.conftest import run_check, run_code

APP = '''import sys
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

app = QApplication(sys.argv)
prozor = QWidget()
prozor.setWindowTitle("Brojač")
oznaka = QLabel("0")
dugme = QPushButton("Povećaj")
raspored = QVBoxLayout(prozor)
raspored.addWidget(oznaka)
raspored.addWidget(dugme)

def povecaj():
    oznaka.setText(str(int(oznaka.text()) + 1))

dugme.clicked.connect(povecaj)
prozor.show()
sys.exit(app.exec())
'''

SCRIPT = '''p = glavni()
print("naslov:", p.windowTitle())
klikni("Povećaj")
klikni("Povećaj")
print("oznaka:", tekst(nadji("QLabel")))
'''


def _criteria(script: str = SCRIPT) -> CheckCriteria:
    return CheckCriteria(cases=(TestCase(gui_script=script,
                                         output_contains=("naslov: Brojač", "oznaka: 2")),))


def test_uses_pyqt():
    assert uses_pyqt("from PyQt6.QtWidgets import QApplication\n")
    assert uses_pyqt("import PyQt6\n")
    assert not uses_pyqt('print("PyQt6 je biblioteka")\n')


def test_gui_check_passes_and_finishes_quickly(qt_app):
    report, results = run_check(APP, _criteria())
    assert report.passed, [(i.message, i.detail) for i in report.items]
    assert results[0].duration_s < 5
    assert "[provera] kraj" in results[0].stdout


def test_gui_check_detects_wrong_behavior(qt_app):
    wrong = APP.replace("int(oznaka.text()) + 1", "int(oznaka.text()) + 2")
    report, _ = run_check(wrong, _criteria())
    assert not report.passed
    assert "oznaka: 4" in report.items[0].detail or "oznaka: 2" in report.items[0].detail


def test_missing_show_is_explained(qt_app):
    report, results = run_check(APP.replace("prozor.show()\n", ""), _criteria())
    assert not report.passed
    assert "Nijedan prozor nije prikazan" in results[0].stdout


def test_missing_exec_fails(qt_app):
    report, results = run_check(APP.replace("sys.exit(app.exec())\n", ""), _criteria())
    assert not report.passed
    assert "[provera] kraj" not in results[0].stdout


def test_error_in_slot_does_not_crash_and_is_reported(qt_app):
    broken = APP.replace("str(int(oznaka.text()) + 1)", "oznaka.text() + 1")
    report, results = run_check(broken, _criteria())
    assert not report.passed
    result = results[0]
    assert result.status is RunStatus.ERROR
    assert "[provera] kraj" in result.stdout, "Prozor ne sme da se sruši zbog greške u slotu."
    info = explain_error(result.stderr)
    assert info.exc_type == "TypeError"
    assert info.line == APP.splitlines().index("    oznaka.setText(str(int(oznaka.text()) + 1))") + 1


def test_gui_program_runs_without_timeout_until_stopped(qt_app):
    """Program sa prozorom ne prekida vremensko ograničenje — radi dok se ne zatvori."""
    code = "import os\nos.environ['QT_QPA_PLATFORM'] = 'offscreen'\n" + APP.replace(
        "sys.exit(app.exec())",
        "from PyQt6.QtCore import QTimer\nQTimer.singleShot(1500, app.quit)\nsys.exit(app.exec())")

    def attach(runner):
        original = runner.run
        runner.run = lambda c, stdin_text=None: original(c, stdin_text, no_timeout=True)

    result = run_code(code, stdin=None, limits=RunnerLimits(timeout_ms=500, kill_grace_ms=300), on_runner=attach)
    assert result.status is RunStatus.SUCCESS
    assert result.duration_s >= 1.0
