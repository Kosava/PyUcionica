# pyqt6_learning_studio/ui/lesson_panel.py
"""Gornji panel: prikaz aktivne lekcije (objašnjenje, primer, zadatak) i navigacija.

Panel ne zna ništa o editoru ni o pokretanju koda — samo emituje signale
(npr. „prebaci ovaj kod u editor“), a glavni prozor odlučuje šta dalje.
"""

from __future__ import annotations

import html
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.progress_manager import LessonStatus, QuizRecord
from core.quiz_manager import required_to_pass
from models.lesson import Lesson
from ui import lesson_formatter as fmt
from ui.code_editor import CodeEditor
from ui.icons import icon, pixmap
from ui.theme import current_theme

def _format_date(stamp: str) -> str:
    """ISO vreme (2026-10-30T07:46:12) → 30.10.2026."""
    try:
        return datetime.fromisoformat(stamp).strftime("%d.%m.%Y.")
    except ValueError:
        return stamp


SIZE_COMPACT = "compact"
SIZE_NORMAL = "normal"
SIZE_EXPANDED = "expanded"
_SIZE_ORDER = (SIZE_COMPACT, SIZE_NORMAL, SIZE_EXPANDED)


def _browser() -> QTextBrowser:
    browser = QTextBrowser()
    browser.setObjectName("LessonText")
    browser.setOpenExternalLinks(True)
    browser.document().setDocumentMargin(14)
    return browser


