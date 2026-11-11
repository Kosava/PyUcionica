# pyqt6_learning_studio/ui/main_window.py
"""Glavni prozor: početna strana, radni prostor sa tri zone i povezivanje svih delova.

Prozor ima dva prikaza (QStackedWidget):

1. **Početna strana** — napredak, preporučena lekcija, pregled modula.
2. **Radni prostor**::

    ┌──────────┬──────────────────────────────────────────┐
    │ Sadržaj  │  Lekcija (naslov, objašnjenje, primer…)   │  ← gornja zona
    │ kursa    ├─────────────────────┬────────────────────┤
    │ (opcion) │  Editor koda        │  Rezultat          │  ← donja zona
    └──────────┴─────────────────────┴────────────────────┘

Glavni prozor je jedino mesto koje zna za sve delove; paneli međusobno
komuniciraju isključivo preko Qt signala koje on povezuje.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QByteArray, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import APP_ICON, APP_NAME, APP_VERSION
from core.check_session import CheckSession
from core.code_runner import CodeRunner, RunResult, RunStatus, uses_pyqt
from core.course_progress import build_overview, module_entry_lesson
from core.error_explainer import explain_error
from core.exercise_checker import CheckReport
from core.lesson_manager import LessonLoadError, LessonManager
from core.lesson_search import LessonSearch
from config.settings import RunnerLimits
from core.progress_manager import ProgressManager
from core.python_locator import Interpreter, locate_python
from core.settings_manager import USER_SETTINGS, SettingsManager
from models.exercise import TestCase
from models.lesson import Lesson
from ui.editor_panel import EditorPanel
from ui.home_page import HomePage
from ui.lesson_browser import LessonBrowser
from ui.lesson_panel import SIZE_COMPACT, SIZE_EXPANDED, SIZE_NORMAL, LessonPanel
from ui.output_panel import OutputPanel
from ui.code_editor import editor_font, set_default_font_size
from ui.quiz_dialog import QuizDialog
from ui.search_dialog import SearchDialog
from ui.settings_dialog import SettingsDialog
from ui.theme import THEME_CHOICES, current_theme, resolve_theme_key

log = logging.getLogger(__name__)

MODE_RUN = "run"
MODE_CHECK = "check"
VIEW_HOME = 0
VIEW_WORKSPACE = 1
_QWIDGETSIZE_MAX = 16_777_215


class MainWindow(QMainWindow):
    """Glavni prozor aplikacije.

    Signals:
        theme_change_requested(str): Korisnik je izabrao drugu temu. Prozor se
            tada ponovo gradi (vidi ``main.py``), uz prenos stanja preko
            :meth:`snapshot` / :meth:`restore_snapshot`.
    """

    theme_change_requested = pyqtSignal(str)

    def __init__(self, lessons: LessonManager, progress: ProgressManager, settings: SettingsManager) -> None:
        super().__init__()
        self._lessons = lessons
        self._progress = progress
        self._settings = settings
        self._lesson: Lesson | None = None
        self._run_mode = MODE_RUN
        self._checked_lesson_id: str | None = None
        self._layout_restored = False
        self._rebuilding = False
        self._search: LessonSearch | None = None
        self._default_layout_pending = {"bottom": False, "main": False, "workspace": False}

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1280, 860)
        self.setMinimumSize(900, 600)

        self._runner = CodeRunner(self._runner_limits(), parent=self, interpreter=self._interpreter())
        self._check = CheckSession(self._runner, parent=self)
        self._build_ui()
        self._build_menu()
        self._connect()
        self._restore_settings()
        self._show_home()

    # ================================================================== izgradnja
    def _build_ui(self) -> None:
        self.home_page = HomePage(self._lessons.course_title)
        self.lesson_browser = LessonBrowser(self._lessons, self._progress)
        self.lesson_browser.setMinimumWidth(220)
        self.lesson_panel = LessonPanel()
        self.editor_panel = EditorPanel()
        self.output_panel = OutputPanel()

        self._bottom_split = QSplitter(Qt.Orientation.Horizontal)
        self._bottom_split.setHandleWidth(8)
        self._bottom_split.setChildrenCollapsible(False)
        self._bottom_split.addWidget(self.editor_panel)
        self._bottom_split.addWidget(self.output_panel)
        self._bottom_split.setStretchFactor(0, 1)
        self._bottom_split.setStretchFactor(1, 1)

        self._main_split = QSplitter(Qt.Orientation.Vertical)
        self._main_split.setHandleWidth(8)
        self._main_split.setChildrenCollapsible(False)
        self._main_split.addWidget(self.lesson_panel)
        self._main_split.addWidget(self._bottom_split)
        self._main_split.setStretchFactor(0, 2)
        self._main_split.setStretchFactor(1, 3)

        self._workspace_split = QSplitter(Qt.Orientation.Horizontal)
        self._workspace_split.setHandleWidth(8)
        self._workspace_split.setChildrenCollapsible(False)
        self._workspace_split.addWidget(self.lesson_browser)
        self._workspace_split.addWidget(self._main_split)
        self._workspace_split.setStretchFactor(0, 0)
        self._workspace_split.setStretchFactor(1, 1)

        workspace = QWidget()
        workspace.setObjectName("Central")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(10, 10, 10, 6)
        layout.addWidget(self._workspace_split)

        self._stack = QStackedWidget()
        self._stack.addWidget(self.home_page)
        self._stack.addWidget(workspace)
        self.setCentralWidget(self._stack)

        bar = self.statusBar()
        bar.setSizeGripEnabled(True)
        self._status_lesson = QLabel()
        self._status_run = QLabel("Spreman")
        self._status_progress = QLabel()
        bar.addWidget(self._status_lesson, 1)
        bar.addPermanentWidget(self._status_run)
        bar.addPermanentWidget(self._status_progress)

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&Datoteka")
        save = QAction("Sačuvaj kod", self)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(self._save_code)
        file_menu.addAction(save)
        file_menu.addSeparator()
        settings_action = QAction("Podešavanja…", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        quit_action = QAction("Izlaz", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        lesson_menu = menu.addMenu("&Lekcija")
        home_action = QAction("Početna strana", self)
        home_action.setShortcut(QKeySequence("Ctrl+H"))
        home_action.triggered.connect(self._show_home)
        self._continue_action = QAction("Nastavi učenje", self)
        self._continue_action.setShortcut(QKeySequence("Ctrl+L"))
        self._continue_action.triggered.connect(self._continue_learning)
        prev_action = QAction("Prethodna lekcija", self)
        prev_action.setShortcut(QKeySequence("Alt+Left"))
        prev_action.triggered.connect(self._go_previous)
        next_action = QAction("Sledeća lekcija", self)
        next_action.setShortcut(QKeySequence("Alt+Right"))
        next_action.triggered.connect(self._go_next)
        search_action = QAction("Pretraži lekcije…", self)
        search_action.setShortcut(QKeySequence("Ctrl+K"))
        search_action.triggered.connect(self._open_search)
        favorite_action = QAction("Dodaj/ukloni iz omiljenih", self)
        favorite_action.setShortcut(QKeySequence("Ctrl+D"))
        favorite_action.triggered.connect(self._toggle_favorite)
        lesson_menu.addActions([home_action, self._continue_action, search_action, favorite_action])
        lesson_menu.addSeparator()
        lesson_menu.addActions([prev_action, next_action])

        run_menu = menu.addMenu("&Pokretanje")
        run_action = QAction("Pokreni", self)
        run_action.setShortcut(QKeySequence("F5"))
        run_action.triggered.connect(self._run_code)
        check_action = QAction("Proveri zadatak", self)
        check_action.setShortcut(QKeySequence("F6"))
        check_action.triggered.connect(self._check_task)
        stop_action = QAction("Zaustavi program", self)
        stop_action.setShortcut(QKeySequence("Shift+F5"))
        stop_action.triggered.connect(self._stop)
        run_menu.addActions([run_action, check_action, stop_action])

        view_menu = menu.addMenu("&Prikaz")
        self._browser_action = QAction("Sadržaj kursa", self)
        self._browser_action.setCheckable(True)
        self._browser_action.setShortcut(QKeySequence("F9"))
        self._browser_action.toggled.connect(self._set_browser_visible)
        view_menu.addAction(self._browser_action)
        self._line_numbers_action = QAction("Brojevi linija", self)
        self._line_numbers_action.setCheckable(True)
        self._line_numbers_action.setChecked(True)
        self._line_numbers_action.toggled.connect(self.editor_panel.set_line_numbers_visible)
        view_menu.addAction(self._line_numbers_action)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("Tema")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        chosen = str(self._settings.get("appearance/theme"))
        for key, label in THEME_CHOICES:
            action = QAction(label, self, checkable=True)
            action.setChecked(key == chosen)
            action.triggered.connect(lambda _=False, k=key: self._choose_theme(k))
            self._theme_group.addAction(action)
            theme_menu.addAction(action)
        view_menu.addSeparator()
        for mode, label in ((SIZE_COMPACT, "Lekcija: samo naslov"),
                            (SIZE_NORMAL, "Lekcija: uobičajeno"),
                            (SIZE_EXPANDED, "Lekcija: prošireno")):
            action = QAction(label, self)
            action.triggered.connect(lambda _=False, m=mode: self.lesson_panel.set_size_mode(m))
            view_menu.addAction(action)

        help_menu = menu.addMenu("Po&moć")
        safety = QAction("Kako se pokreće kod (bezbednost)", self)
        safety.triggered.connect(self._show_safety_info)
        about = QAction("O aplikaciji", self)
        about.triggered.connect(self._show_about)
        help_menu.addActions([safety, about])

        # Ctrl+Enter radi i kada fokus nije u editoru (samo u radnom prostoru).
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._run_code)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._run_code)

    def _connect(self) -> None:
        lp, ep, op = self.lesson_panel, self.editor_panel, self.output_panel
        self.home_page.lesson_requested.connect(self._request_lesson)
        self.home_page.module_requested.connect(self._request_module)
        self.home_page.search_requested.connect(self._open_search)
        lp.favorite_toggled.connect(self._on_favorite_toggled)
        lp.search_requested.connect(self._open_search)
        self.lesson_browser.lesson_activated.connect(self._request_lesson)

        lp.previous_requested.connect(self._go_previous)
        lp.next_requested.connect(self._go_next)
        lp.completed_toggled.connect(self._on_completed_toggled)
        lp.load_code_requested.connect(self._load_code_into_editor)
        lp.size_mode_changed.connect(self._apply_lesson_size)
        lp.home_requested.connect(self._show_home)
        lp.quiz_requested.connect(self._open_quiz)
        lp.browser_toggled.connect(self._browser_action.setChecked)

        ep.run_requested.connect(self._run_code)
        ep.check_requested.connect(self._check_task)
        ep.reset_requested.connect(self._reset_code)
        ep.save_requested.connect(self._save_code)
        ep.line_numbers_toggled.connect(self._line_numbers_action.setChecked)

        op.input_submitted.connect(self._runner.send_input)
        op.stop_requested.connect(self._stop)
        op.go_to_line_requested.connect(self.editor_panel.editor.go_to_line)
        op.complete_and_next_requested.connect(self._complete_and_next)

        self._runner.stdout_received.connect(op.append_stdout)
        self._runner.stderr_received.connect(op.append_stderr)
        self._runner.input_requested.connect(self._on_input_requested)
        self._runner.preset_input_used.connect(op.append_preset_input)
        self._runner.finished.connect(self._on_run_finished)

        self._check.case_started.connect(self._on_case_started)
        self._check.finished.connect(self._on_check_finished)

    # ================================================================== prikazi
    def _in_workspace(self) -> bool:
        return self._stack.currentIndex() == VIEW_WORKSPACE

    def _show_home(self) -> None:
        self.home_page.show_overview(build_overview(self._lessons, self._progress))
        self._stack.setCurrentIndex(VIEW_HOME)
        self.setWindowTitle(APP_NAME)
        self._status_lesson.setText("Početna strana")
        self._update_progress()

    def _show_workspace(self) -> None:
        self._stack.setCurrentIndex(VIEW_WORKSPACE)
        if self._lesson is not None:
            self.setWindowTitle(f"{self._lesson.number}. {self._lesson.title} — {APP_NAME}")
            self._status_lesson.setText(f"Lekcija {self._lesson.number}: {self._lesson.title}")
        self.editor_panel.editor.setFocus()

    def _continue_learning(self) -> None:
        overview = build_overview(self._lessons, self._progress)
        target = overview.recommended or overview.current
        if target is not None:
            self._request_lesson(target.lesson_id)

    def _set_browser_visible(self, visible: bool) -> None:
        self.lesson_browser.setVisible(visible)
        self.lesson_panel.set_browser_checked(visible)
        if visible:
            self.lesson_browser.refresh()

    # ================================================================== lekcije
    def _request_lesson(self, lesson_id: str) -> None:
        """Otvara lekciju na zahtev korisnika (sa pitanjem o nesačuvanom kodu)."""
        if self._lesson is not None and self._lesson.lesson_id == lesson_id:
            self._show_workspace()
            return
        if not self._confirm_leave_code("otvaranja druge lekcije"):
            return
        if self._open_lesson(lesson_id):
            self._show_workspace()

    def _request_module(self, module_id: str) -> None:
        target = module_entry_lesson(self._lessons, self._progress, module_id)
        if target is not None:
            self._request_lesson(target)

    def _open_lesson(self, lesson_id: str) -> bool:
        try:
            lesson = self._lessons.load(lesson_id)
        except LessonLoadError as exc:
            log.error("Lekcija nije učitana: %s", exc)
            QMessageBox.warning(self, "Lekcija nije dostupna", str(exc))
            return False
        self._stop()
        self._lesson = lesson
        self._progress.set_current_lesson(lesson_id, lesson.module.module_id)

        saved = self._progress.saved_code(lesson_id)
        code = saved if saved is not None else lesson.exercise.starter_code
        self.editor_panel.editor.set_text(code, mark_clean=True)
        self.output_panel.clear()
        self._status_run.setText("Spreman")

        self.lesson_panel.show_lesson(
            lesson,
            position=lesson.number,
            total_in_course=len(self._lessons.all_lessons),
            has_previous=self._lessons.previous_id(lesson_id) is not None,
            has_next=self._lessons.next_id(lesson_id) is not None,
            completed=self._progress.is_completed(lesson_id),
        )
        self.lesson_panel.set_quiz_info(self._progress.quiz_record(lesson_id))
        self.lesson_panel.set_favorite(self._progress.is_favorite(lesson_id))
        self.lesson_panel.set_exercise_status(self._progress.lesson_status(lesson_id))
        self._update_progress()
        self._status_lesson.setText(f"Lekcija {lesson.number}: {lesson.title}")
        self.setWindowTitle(f"{lesson.number}. {lesson.title} — {APP_NAME}")
        if saved is not None:
            self.statusBar().showMessage("Učitan je tvoj sačuvani kod za ovu lekciju.", 4000)
        return True

    def _go_previous(self) -> None:
        if self._lesson and self._in_workspace():
            target = self._lessons.previous_id(self._lesson.lesson_id)
            if target and self._confirm_leave_code("prelaska na prethodnu lekciju"):
                self._open_lesson(target)

    def _go_next(self) -> None:
        if self._lesson and self._in_workspace():
            target = self._lessons.next_id(self._lesson.lesson_id)
            if target and self._confirm_leave_code("prelaska na sledeću lekciju"):
                self._open_lesson(target)

    # ================================================================== pretraga i omiljene
    def _open_search(self) -> None:
        if self._search is None:
            self._search = LessonSearch(self._lessons)
        modules = {m.module_id: f"Modul {m.number} · {m.title}" for m in self._lessons.modules}
        dialog = SearchDialog(self._search, modules, self)
        dialog.lesson_selected.connect(self._request_lesson)
        dialog.exec()

    def _on_favorite_toggled(self, favorite: bool) -> None:
        if self._lesson is None:
            return
        self._progress.set_favorite(self._lesson.lesson_id, favorite)
        self.lesson_browser.refresh()
        self.statusBar().showMessage(
            "Lekcija je dodata u omiljene." if favorite else "Lekcija je uklonjena iz omiljenih.", 3000)

    def _toggle_favorite(self) -> None:
        if self._lesson is not None and self._in_workspace():
            new_state = not self.lesson_panel.is_favorite()
            self.lesson_panel.set_favorite(new_state)
            self._on_favorite_toggled(new_state)

    def _open_quiz(self) -> None:
        if self._lesson is None or not self._lesson.quiz:
            return
        lesson = self._lesson

        def on_finished(score: int, total: int, passed: bool) -> None:
            self._progress.record_quiz(lesson.lesson_id, score, total, passed)
            self.lesson_panel.set_quiz_info(self._progress.quiz_record(lesson.lesson_id))
            self._update_progress()

        dialog = QuizDialog(f"Lekcija {lesson.number}: {lesson.title}", lesson.quiz, on_finished, self,
                            interpreter=self._runner.interpreter)
        dialog.exec()
        record = self._progress.quiz_record(lesson.lesson_id)
        if record is not None and record.passed and not self._progress.is_completed(lesson.lesson_id) \
                and self._progress.is_solved(lesson.lesson_id):
            self.statusBar().showMessage(
                "Zadatak je rešen i kviz položen — lekciju možeš označiti kao završenu.", 8000)

    def _on_completed_toggled(self, completed: bool) -> None:
        if self._lesson:
            self._progress.set_completed(self._lesson.lesson_id, completed)
            self._update_progress()
            if completed:
                self.statusBar().showMessage("Lekcija je označena kao završena.", 3000)

    def _complete_and_next(self) -> None:
        """Posle uspešne provere: označi lekciju kao završenu i pređi na sledeću."""
        if self._lesson is None:
            return
        self._progress.set_completed(self._lesson.lesson_id, True)
        self.lesson_panel.set_completed(True)
        self._update_progress()
        target = self._lessons.next_id(self._lesson.lesson_id)
        if target is None:
            QMessageBox.information(
                self, "Kraj dostupnih lekcija",
                "Ovo je poslednja trenutno dostupna lekcija. Sledeće lekcije su u pripremi.\n\n"
                "Na početnoj strani možeš da vidiš svoj napredak i ponoviš ranije lekcije.")
            return
        if self._confirm_leave_code("prelaska na sledeću lekciju"):
            self._open_lesson(target)

    def _update_progress(self) -> None:
        available = [info.lesson_id for info in self._lessons.available_lessons]
        done = self._progress.completed_count(available)
        self.lesson_panel.set_progress(done, len(available))
        total = len(self._lessons.all_lessons)
        completed = self._progress.completed_count(available)
        percent = round(100 * completed / total) if total else 0
        self._status_progress.setText(f"Kurs: {percent}% ({completed}/{total} lekcija)")
        self.lesson_browser.refresh(self._lesson.lesson_id if self._lesson else None)

    # ================================================================== kod u editoru
    def _confirm_leave_code(self, action: str) -> bool:
        """Pita šta da radi sa nesačuvanim kodom. Vraća False ako je korisnik otkazao."""
        editor = self.editor_panel.editor
        if self._lesson is None or not editor.is_modified():
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Nesačuvane izmene")
        box.setText(f"Kod u lekciji „{self._lesson.title}“ ima nesačuvane izmene.")
        box.setInformativeText(f"Šta želiš da uradiš sa njim pre {action}?")
        save = box.addButton("Sačuvaj", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Odbaci izmene", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Otkaži", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            self._save_code()
            return True
        return clicked is discard

    def _load_code_into_editor(self, code: str, source: str) -> None:
        if not self._confirm_leave_code(f"učitavanja ({source})"):
            return
        self.editor_panel.editor.set_text(code, mark_clean=False)
        self.editor_panel.editor.setFocus()
        self.statusBar().showMessage(f"U editor je učitan {source}.", 3000)

    def _reset_code(self) -> None:
        if self._lesson is None:
            return
        editor = self.editor_panel.editor
        starter = self._lesson.exercise.starter_code
        if editor.text() == starter:
            self.statusBar().showMessage("Editor već sadrži početni kod.", 3000)
            return
        answer = QMessageBox.question(
            self, "Vrati početni kod",
            "Kod u editoru biće zamenjen početnim kodom zadatka.\n"
            "Tvoj sačuvani kod ostaje sačuvan dok ponovo ne klikneš „Sačuvaj kod“.\n\nNastaviti?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            editor.set_text(starter, mark_clean=False)
            self.output_panel.clear()

    def _save_code(self) -> None:
        if self._lesson is None:
            return
        editor = self.editor_panel.editor
        self._progress.save_code(self._lesson.lesson_id, editor.text())
        editor.mark_clean()
        self.statusBar().showMessage("Kod je sačuvan.", 3000)

    # ================================================================== pokretanje
    def _run_code(self) -> None:
        self._start(MODE_RUN)

    def _check_task(self) -> None:
        self._start(MODE_CHECK)

    def _stop(self) -> None:
        if self._check.is_active():
            self._check.cancel()
        else:
            self._runner.stop()

    def _start(self, mode: str) -> None:
        if (self._runner.is_running() or self._check.is_active()
                or self._lesson is None or not self._in_workspace()):
            return
        code = self.editor_panel.editor.text()
        self._run_mode = mode
        self.editor_panel.editor.clear_error_marks()
        self.editor_panel.set_running(True)
        self._status_run.setText("Izvršava se…")
        if mode == MODE_CHECK:
            self._checked_lesson_id = self._lesson.lesson_id
            self.output_panel.start_check()
            self._check.start(code, self._lesson.exercise.criteria)
        else:
            if uses_pyqt(code):
                self.output_panel.start_run("Pokretanje programa sa prozorom")
                self.output_panel.show_message(
                    "info", "Program sa prozorom",
                    "Prozor se otvara posebno. Program radi dok ga ne zatvoriš (ili klikneš "
                    "„Zaustavi“), pa za njega ne važi vremensko ograničenje. Ono što program "
                    "ispiše pomoću print() pojavljuje se ovde.")
                self._runner.run(code, no_timeout=True)
            else:
                self.output_panel.start_run("Pokretanje programa")
                self._runner.run(code)

    def _on_input_requested(self) -> None:
        self.output_panel.show_waiting_for_input()
        self._status_run.setText("Program čeka unos")

    def _on_run_finished(self, result: RunResult) -> None:
        if self._run_mode == MODE_CHECK:
            return  # Rezultate provere obrađuje CheckSession.
        self.editor_panel.set_running(False)
        self.output_panel.finish(result)
        self._status_run.setText(result.status.label)
        if result.status is RunStatus.ERROR:
            self._show_error_for(result)

    def _show_error_for(self, result: RunResult, user_code: str | None = None) -> bool:
        """Prikazuje objašnjenje greške i označava liniju u editoru.

        Args:
            result: Rezultat sa greškom.
            user_code: Korisnikov kod, ako je pri proveri dodat test kod — tada
                greška posle poslednje korisnikove linije potiče iz testa.
        """
        info = explain_error(result.stderr)
        if info is None:
            return False
        in_test = (user_code is not None and info.line is not None
                   and info.line > len(user_code.splitlines()))
        self.output_panel.show_error(info, in_test_code=in_test)
        if info.line and not in_test:
            self.editor_panel.editor.mark_error_line(info.line)
        return True

    def _on_case_started(self, index: int, total: int, case: TestCase) -> None:
        self.output_panel.begin_check_case(index, total, case.input_label)

    def _on_check_finished(self, report: CheckReport, results: list[RunResult]) -> None:
        self.editor_panel.set_running(False)
        self.output_panel.finish_check(results, report.passed)
        # _run_mode ostaje MODE_CHECK do sledećeg pokretanja: runner.finished za
        # poslednji slučaj stiže i do _on_run_finished, koji ga tada ignoriše.
        if self._lesson is None or self._lesson.lesson_id != self._checked_lesson_id:
            return  # Korisnik je u međuvremenu prešao na drugu lekciju.
        lesson_id = self._lesson.lesson_id
        attempts = self._progress.record_attempt(lesson_id, report.passed)
        self.lesson_panel.set_exercise_status(self._progress.lesson_status(lesson_id))

        failed_run = next((r for r in results if r.status is RunStatus.ERROR), None)
        if failed_run is not None and self._show_error_for(failed_run, self._check.code):
            self._status_run.setText("Provera: greška u programu")
            self.statusBar().showMessage(
                "Provera: program je prijavio grešku — prvo je ispravi, pa ponovo proveri.", 6000)
            self._update_progress()
            return

        has_next = self._lessons.next_id(lesson_id) is not None
        next_action = "Završi lekciju i pređi na sledeću" if has_next else "Označi lekciju kao završenu"
        self.output_panel.show_check_report(report, attempts, next_action)
        if report.passed:
            self._status_run.setText("Zadatak rešen")
            # Tačno rešenje se automatski čuva, da se ne bi izgubilo.
            self._progress.save_code(lesson_id, self.editor_panel.editor.text())
            self.editor_panel.editor.mark_clean()
            self.statusBar().showMessage("Zadatak je rešen, a tvoje rešenje je sačuvano.", 6000)
        else:
            self._status_run.setText("Provera nije prošla")
        self._update_progress()

    # ================================================================== veličina lekcije
    def _apply_lesson_size(self, mode: str) -> None:
        total = max(400, self._main_split.height())
        if mode == SIZE_COMPACT:
            QTimer.singleShot(0, self._apply_compact)
            return
        self.lesson_panel.setMaximumHeight(_QWIDGETSIZE_MAX)
        ratio = 0.68 if mode == SIZE_EXPANDED else 0.42
        top = int(total * ratio)
        self._main_split.setSizes([top, total - top])

    def _apply_compact(self) -> None:
        height = self.lesson_panel.sizeHint().height()
        self.lesson_panel.setMaximumHeight(height)
        total = max(400, self._main_split.height())
        self._main_split.setSizes([height, total - height])

    # ================================================================== podešavanja
    def _runner_limits(self) -> RunnerLimits:
        return RunnerLimits(
            timeout_ms=int(self._settings.get("runner/timeout_s")) * 1000,
            max_output_chars=int(self._settings.get("runner/max_output_kchars")) * 1000,
        )

    def _interpreter(self) -> Interpreter:
        return locate_python(str(self._settings.get("runner/python_path")))

    def _restore_settings(self) -> None:
        s = self._settings
        for key, restore in (("window/geometry", self.restoreGeometry),
                             ("window/state", self.restoreState)):
            data = s.get(key)
            if data:
                restore(QByteArray(data))
        bottom_split = s.get("layout/bottom_split")
        if bottom_split:
            self._bottom_split.restoreState(QByteArray(bottom_split))
        else:
            self._default_layout_pending["bottom"] = True
        workspace_split = s.get("layout/workspace_split")
        if workspace_split:
            self._workspace_split.restoreState(QByteArray(workspace_split))
        else:
            self._default_layout_pending["workspace"] = True
        browser_visible = bool(s.get("layout/browser_visible"))
        self._browser_action.setChecked(browser_visible)
        self._set_browser_visible(browser_visible)

        self._apply_user_settings()
        mode = str(s.get("layout/lesson_size"))
        self.lesson_panel.set_size_mode(mode, emit=False)
        main_split = s.get("layout/main_split")
        if main_split and mode != SIZE_COMPACT:
            self._main_split.restoreState(QByteArray(main_split))
        else:
            self._default_layout_pending["main"] = True

    def _apply_user_settings(self) -> None:
        """Primenjuje podešavanja iz dijaloga (font, brojevi linija, ograničenja, potvrda rešenja)."""
        s = self._settings
        set_default_font_size(int(s.get("editor/font_size")))
        font = editor_font()
        self.editor_panel.editor.set_editor_font(font)
        self.lesson_panel.set_code_font(font)
        self.output_panel.set_output_font(font)
        line_numbers = bool(s.get("editor/line_numbers"))
        self.editor_panel.set_line_numbers_visible(line_numbers)
        self._line_numbers_action.setChecked(line_numbers)
        self.lesson_panel.set_confirm_solution(bool(s.get("lesson/confirm_solution")))
        self._runner.set_limits(self._runner_limits())
        self._runner.set_interpreter(self._interpreter())

    def _open_settings(self) -> None:
        # Brojevi linija se menjaju i iz menija, pa se prvo sačuva trenutno stanje.
        self._settings.set("editor/line_numbers", self.editor_panel.line_numbers_visible())
        values = {key: self._settings.get(key) for key in USER_SETTINGS}
        dialog = SettingsDialog(values, self._progress, self)
        dialog.progress_reset.connect(self._on_progress_reset)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            new_values = dialog.values()
            theme = new_values.pop("appearance/theme")
            self._settings.set_many(new_values)
            self._apply_user_settings()
            self.statusBar().showMessage("Podešavanja su sačuvana.", 3000)
            self._choose_theme(theme)

    # ================================================================== tema
    def _choose_theme(self, key: str) -> None:
        """Pamti izbor teme i, ako se tema zaista menja, traži ponovnu izgradnju prozora."""
        previous = str(self._settings.get("appearance/theme"))
        self._settings.set("appearance/theme", key)
        if resolve_theme_key(key) != current_theme().key:
            self.theme_change_requested.emit(key)
        elif key != previous:
            self.statusBar().showMessage("Tema je sačuvana.", 3000)

    def snapshot(self) -> dict:
        """Stanje koje se prenosi u novi prozor (otvorena lekcija, kod u editoru, prikaz)."""
        editor = self.editor_panel.editor
        return {
            "view": self._stack.currentIndex(),
            "lesson_id": self._lesson.lesson_id if self._lesson else None,
            "code": editor.text(),
            "baseline": editor.baseline,
            "lesson_tab": self.lesson_panel.current_tab(),
        }

    def restore_snapshot(self, state: dict) -> None:
        lesson_id = state.get("lesson_id")
        if lesson_id and self._open_lesson(lesson_id):
            self.editor_panel.editor.restore_state(state.get("code", ""), state.get("baseline", ""))
            self.lesson_panel.set_current_tab(int(state.get("lesson_tab", 0)))
        if state.get("view") == VIEW_WORKSPACE and self._lesson is not None:
            self._show_workspace()
        else:
            self._show_home()

    def close_for_rebuild(self) -> None:
        """Zatvara prozor bez pitanja o kodu (kod se prenosi u novi prozor)."""
        self._rebuilding = True
        self.close()

    def _on_progress_reset(self) -> None:
        """Posle brisanja napretka: editor ostaje, ali se lekcija ponovo učitava bez starog stanja."""
        self.editor_panel.editor.mark_clean()
        lesson_id = self._lesson.lesson_id if self._lesson else None
        self._lesson = None
        if lesson_id is not None and self._in_workspace():
            self._open_lesson(lesson_id)
        else:
            self._show_home()
        self._update_progress()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Podrazumevani raspored se računa tek kada prozor dobije stvarnu veličinu."""
        super().showEvent(event)
        if not self._layout_restored:
            self._layout_restored = True
            QTimer.singleShot(0, self._apply_default_layout)

    def _apply_default_layout(self) -> None:
        if self._default_layout_pending["workspace"]:
            width = max(900, self._workspace_split.width())
            self._workspace_split.setSizes([280, width - 280])
        if self._default_layout_pending["bottom"]:
            half = max(200, self._bottom_split.width()) // 2
            self._bottom_split.setSizes([half, half])
        if self._default_layout_pending["main"]:
            self._apply_lesson_size(self.lesson_panel.size_mode)

    def _save_settings(self) -> None:
        s = self._settings
        s.set("window/geometry", self.saveGeometry())
        s.set("window/state", self.saveState())
        s.set("layout/main_split", self._main_split.saveState())
        s.set("layout/bottom_split", self._bottom_split.saveState())
        s.set("layout/workspace_split", self._workspace_split.saveState())
        s.set("layout/browser_visible", self._browser_action.isChecked())
        s.set("layout/lesson_size", self.lesson_panel.size_mode)
        s.set("editor/line_numbers", self.editor_panel.line_numbers_visible())

    # ================================================================== pomoć
    def _show_safety_info(self) -> None:
        QMessageBox.information(
            self, "Kako se pokreće kod",
            "Tvoj kod se pokreće u zasebnom Python procesu, u privremenom direktorijumu, "
            "sa vremenskim ograničenjem i ograničenjem količine izlaza. Ako se program zaglavi, "
            "zaustavlja se automatski ili dugmetom „Zaustavi“.\n\n"
            "Važno: zaseban proces NIJE zaštićeno okruženje (sandbox). Program koji pokreneš ima "
            "ista prava kao i ti — može da čita i menja tvoje fajlove. Zato ovde pokreći samo kod "
            "koji razumeš, a ne kod nepoznatog porekla sa interneta.",
        )

    def _show_about(self) -> None:
        QMessageBox.about(
            self, f"O aplikaciji {APP_NAME}",
            f"<b>{APP_NAME}</b> {APP_VERSION}<br><br>"
            "Interaktivna platforma za učenje Pythona i PyQt6 za potpune početnike.<br>"
            "Čitaj lekciju, piši kod dole levo, pokreni ga i odmah vidi rezultat dole desno.<br><br>"
            f"Napredak se čuva u:<br><code>{self._progress.storage_file}</code>",
        )

    # ================================================================== zatvaranje
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if not self._rebuilding and not self._confirm_leave_code("zatvaranja aplikacije"):
            event.ignore()
            return
        self._runner.shutdown()
        self._save_settings()
        event.accept()
