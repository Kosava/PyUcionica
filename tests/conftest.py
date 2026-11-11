# pyqt6_learning_studio/tests/conftest.py
"""Zajednička podešavanja za pytest: putanja projekta, Qt aplikacija i pomoćnik za pokretanje koda."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from config.settings import RunnerLimits  # noqa: E402
from core.code_runner import CodeRunner, RunResult  # noqa: E402


@pytest.fixture(scope="session")
def qt_app() -> QCoreApplication:
    """Jedna QApplication za sve testove (offscreen — prozori se ne prikazuju)."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    from ui.theme import apply_theme

    apply_theme(app)
    return app


def run_code(
    code: str,
    stdin: str | None = "",
    limits: RunnerLimits | None = None,
    on_runner=None,
    wait_ms: int = 20_000,
) -> RunResult:
    """Pokreće kod i blokira dok se ne završi; vraća RunResult."""
    runner = CodeRunner(limits or RunnerLimits(timeout_ms=5_000))
    results: list[RunResult] = []
    loop = QEventLoop()
    runner.finished.connect(lambda r: (results.append(r), loop.quit()))
    if on_runner is not None:
        on_runner(runner)
    runner.run(code, stdin_text=stdin)
    QTimer.singleShot(wait_ms, loop.quit)
    if not results:
        loop.exec()
    assert results, "Program se nije završio u očekivanom vremenu."
    return results[0]


@pytest.fixture(autouse=True)
def _close_all_databases(monkeypatch):
    """Svaka baza otvorena tokom testa zatvara se posle testa (bez ResourceWarning-a)."""
    from database import database_manager

    created: list = []
    original_init = database_manager.DatabaseManager.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(database_manager.DatabaseManager, "__init__", tracking_init)
    yield
    for db in created:
        db.close()


@pytest.fixture
def run(qt_app):
    return run_code


def run_check(code: str, criteria, wait_ms: int = 60_000):
    """Pokreće sve test slučajeve zadatka (CheckSession) i vraća (CheckReport, rezultati)."""
    from core.check_session import CheckSession

    runner = CodeRunner(RunnerLimits(timeout_ms=5_000))
    session = CheckSession(runner)
    out: list = []
    loop = QEventLoop()
    session.finished.connect(lambda report, results: (out.append((report, results)), loop.quit()))
    session.start(code, criteria)
    QTimer.singleShot(wait_ms, loop.quit)
    if not out:
        loop.exec()
    assert out, "Provera se nije završila u očekivanom vremenu."
    return out[0]