class LessonPanel(QFrame):
    """Prikaz lekcije.

    Signals:
        previous_requested / next_requested: Navigacija između lekcija.
        completed_toggled(bool): Korisnik je (od)označio lekciju kao završenu.
        load_code_requested(str, str): Učitaj kod u editor (kod, opis izvora).
        size_mode_changed(str): Promenjena veličina panela
            (``compact`` / ``normal`` / ``expanded``).
        home_requested: Kliknuto je „Početna“.
        quiz_requested: Korisnik želi da radi kviz lekcije.
        favorite_toggled(bool): Lekcija je dodata u omiljene / uklonjena iz njih.
        search_requested: Otvori pretragu lekcija.
        browser_toggled(bool): Prikaži/sakrij bočni panel „Sadržaj kursa“.
    """

    previous_requested = pyqtSignal()
    next_requested = pyqtSignal()
    completed_toggled = pyqtSignal(bool)
    load_code_requested = pyqtSignal(str, str)
    size_mode_changed = pyqtSignal(str)
    home_requested = pyqtSignal()
    quiz_requested = pyqtSignal()
    favorite_toggled = pyqtSignal(bool)
    search_requested = pyqtSignal()
    browser_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._lesson: Lesson | None = None
        self._hints_shown = 0
        self._solution_shown = False
        self._size_mode = SIZE_NORMAL
        self._confirm_solution = True
        self._status: LessonStatus | None = None
        c = current_theme().colors

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 0)
        root.setSpacing(6)

        # --- red 1: modul, napredak, veličina panela
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self._home_btn = QToolButton()
        self._home_btn.setIcon(icon("home", c["icon"]))
        self._home_btn.setToolTip("Početna strana (Ctrl+H)")
        self._home_btn.clicked.connect(self.home_requested)
        self._browser_btn = QToolButton()
        self._browser_btn.setIcon(icon("sidebar", c["icon"]))
        self._browser_btn.setCheckable(True)
        self._browser_btn.setToolTip("Prikaži ili sakrij sadržaj kursa (F9)")
        self._browser_btn.toggled.connect(self.browser_toggled)
        row1.addWidget(self._home_btn)
        row1.addWidget(self._browser_btn)
        self._search_btn = QToolButton()
        self._search_btn.setIcon(icon("search", c["icon"]))
        self._search_btn.setToolTip("Pretraži sve lekcije (Ctrl+K)")
        self._search_btn.clicked.connect(self.search_requested)
        row1.addWidget(self._search_btn)
        row1.addSpacing(4)
        self._module_label = QLabel()
        self._module_label.setObjectName("ModuleLabel")
        self._position_label = QLabel()
        self._position_label.setObjectName("Faint")
        self._progress = QProgressBar()
        self._progress.setFixedWidth(150)
        self._progress.setTextVisible(False)
        self._progress_label = QLabel()
        self._progress_label.setObjectName("Faint")
        self._shrink_btn = QToolButton()
        self._shrink_btn.setIcon(icon("chevrons-up", c["icon"]))
        self._shrink_btn.setToolTip("Smanji prostor lekcije")
        self._shrink_btn.clicked.connect(lambda: self._step_size(-1))
        self._grow_btn = QToolButton()
        self._grow_btn.setIcon(icon("chevrons-down", c["icon"]))
        self._grow_btn.setToolTip("Proširi prostor lekcije")
        self._grow_btn.clicked.connect(lambda: self._step_size(+1))
        row1.addWidget(self._module_label)
        row1.addStretch(1)
        row1.addWidget(self._position_label)
        row1.addWidget(self._progress)
        row1.addWidget(self._progress_label)
        row1.addSpacing(6)
        row1.addWidget(self._shrink_btn)
        row1.addWidget(self._grow_btn)
        root.addLayout(row1)

        # --- red 2: naslov i navigacija
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self._title = QLabel()
        self._title.setObjectName("LessonTitle")
        self._title.setWordWrap(True)
        self._prev_btn = QPushButton(icon("chevron-left", c["icon"]), "Prethodna lekcija")
        self._prev_btn.clicked.connect(self.previous_requested)
        self._next_btn = QPushButton("Sledeća lekcija")
        self._next_btn.setIcon(icon("chevron-right", c["icon"]))
        self._next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._next_btn.clicked.connect(self.next_requested)
        self._complete_btn = QPushButton()
        self._complete_btn.setObjectName("CompleteButton")
        self._complete_btn.setCheckable(True)
        self._complete_btn.toggled.connect(self._on_complete_toggled)
        self._fav_btn = QToolButton()
        self._fav_btn.setCheckable(True)
        self._fav_btn.toggled.connect(self._on_favorite_toggled)
        self._update_favorite_button(False)
        row2.addWidget(self._title, 1)
        row2.addWidget(self._fav_btn)
        row2.addWidget(self._prev_btn)
        row2.addWidget(self._next_btn)
        row2.addWidget(self._complete_btn)
        root.addLayout(row2)

        # --- red 3: cilj lekcije
        self._goal_row = QWidget()
        goal_layout = QHBoxLayout(self._goal_row)
        goal_layout.setContentsMargins(0, 0, 0, 4)
        goal_layout.setSpacing(6)
        goal_icon = QLabel()
        goal_icon.setPixmap(pixmap("target", c["accent"], 16))
        self._goal = QLabel()
        self._goal.setObjectName("GoalLabel")
        self._goal.setWordWrap(True)
        goal_layout.addWidget(goal_icon, 0, Qt.AlignmentFlag.AlignTop)
        goal_layout.addWidget(self._goal, 1)
        root.addWidget(self._goal_row)

        # --- kartice: objašnjenje, primer, zadatak
        self._tabs = QTabWidget()
        self._tabs.setObjectName("LessonTabs")
        self._tabs.setDocumentMode(True)

        self._explain_view = _browser()
        self._tabs.addTab(self._explain_view, icon("book-open", c["icon"]), "Objašnjenje")

        example_tab = QWidget()
        ex_layout = QHBoxLayout(example_tab)
        ex_layout.setContentsMargins(0, 8, 0, 0)
        ex_split = QSplitter(Qt.Orientation.Horizontal)
        ex_split.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        self._example_code = CodeEditor(read_only=True)
        self._example_code.setMinimumHeight(80)
        example_frame = QFrame()
        example_frame.setObjectName("Panel")
        ef = QVBoxLayout(example_frame)
        ef.setContentsMargins(1, 1, 1, 1)
        ef.addWidget(self._example_code)
        self._copy_example_btn = QPushButton(icon("file-input", c["icon"]), "Prebaci primer u editor")
        self._copy_example_btn.setToolTip("Učitaj primer u editor ispod, da ga pokreneš i menjaš")
        self._copy_example_btn.clicked.connect(self._on_copy_example)
        copy_row = QHBoxLayout()
        copy_row.addWidget(self._copy_example_btn)
        copy_row.addStretch(1)
        left_layout.addWidget(example_frame, 1)
        left_layout.addLayout(copy_row)
        self._steps_view = _browser()
        ex_split.addWidget(left)
        ex_split.addWidget(self._steps_view)
        ex_split.setSizes([480, 520])
        ex_layout.addWidget(ex_split)
        self._tabs.addTab(example_tab, icon("code", c["icon"]), "Primer")

        task_tab = QWidget()
        task_layout = QVBoxLayout(task_tab)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.setSpacing(0)
        self._task_view = _browser()
        task_layout.addWidget(self._task_view, 1)
        task_buttons = QHBoxLayout()
        task_buttons.setContentsMargins(14, 6, 0, 8)
        task_buttons.setSpacing(8)
        self._hint_btn = QPushButton(icon("lightbulb", c["warning"]), "Nagoveštaj")
        self._hint_btn.clicked.connect(self._show_next_hint)
        self._solution_btn = QPushButton(icon("eye", c["icon"]), "Prikaži rešenje")
        self._solution_btn.clicked.connect(self._reveal_solution)
        self._solution_to_editor_btn = QPushButton(icon("file-input", c["icon"]), "Prebaci rešenje u editor")
        self._solution_to_editor_btn.clicked.connect(self._on_copy_solution)
        self._starter_btn = QPushButton(icon("rotate-ccw", c["icon"]), "Učitaj početni kod zadatka")
        self._starter_btn.clicked.connect(self._on_load_starter)
        task_buttons.addWidget(self._hint_btn)
        task_buttons.addWidget(self._solution_btn)
        task_buttons.addWidget(self._solution_to_editor_btn)
        task_buttons.addStretch(1)
        task_buttons.addWidget(self._starter_btn)
        task_layout.addLayout(task_buttons)
        self._tabs.addTab(task_tab, icon("clipboard-check", c["icon"]), "Zadatak")

        quiz_tab = QWidget()
        quiz_layout = QVBoxLayout(quiz_tab)
        quiz_layout.setContentsMargins(0, 0, 0, 0)
        quiz_layout.setSpacing(0)
        self._quiz_view = _browser()
        quiz_layout.addWidget(self._quiz_view, 1)
        quiz_buttons = QHBoxLayout()
        quiz_buttons.setContentsMargins(14, 6, 0, 8)
        self._quiz_btn = QPushButton(icon("award", c["accent_text"]), "Započni kviz")
        self._quiz_btn.setObjectName("PrimaryButton")
        self._quiz_btn.clicked.connect(self.quiz_requested)
        quiz_buttons.addWidget(self._quiz_btn)
        quiz_buttons.addStretch(1)
        quiz_layout.addLayout(quiz_buttons)
        self._tabs.addTab(quiz_tab, icon("award", c["icon"]), "Kviz")

        root.addWidget(self._tabs, 1)
        self._update_size_buttons()

    # ------------------------------------------------------------------ prikaz lekcije
    def show_lesson(self, lesson: Lesson, position: int, total_in_course: int,
                    has_previous: bool, has_next: bool, completed: bool) -> None:
        """Prikazuje lekciju.

        Args:
            lesson: Lekcija za prikaz.
            position: Redni broj lekcije u kursu.
            total_in_course: Ukupan broj lekcija u planu kursa.
            has_previous / has_next: Da li postoji prethodna/sledeća dostupna lekcija.
            completed: Da li je lekcija označena kao završena.
        """
        self._lesson = lesson
        self._status = None
        self._hints_shown = 0
        self._solution_shown = False
        theme = current_theme()

        self._module_label.setText(f"MODUL {lesson.module.number} · {lesson.module.title.upper()}")
        self._position_label.setText(f"Lekcija {position} od {total_in_course}")
        self._title.setText(f"{lesson.number}. {lesson.title}")
        self._goal.setText(lesson.goal)
        self._prev_btn.setEnabled(has_previous)
        self._next_btn.setEnabled(has_next)
        self._next_btn.setToolTip("" if has_next else "Sledeće lekcije su u pripremi.")
        self.set_completed(completed)

        # Objašnjenje + pojmovi
        body = "".join(fmt.paragraph(p, theme) for p in lesson.explanation)
        if lesson.terms:
            c = theme.colors
            rows = "".join(
                f"<tr><td style='padding:5px 12px 5px 0; font-weight:600; white-space:nowrap;"
                f" vertical-align:top;'>{html.escape(t.term)}</td>"
                f"<td style='padding:5px 0; color:{c['text_muted']};'>{fmt.inline(t.definition, theme)}</td></tr>"
                for t in lesson.terms
            )
            body += fmt.heading("Novi pojmovi", theme) + f"<table cellspacing='0'>{rows}</table>"
        self._explain_view.setHtml(fmt.page(body, theme))

        # Primer
        self._example_code.set_text(lesson.example_code)
        steps = fmt.heading("Kod deo po deo", theme)
        for step in lesson.example_steps:
            steps += fmt.code_block(step.code, theme)
            steps += f"<p style='margin:0 0 12px 0;'>{fmt.inline(step.explanation, theme)}</p>"
        self._steps_view.setHtml(fmt.page(steps, theme))

        self._render_task()
        self._tabs.setCurrentIndex(0)

    def _render_task(self) -> None:
        if self._lesson is None:
            return
        theme = current_theme()
        c = theme.colors
        ex = self._lesson.exercise
        body = (
            f"<p style='margin:0 0 8px 0;'><span style='background:{c['accent_soft']};"
            f" color:{c['accent']}; font-weight:600;'>&nbsp;{html.escape(ex.type.label)}&nbsp;</span></p>"
        )
        body += "".join(fmt.paragraph(p, theme) for p in ex.description.split("\n\n"))
        if ex.expected_output_preview:
            body += fmt.heading("Očekivani rezultat", theme) + fmt.code_block(ex.expected_output_preview, theme)
        criteria = ex.criteria.describe()
        if criteria:
            items = "".join(f"<li style='margin-bottom:3px;'>{html.escape(x)}</li>" for x in criteria)
            body += fmt.heading("Kako se proverava", theme) + f"<ul style='margin-top:0;'>{items}</ul>"
            body += (f"<p style='color:{c['text_muted']};'>Kada završiš, klikni „Proveri zadatak“ "
                     f"ispod editora.</p>")
        if self._hints_shown:
            body += fmt.heading("Nagoveštaji", theme)
            for index, hint in enumerate(ex.hints[: self._hints_shown], start=1):
                body += (
                    f"<table width='100%' cellpadding='8' cellspacing='0' style='margin:3px 0;'>"
                    f"<tr><td style='background:{c['warning_soft']}; border-left:3px solid {c['warning']};'>"
                    f"<b>{index}.</b> {fmt.inline(hint, theme)}</td></tr></table>"
                )
        if self._solution_shown:
            body += fmt.heading("Rešenje", theme) + fmt.code_block(ex.solution, theme)
        status = self._status
        if status is not None and status.attempts:
            if status.solved_at:
                state = (f"<span style='color:{c['success']}; font-weight:600;'>rešen</span> "
                         f"({_format_date(status.solved_at)})")
            else:
                state = f"<span style='color:{c['warning']}; font-weight:600;'>još nije rešen</span>"
            body += fmt.heading("Tvoji pokušaji", theme) + (
                f"<p>Provera pokrenuta {status.attempts} put(a) · zadatak je {state}.</p>")
        self._task_view.setHtml(fmt.page(body, theme))

        total_hints = len(ex.hints)
        if total_hints == 0:
            self._hint_btn.setText("Nema nagoveštaja")
            self._hint_btn.setEnabled(False)
        elif self._hints_shown >= total_hints:
            self._hint_btn.setText(f"Nagoveštaji prikazani ({total_hints}/{total_hints})")
            self._hint_btn.setEnabled(False)
        else:
            self._hint_btn.setText(f"Nagoveštaj ({self._hints_shown + 1}/{total_hints})")
            self._hint_btn.setEnabled(True)
        self._solution_btn.setEnabled(bool(ex.solution) and not self._solution_shown)
        self._solution_to_editor_btn.setVisible(self._solution_shown)

    # ------------------------------------------------------------------ akcije
    def _show_next_hint(self) -> None:
        if self._lesson and self._hints_shown < len(self._lesson.exercise.hints):
            self._hints_shown += 1
            self._render_task()
            self._task_view.verticalScrollBar().setValue(self._task_view.verticalScrollBar().maximum())

    def _reveal_solution(self) -> None:
        if self._lesson is None:
            return
        if not self._confirm_solution:
            self._solution_shown = True
            self._render_task()
            self._task_view.verticalScrollBar().setValue(self._task_view.verticalScrollBar().maximum())
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Prikaz rešenja")
        box.setText("Da li želiš da vidiš rešenje?")
        box.setInformativeText(
            "Najviše se nauči kada zadatak rešiš sam. Probaj prvo nagoveštaje — "
            "rešenje uvek možeš da pogledaš kasnije."
        )
        show = box.addButton("Prikaži rešenje", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Probaću još", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is show:
            self._solution_shown = True
            self._render_task()
            self._task_view.verticalScrollBar().setValue(self._task_view.verticalScrollBar().maximum())

    def _on_copy_example(self) -> None:
        if self._lesson:
            self.load_code_requested.emit(self._lesson.example_code, "primer")

    def _on_copy_solution(self) -> None:
        if self._lesson:
            self.load_code_requested.emit(self._lesson.exercise.solution, "rešenje")

    def _on_load_starter(self) -> None:
        if self._lesson:
            self.load_code_requested.emit(self._lesson.exercise.starter_code, "početni kod zadatka")

    def _on_complete_toggled(self, checked: bool) -> None:
        self._update_complete_button(checked)
        self.completed_toggled.emit(checked)

    def _update_complete_button(self, checked: bool) -> None:
        c = current_theme().colors
        if checked:
            self._complete_btn.setText("Završena")
            self._complete_btn.setIcon(icon("check-circle", c["success"]))
            self._complete_btn.setToolTip("Klikni da poništiš oznaku")
        else:
            self._complete_btn.setText("Označi kao završenu")
            self._complete_btn.setIcon(icon("circle", c["icon"]))
            self._complete_btn.setToolTip("Označi da si završio ovu lekciju")

    def _on_favorite_toggled(self, checked: bool) -> None:
        self._update_favorite_button(checked)
        self.favorite_toggled.emit(checked)

    def _update_favorite_button(self, favorite: bool) -> None:
        c = current_theme().colors
        self._fav_btn.setIcon(icon("star-filled", c["warning"]) if favorite else icon("star", c["icon"]))
        self._fav_btn.setToolTip("Ukloni iz omiljenih lekcija" if favorite else "Dodaj u omiljene lekcije")

    def set_favorite(self, favorite: bool) -> None:
        """Postavlja zvezdicu bez emitovanja signala."""
        self._fav_btn.blockSignals(True)
        self._fav_btn.setChecked(favorite)
        self._fav_btn.blockSignals(False)
        self._update_favorite_button(favorite)

    def is_favorite(self) -> bool:
        return self._fav_btn.isChecked()

    def set_completed(self, completed: bool) -> None:
        """Postavlja oznaku „završena“ bez emitovanja signala."""
        self._complete_btn.blockSignals(True)
        self._complete_btn.setChecked(completed)
        self._complete_btn.blockSignals(False)
        self._update_complete_button(completed)

    def set_progress(self, completed: int, available: int) -> None:
        """Prikazuje napredak kroz dostupne lekcije."""
        self._progress.setMaximum(max(1, available))
        self._progress.setValue(completed)
        percent = round(100 * completed / available) if available else 0
        self._progress_label.setText(f"{completed}/{available} završeno ({percent}%)")
        self._progress.setToolTip(f"Završeno {completed} od {available} dostupnih lekcija")

    def set_browser_checked(self, visible: bool) -> None:
        """Usklađuje dugme sa vidljivošću bočnog panela, bez emitovanja signala."""
        self._browser_btn.blockSignals(True)
        self._browser_btn.setChecked(visible)
        self._browser_btn.blockSignals(False)

    def set_confirm_solution(self, confirm: bool) -> None:
        """Da li se pre prikaza rešenja traži potvrda."""
        self._confirm_solution = confirm

    def set_exercise_status(self, status: LessonStatus | None) -> None:
        """Prikazuje broj provera i datum rešavanja u kartici „Zadatak“."""
        self._status = status
        self._render_task()

    def set_code_font(self, font) -> None:
        self._example_code.set_editor_font(font)

    def set_quiz_info(self, record: QuizRecord | None) -> None:
        """Prikazuje opis kviza i dosadašnje rezultate (poziva se posle show_lesson)."""
        if self._lesson is None:
            return
        theme = current_theme()
        c = theme.colors
        quiz = self._lesson.quiz
        total = len(quiz)
        if not total:
            self._quiz_view.setHtml(fmt.page("<p>Ova lekcija nema kviz.</p>", theme))
            self._quiz_btn.setEnabled(False)
            return
        kinds: dict[str, int] = {}
        for q in quiz:
            kinds[q.kind.label] = kinds.get(q.kind.label, 0) + 1
        kind_items = "".join(
            f"<li>{html.escape(label)}: {count}</li>" for label, count in kinds.items())
        body = (
            f"<p>Kratak kviz proverava da li si razumeo lekciju. Ima <b>{total}</b> pitanja, "
            f"a za prolaz je potrebno bar <b>{required_to_pass(total)}</b> tačnih odgovora.</p>"
            f"<ul style='margin-top:0;'>{kind_items}</ul>"
            f"<p style='color:{c['text_muted']};'>Posle svakog odgovora vidiš objašnjenje. Kod pitanja "
            f"sa programom možeš da pokreneš program i uveriš se šta zaista ispisuje. "
            f"Kviz možeš ponavljati koliko god želiš — čuva se najbolji rezultat.</p>"
        )
        if record is not None:
            state = ("<span style='color:{0}; font-weight:600;'>položen</span>".format(c["success"])
                     if record.passed else
                     "<span style='color:{0}; font-weight:600;'>još nije položen</span>".format(c["warning"]))
            body += fmt.heading("Tvoji rezultati", theme) + (
                f"<p>Najbolji rezultat: <b>{record.best}/{record.total}</b> · poslednji: "
                f"{record.last}/{record.total} · pokušaja: {record.attempts} · kviz je {state}.</p>"
            )
        self._quiz_view.setHtml(fmt.page(body, theme))
        self._quiz_btn.setEnabled(True)
        self._quiz_btn.setText("Ponovi kviz" if record is not None else "Započni kviz")

    def current_tab(self) -> int:
        return self._tabs.currentIndex()

    def set_current_tab(self, index: int) -> None:
        if 0 <= index < self._tabs.count():
            self._tabs.setCurrentIndex(index)

    def show_quiz_tab(self) -> None:
        self._tabs.setCurrentIndex(3)

    def show_task_tab(self) -> None:
        self._tabs.setCurrentIndex(2)

    # ------------------------------------------------------------------ veličina
    @property
    def size_mode(self) -> str:
        return self._size_mode

    def set_size_mode(self, mode: str, emit: bool = True) -> None:
        if mode not in _SIZE_ORDER:
            mode = SIZE_NORMAL
        self._size_mode = mode
        compact = mode == SIZE_COMPACT
        self._tabs.setVisible(not compact)
        self._goal_row.setVisible(not compact)
        self._update_size_buttons()
        if emit:
            self.size_mode_changed.emit(mode)

    def _step_size(self, delta: int) -> None:
        index = _SIZE_ORDER.index(self._size_mode) + delta
        index = max(0, min(len(_SIZE_ORDER) - 1, index))
        self.set_size_mode(_SIZE_ORDER[index])

    def _update_size_buttons(self) -> None:
        index = _SIZE_ORDER.index(self._size_mode)
        self._shrink_btn.setEnabled(index > 0)
        self._grow_btn.setEnabled(index < len(_SIZE_ORDER) - 1)

    def compact_height(self) -> int:
        """Visina panela kada su prikazani samo naslov i navigacija."""
        return self.layout().contentsMargins().top() + 92
