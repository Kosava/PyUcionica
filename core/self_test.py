# pyqt6_learning_studio/core/self_test.py
"""Samoprovera instalacije: ``python main.py --self-test`` (ili ``pyqt6-learning-studio --self-test``).

Proverava sve što je potrebno da aplikacija radi, BEZ diranja korisnikovih
podataka (koristi se baza u memoriji):

1. plan kursa i sve dostupne lekcije mogu da se učitaju,
2. SQLite baza i šema rade,
3. Python interpreter za korisnikov kod može da se pokrene (izlaz, unos, greška),
4. provera prozora (PyQt6, bez prikaza na ekranu) radi,
5. glavni prozor može da se napravi.

Koristi se posle instalacije (PKGBUILD ``check()``) i za proveru PyInstaller paketa.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from config.settings import APP_NAME, APP_VERSION, COURSE_FILE, RunnerLimits


def _wait_for(signal_owner_start: Callable[[Callable], None], timeout_ms: int = 30_000):
    """Pokreće asinhronu operaciju i čeka njen rezultat (ili None posle isteka vremena)."""
    results: list = []
    loop = QEventLoop()

    def done(*values):
        results.append(values if len(values) != 1 else values[0])
        loop.quit()

    signal_owner_start(done)
    QTimer.singleShot(timeout_ms, loop.quit)
    if not results:
        loop.exec()
    return results[0] if results else None


def run_self_test(app: QApplication, out=sys.stdout) -> int:
    """Izvršava sve provere, ispisuje rezultat svake i vraća 0 (sve u redu) ili 1."""
    from core.check_session import CheckSession
    from core.code_runner import CodeRunner, RunStatus
    from core.lesson_manager import LessonManager
    from core.progress_manager import ProgressManager
    from core.python_locator import locate_python
    from core.settings_manager import SettingsManager
    from database.database_manager import DatabaseManager
    from ui.theme import apply_theme

    print(f"{APP_NAME} {APP_VERSION} — samoprovera", file=out)
    failures = 0

    def step(name: str, check: Callable[[], str]) -> None:
        nonlocal failures
        try:
            detail = check()
            print(f"  [OK]    {name}: {detail}", file=out)
        except Exception as exc:  # noqa: BLE001 - svaka greška je neuspela provera
            failures += 1
            print(f"  [GREŠKA] {name}: {type(exc).__name__}: {exc}", file=out)
            traceback.print_exc(file=sys.stderr)

    state: dict = {}

    def course() -> str:
        lessons = LessonManager(COURSE_FILE)
        errors = lessons.validate_all()
        if errors:
            raise RuntimeError("; ".join(errors))
        state["lessons"] = lessons
        return f"{len(lessons.available_lessons)} od {len(lessons.all_lessons)} lekcija"

    def database() -> str:
        db = DatabaseManager(":memory:")
        progress = ProgressManager(db)
        progress.set_completed("test")
        if not progress.is_completed("test"):
            raise RuntimeError("upis u bazu nije uspeo")
        state["db"] = db
        return f"šema verzija {db.schema_version}"

    interpreter = locate_python()
    runner = CodeRunner(RunnerLimits(timeout_ms=20_000), interpreter=interpreter)

    def run_code() -> str:
        def start(done):
            runner.finished.connect(done)
            runner.run('x = input()\nprint("zbir", int(x) + 3)\nprint("čćžšđ")\n', stdin_text="2")
        result = _wait_for(start)
        runner.finished.disconnect()
        if result is None or result.status is not RunStatus.SUCCESS or "zbir 5" not in result.stdout:
            raise RuntimeError(f"neočekivan rezultat: {getattr(result, 'stderr', '') or result}")
        return interpreter.description

    def error_report() -> str:
        def start(done):
            runner.finished.connect(done)
            runner.run('print(1 / 0)\n', stdin_text="")
        result = _wait_for(start)
        runner.finished.disconnect()
        if result is None or "ZeroDivisionError" not in result.stderr:
            raise RuntimeError("greška u programu nije prijavljena")
        return "greške se prijavljuju"

    def gui_check() -> str:
        lessons = state["lessons"]
        lesson = lessons.load("m08_l02")
        session = CheckSession(runner)

        def start(done):
            session.finished.connect(done)
            session.start(lesson.exercise.solution, lesson.exercise.criteria)
        outcome = _wait_for(start)
        if outcome is None or not outcome[0].passed:
            raise RuntimeError("rešenje lekcije 49 nije prošlo proveru prozora")
        return "provera prozora radi"

    def main_window() -> str:
        from ui.main_window import MainWindow

        db = state["db"]
        apply_theme(app)
        window = MainWindow(state["lessons"], ProgressManager(db), SettingsManager(db))
        window.close()
        return "glavni prozor se pravi bez grešaka"

    step("Plan kursa i lekcije", course)
    step("SQLite baza", database)
    step("Pokretanje Python koda", run_code)
    step("Prijava greške u programu", error_report)
    if "lessons" in state:
        step("Provera PyQt6 prozora", gui_check)
    if "lessons" in state and "db" in state:
        step("Glavni prozor", main_window)
    runner.shutdown()

    print("Samoprovera uspešna." if not failures else f"Samoprovera: {failures} greška(e).", file=out)
    return 0 if not failures else 1
