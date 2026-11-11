# pyqt6_learning_studio/tests/test_workflows.py
"""Testovi glavnih tokova rada kroz pravi glavni prozor (bez prikaza na ekranu).

Svaki test prati ono što bi korisnik uradio: otvara lekciju, piše kod, pokreće
ga, proverava zadatak, prelazi na sledeću lekciju, zatvara i ponovo otvara
aplikaciju. Dijalozi sa pitanjima (QMessageBox) se „odgovaraju“ automatski.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QMessageBox

from config.settings import COURSE_FILE
from core.lesson_manager import LessonManager
from core.progress_manager import ProgressManager
from core.settings_manager import SettingsManager
from database.database_manager import DatabaseManager

LESSONS = LessonManager(COURSE_FILE)


# ---------------------------------------------------------------------------
# Pomoćne funkcije
# ---------------------------------------------------------------------------
def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(predicate, timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("Uslov nije ispunjen na vreme.")
        wait(50)


class App:
    """Glavni prozor nad bazom u fajlu, sa mogućnošću „ponovnog pokretanja“."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.window = None
        self.start()

    def start(self):
        from ui.main_window import MainWindow

        self.db = DatabaseManager(self.db_path)
        self.progress = ProgressManager(self.db)
        self.settings = SettingsManager(self.db)
        self.window = MainWindow(LESSONS, self.progress, self.settings)
        self.window.resize(1300, 850)
        self.window.show()
        wait(50)
        return self.window

    def restart(self):
        self.window.close()
        self.db.close()
        return self.start()

    def idle(self):
        w = self.window
        wait_until(lambda: not w._runner.is_running() and not w._check.is_active())
        wait(50)


@pytest.fixture
def app(qt_app, tmp_path: Path):
    instance = App(tmp_path / "test.db")
    yield instance
    w = instance.window
    w.editor_panel.editor.mark_clean()
    w.close()
    instance.db.close()


@pytest.fixture
def answer_dialogs(monkeypatch):
    """Automatski odgovori na QMessageBox: lista tekstova dugmadi koja se „kliknu“, redom."""
    answers: list[str] = []
    asked: list[str] = []

    def fake_exec(box):
        asked.append(box.text())
        wanted = answers.pop(0)
        for button in box.buttons():
            if button.text() == wanted:
                box._fake_clicked = button
                return 0
        raise AssertionError(f"Dijalog nema dugme „{wanted}“: {[b.text() for b in box.buttons()]}")

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: getattr(box, "_fake_clicked", None))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: _pop_standard(answers, asked, a)))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: asked.append(a[2])))
    return answers, asked


def _pop_standard(answers, asked, args):
    asked.append(args[2])
    return QMessageBox.StandardButton.Yes if answers.pop(0) == "Da" else QMessageBox.StandardButton.No


# ---------------------------------------------------------------------------
# Tokovi rada
# ---------------------------------------------------------------------------
def test_full_learning_flow_and_restart(app):
    w = app.window
    assert w._stack.currentIndex() == 0, "Aplikacija počinje na početnoj strani."

    w._continue_learning()
    assert w._lesson.lesson_id == "m01_l01" and w._stack.currentIndex() == 1

    lesson = w._lesson
    w.editor_panel.editor.set_text(lesson.exercise.solution, mark_clean=False)
    w._check_task()
    app.idle()
    assert w._status_run.text() == "Zadatak rešen"
    assert app.progress.is_solved("m01_l01")
    assert app.progress.saved_code("m01_l01") == lesson.exercise.solution
    assert not w.editor_panel.editor.is_modified(), "Tačno rešenje se automatski čuva."

    w.output_panel._on_card_action()        # „Završi lekciju i pređi na sledeću“
    assert app.progress.is_completed("m01_l01")
    assert w._lesson.lesson_id == "m01_l02"

    w = app.restart()
    assert w._stack.currentIndex() == 0
    overview_target = w.home_page._hero_lesson_id
    assert overview_target == "m01_l02", "Posle ponovnog pokretanja nastavlja se sa sledećom lekcijom."
    w._request_lesson("m01_l01")
    assert w.editor_panel.editor.text() == lesson.exercise.solution
    assert w.lesson_panel._complete_btn.isChecked()


def test_wrong_solution_records_attempt(app):
    w = app.window
    w._request_lesson("m02_l06")
    w.editor_panel.editor.set_text('ime = input()\ngodine = int(input())\nprint("Zdravo, Ana!")\n', mark_clean=False)
    w._check_task()
    app.idle()
    assert w._status_run.text() == "Provera nije prošla"
    assert app.progress.attempts("m02_l06") == 1 and not app.progress.is_solved("m02_l06")
    assert w.editor_panel.editor.is_modified(), "Netačno rešenje se ne čuva automatski."


def test_run_with_interactive_input(app):
    w = app.window
    w._request_lesson("m02_l06")
    w.editor_panel.editor.set_text('ime = input("Ime: ")\nprint("Zdravo,", ime)\n', mark_clean=False)
    w._run_code()
    wait_until(lambda: w._runner.is_waiting_for_input())
    assert w.output_panel._input.isEnabled()
    w.output_panel._input.setText("Mila")
    w.output_panel._submit_input()
    app.idle()
    assert "Zdravo, Mila" in w.output_panel._view.toPlainText()
    assert w._status_run.text() == "Uspešno izvršeno"


