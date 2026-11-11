# pyqt6_learning_studio/core/check_session.py
"""Provera zadatka kroz jedno ili više pokretanja programa (test slučajeva).

Sesija koristi postojeći :class:`~core.code_runner.CodeRunner`: pokreće slučajeve
jedan za drugim, svaki sa svojim unapred zadatim unosom, skuplja rezultate i
na kraju ih predaje funkciji :func:`~core.exercise_checker.evaluate`.

Ako neki slučaj prekorači vreme ili bude prekinut, preostali se ne pokreću.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.code_runner import CodeRunner, RunResult, RunStatus
from core.exercise_checker import CheckReport, evaluate
from models.exercise import CheckCriteria, TestCase

log = logging.getLogger(__name__)

_STOP_STATUSES = (RunStatus.TIMEOUT, RunStatus.OUTPUT_LIMIT, RunStatus.STOPPED, RunStatus.FAILED_TO_START)


class CheckSession(QObject):
    """Pokreće sve test slučajeve zadatka redom.

    Signals:
        case_started(int, int, TestCase): Počinje slučaj broj ``index`` od ``total``.
        case_finished(int, RunResult): Slučaj je završen.
        finished(CheckReport, list): Provera je gotova — izveštaj i svi rezultati.
    """

    case_started = pyqtSignal(int, int, object)
    case_finished = pyqtSignal(int, object)
    finished = pyqtSignal(object, list)

    def __init__(self, runner: CodeRunner, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._active = False
        self._code = ""
        self._criteria = CheckCriteria()
        self._cases: tuple[TestCase, ...] = ()
        self._results: list[RunResult] = []
        runner.finished.connect(self._on_run_finished)

    def is_active(self) -> bool:
        return self._active

    @property
    def code(self) -> str:
        """Korisnikov kod koji se proverava (bez test koda)."""
        return self._code

    def start(self, code: str, criteria: CheckCriteria) -> bool:
        """Počinje proveru. Vraća ``False`` ako je program već pokrenut."""
        if self._active or self._runner.is_running():
            return False
        self._active = True
        self._code = code
        self._criteria = criteria
        self._cases = criteria.effective_cases()
        self._results = []
        self._run_next()
        return True

    def cancel(self) -> None:
        """Prekida proveru (trenutni program se zaustavlja, ostali se ne pokreću)."""
        if self._active:
            self._runner.stop()

    def _run_next(self) -> None:
        index = len(self._results)
        case = self._cases[index]
        self.case_started.emit(index + 1, len(self._cases), case)
        if not self._runner.run(case.program_for(self._code), stdin_text=case.stdin,
                                gui_script=case.gui_script or None):
            log.error("Runner je zauzet — provera se prekida.")
            self._finish()

    def _on_run_finished(self, result: RunResult) -> None:
        if not self._active:
            return
        self._results.append(result)
        self.case_finished.emit(len(self._results), result)
        if result.status in _STOP_STATUSES or len(self._results) >= len(self._cases):
            self._finish()
        else:
            # Sledeći slučaj pokreni tek kada se trenutni signal potpuno obradi.
            QTimer.singleShot(0, self._run_next)

    def _finish(self) -> None:
        self._active = False
        report: CheckReport = evaluate(self._code, self._results, self._criteria)
        self.finished.emit(report, list(self._results))