def test_runtime_error_is_explained_and_marked(app):
    w = app.window
    w._request_lesson("m01_l05")
    w.editor_panel.editor.set_text('print("a")\nprint(1 / 0)\n', mark_clean=False)
    w._run_code()
    app.idle()
    assert w._status_run.text() == "Program je prijavio grešku"
    assert w.output_panel._card_action == "line" and w.output_panel._error_line == 2
    assert "Deljenje nulom" in w.output_panel._card._title.text()


def test_stop_long_running_program(app):
    w = app.window
    w._request_lesson("m01_l01")
    w.editor_panel.editor.set_text("import time\nwhile True:\n    time.sleep(0.05)\n", mark_clean=False)
    w._run_code()
    wait(300)
    assert w._runner.is_running()
    w._stop()
    app.idle()
    assert w._status_run.text() == "Prekinuto"


def test_unsaved_code_cancel_discard_save(app, answer_dialogs):
    answers, asked = answer_dialogs
    w = app.window
    w._request_lesson("m01_l02")
    w.editor_panel.editor.set_text('print("moj kod")\n', mark_clean=False)

    answers.append("Otkaži")
    w._request_lesson("m01_l03")
    assert w._lesson.lesson_id == "m01_l02", "Otkaži zadržava trenutnu lekciju."
    assert "nesačuvane izmene" in asked[-1]

    answers.append("Odbaci izmene")
    w._request_lesson("m01_l03")
    assert w._lesson.lesson_id == "m01_l03"
    assert app.progress.saved_code("m01_l02") is None

    w._request_lesson("m01_l02")
    w.editor_panel.editor.set_text('print("drugi pokušaj")\n', mark_clean=False)
    answers.append("Sačuvaj")
    w._request_lesson("m01_l04")
    assert app.progress.saved_code("m01_l02") == 'print("drugi pokušaj")\n'


def test_close_with_unsaved_code_can_be_cancelled(app, answer_dialogs):
    answers, _ = answer_dialogs
    w = app.window
    w._request_lesson("m01_l01")
    w.editor_panel.editor.set_text("print(42)\n", mark_clean=False)
    answers.append("Otkaži")
    assert not w.close(), "Zatvaranje je otkazano."
    assert w.isVisible()
    answers.append("Sačuvaj")
    assert w.close()
    assert app.progress.saved_code("m01_l01") == "print(42)\n"


def test_reset_starter_code(app, answer_dialogs):
    answers, _ = answer_dialogs
    w = app.window
    w._request_lesson("m01_l01")
    starter = w._lesson.exercise.starter_code
    w.editor_panel.editor.set_text("print('promena')\n", mark_clean=False)
    answers.append("Ne")
    w._reset_code()
    assert w.editor_panel.editor.text() != starter
    answers.append("Da")
    w._reset_code()
    assert w.editor_panel.editor.text() == starter


def test_favorites_and_search_open_lesson(app):
    w = app.window
    w._request_lesson("m03_l06")
    w._toggle_favorite()
    assert app.progress.favorite_ids() == ["m03_l06"]
    w._show_home()
    assert [i.lesson_id for i in w.home_page._overview.favorites] == ["m03_l06"]

    from core.lesson_search import LessonSearch

    hit = LessonSearch(LESSONS).search("ugnježdeni")[0]
    w._request_lesson(hit.info.lesson_id)
    assert w._lesson.lesson_id == "m03_l05" and w._stack.currentIndex() == 1


def test_gui_lesson_check_through_window(app):
    w = app.window
    w._request_lesson("m10_l01")
    w.editor_panel.editor.set_text(w._lesson.exercise.solution, mark_clean=False)
    w._check_task()
    app.idle()
    assert w._status_run.text() == "Zadatak rešen"
    assert app.progress.is_solved("m10_l01")
    assert "Bravo" in w.output_panel._card._title.text()


def test_theme_change_keeps_unsaved_code(qt_app, tmp_path: Path):
    import main as app_main
    from ui.theme import apply_theme, current_theme

    db = DatabaseManager(tmp_path / "t.db")
    controller = app_main.WindowController(qt_app, LESSONS, ProgressManager(db), SettingsManager(db))
    w = controller.create()
    w._request_lesson("m01_l04")
    w.editor_panel.editor.set_text("# nesačuvano\n", mark_clean=False)
    w._choose_theme("dark")
    wait(50)
    new = controller.window
    assert new is not w and current_theme().key == "dark"
    assert new._lesson.lesson_id == "m01_l04"
    assert new.editor_panel.editor.text() == "# nesačuvano\n" and new.editor_panel.editor.is_modified()
    new.editor_panel.editor.mark_clean()
    new.close()
    apply_theme(qt_app, "light")
    db.close()


def test_settings_persist_between_starts(app):
    app.settings.set_many({"runner/timeout_s": 7, "editor/font_size": 13})
    w = app.restart()
    assert w._runner.limits.timeout_ms == 7000
    assert w.output_panel._view.font().pointSize() == 13
