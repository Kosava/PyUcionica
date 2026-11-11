# pyqt6_learning_studio/ui/quiz_dialog.py
"""Dijalog kviza: pitanje po pitanje, objašnjenje posle svakog odgovora, rezime na kraju.

Kod pitanja „Predvidi rezultat“ i „Upiši šta program ispisuje“ korisnik posle
odgovora može da pokrene program (u zasebnom procesu, kao i kod iz editora) i
vidi stvarni izlaz.
"""

from __future__ import annotations

import html
import random

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import RunnerLimits
from core.code_runner import CodeRunner, RunResult, RunStatus
from core.python_locator import Interpreter
from core.quiz_manager import QuizSession
from models.quiz import QuestionKind, QuizQuestion
from ui.code_editor import CodeEditor, editor_font
from ui.icons import icon, pixmap
from ui.theme import current_theme
from ui.widgets.feedback_card import FeedbackCard

def _code_html(text: str) -> str:
    """Višeredni tekst kao blok koda (za prikaz tačnog odgovora)."""
    c = current_theme().colors
    return (f"<pre style='margin:4px 0 0 0; padding:6px; background:{c['code_bg']}; "
            f"font-family:monospace;'>{html.escape(text)}</pre>")


_QUIZ_RUN_LIMITS = RunnerLimits(timeout_ms=3_000, max_output_chars=5_000, kill_grace_ms=500)


class QuizDialog(QDialog):
    """Kviz jedne lekcije.

    Posle zatvaranja, ``result_score`` / ``result_total`` / ``result_passed``
    sadrže rezultat poslednjeg ZAVRŠENOG pokušaja (ili ``None`` ako kviz nije
    završen). Svaki završen pokušaj se prijavljuje i preko ``on_finished``.

    Args:
        title: Naslov (npr. „Lekcija 6: Promenljive“).
        questions: Pitanja kviza.
        on_finished: Funkcija koja se poziva posle svakog završenog pokušaja,
            sa argumentima (score, total, passed).
        rng: Generator slučajnih brojeva (za ponovljive testove).
    """

    def __init__(self, title: str, questions: tuple[QuizQuestion, ...], on_finished=None,
                 parent: QWidget | None = None, rng: random.Random | None = None,
                 interpreter: Interpreter | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Kviz — {title}")
        self.setModal(True)
        self.resize(720, 640)
        self.setMinimumSize(560, 480)
        self._title = title
        self._questions = questions
        self._on_finished = on_finished
        self._rng = rng
        self._session: QuizSession | None = None
        self.result_score: int | None = None
        self.result_total: int | None = None
        self.result_passed: bool | None = None

        self._runner = CodeRunner(_QUIZ_RUN_LIMITS, parent=self, interpreter=interpreter)
        self._runner.finished.connect(self._on_run_finished)
        self._run_output_parts: list[str] = []
        self._runner.stdout_received.connect(self._run_output_parts.append)
        self._runner.stderr_received.connect(self._run_output_parts.append)

        c = current_theme().colors
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # --- zaglavlje
        head = QHBoxLayout()
        head_icon = QLabel()
        head_icon.setPixmap(pixmap("award", c["accent"], 20))
        self._head_title = QLabel(f"Kviz: {html.escape(title)}")
        self._head_title.setObjectName("PanelTitle")
        self._counter = QLabel()
        self._counter.setObjectName("Muted")
        head.addWidget(head_icon)
        head.addWidget(self._head_title, 1)
        head.addWidget(self._counter)
        root.addLayout(head)
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        root.addWidget(self._progress)

        self._pages = QStackedWidget()
        root.addWidget(self._pages, 1)
        self._pages.addWidget(self._build_question_page())
        self._pages.addWidget(self._build_summary_page())

        # --- dugmad
        buttons = QHBoxLayout()
        self._close_btn = QPushButton("Zatvori")
        self._close_btn.clicked.connect(self.reject)
        self._retry_btn = QPushButton(icon("rotate-ccw", c["icon"]), "Ponovi kviz")
        self._retry_btn.clicked.connect(self.start)
        self._primary_btn = QPushButton()
        self._primary_btn.setObjectName("PrimaryButton")
        self._primary_btn.setDefault(True)
        self._primary_btn.clicked.connect(self._on_primary)
        buttons.addWidget(self._close_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._retry_btn)
        buttons.addWidget(self._primary_btn)
        root.addLayout(buttons)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_primary)
        self.start()

    # ================================================================== izgradnja
    def _build_question_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        self._question_scroll = scroll
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(10)

        self._kind_label = QLabel()
        self._kind_label.setObjectName("ModuleLabel")
        self._question_label = QLabel()
        self._question_label.setObjectName("QuizQuestion")
        self._question_label.setWordWrap(True)
        self._question_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._kind_label)
        layout.addWidget(self._question_label)

        self._code_frame = QFrame()
        self._code_frame.setObjectName("Panel")
        cf = QVBoxLayout(self._code_frame)
        cf.setContentsMargins(1, 1, 1, 1)
        self._code_view = CodeEditor(read_only=True)
        self._code_view.setMinimumHeight(70)
        cf.addWidget(self._code_view)
        layout.addWidget(self._code_frame)

        self._options_box = QWidget()
        self._options_layout = QVBoxLayout(self._options_box)
        self._options_layout.setContentsMargins(0, 0, 0, 0)
        self._options_layout.setSpacing(6)
        self._option_group = QButtonGroup(self)
        self._option_group.idClicked.connect(lambda _id: self._update_buttons())
        layout.addWidget(self._options_box)

        self._text_answer = QPlainTextEdit()
        self._text_answer.setObjectName("QuizAnswer")
        self._text_answer.setFont(editor_font())
        self._text_answer.setPlaceholderText("Upiši tačno ono što će program ispisati, red po red…")
        self._text_answer.setFixedHeight(90)
        self._text_answer.textChanged.connect(self._update_buttons)
        layout.addWidget(self._text_answer)

        self._feedback = FeedbackCard()
        layout.addWidget(self._feedback)

        self._run_row = QWidget()
        rr = QVBoxLayout(self._run_row)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.setSpacing(6)
        run_buttons = QHBoxLayout()
        c = current_theme().colors
        self._run_btn = QPushButton(icon("play", c["icon"]), "Pokreni program i proveri")
        self._run_btn.setToolTip("Pokreni ovaj kod i pogledaj šta stvarno ispisuje")
        self._run_btn.clicked.connect(self._run_code)
        run_buttons.addWidget(self._run_btn)
        run_buttons.addStretch(1)
        rr.addLayout(run_buttons)
        self._run_output = QPlainTextEdit()
        self._run_output.setObjectName("OutputView")
        self._run_output.setReadOnly(True)
        self._run_output.setFont(editor_font())
        self._run_output.setFixedHeight(90)
        rr.addWidget(self._run_output)
        layout.addWidget(self._run_row)
        layout.addStretch(1)
        return page

    def _build_summary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        self._summary_icon = QLabel()
        self._summary_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_score = QLabel()
        self._summary_score.setObjectName("HomeTitle")
        self._summary_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_text = QLabel()
        self._summary_text.setWordWrap(True)
        self._summary_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_text.setObjectName("Muted")
        layout.addWidget(self._summary_icon)
        layout.addWidget(self._summary_score)
        layout.addWidget(self._summary_text)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._review = QWidget()
        self._review_layout = QVBoxLayout(self._review)
        self._review_layout.setContentsMargins(0, 0, 0, 0)
        self._review_layout.setSpacing(6)
        scroll.setWidget(self._review)
        layout.addWidget(scroll, 1)
        return page

    # ================================================================== tok kviza
    def start(self) -> None:
        """Počinje (novi) pokušaj — odgovori se ponovo mešaju."""
        self._runner.shutdown()
        self._session = QuizSession(self._questions, rng=self._rng)
        self._progress.setMaximum(self._session.total)
        self._pages.setCurrentIndex(0)
        self._show_question()

    def _show_question(self) -> None:
        session = self._session
        assert session is not None
        presented = session.current
        q = presented.question
        self._counter.setText(f"Pitanje {session.index + 1} od {session.total}")
        self._progress.setValue(session.index)
        self._kind_label.setText(q.kind.label.upper())
        self._question_label.setText(q.question)

        has_code = bool(q.code.strip())
        self._code_frame.setVisible(has_code)
        if has_code:
            self._code_view.set_text(q.code.rstrip("\n"))
            lines = max(2, len(q.code.rstrip("\n").splitlines()))
            self._code_view.setFixedHeight(int(min(260, 22 + lines * self.fontMetrics().height() * 1.3)))

        for button in self._option_group.buttons():
            self._option_group.removeButton(button)
            button.deleteLater()
        is_text = q.kind is QuestionKind.OUTPUT
        self._options_box.setVisible(not is_text)
        self._text_answer.setVisible(is_text)
        self._text_answer.setReadOnly(False)
        self._text_answer.clear()
        if not is_text:
            for index, text in enumerate(presented.options):
                radio = QRadioButton(text)
                radio.setObjectName("QuizOption")
                if q.kind is QuestionKind.PREDICT:
                    radio.setFont(editor_font())
                self._option_group.addButton(radio, index)
                self._options_layout.addWidget(radio)
        else:
            self._text_answer.setFocus()

        self._feedback.clear()
        self._run_row.setVisible(False)
        self._run_output.clear()
        self._update_buttons()

    def _current_answer(self) -> int | str | None:
        q = self._session.current.question
        if q.kind is QuestionKind.OUTPUT:
            text = self._text_answer.toPlainText()
            return text if text.strip() else None
        checked = self._option_group.checkedId()
        return checked if checked >= 0 else None

    def _update_buttons(self) -> None:
        session = self._session
        if session is None:
            return
        on_summary = self._pages.currentIndex() == 1
        self._retry_btn.setVisible(on_summary)
        self._close_btn.setVisible(not on_summary)
        if on_summary:
            self._primary_btn.setText("Zatvori")
            self._primary_btn.setEnabled(True)
            return
        if not session.is_answered():
            self._primary_btn.setText("Proveri odgovor")
            self._primary_btn.setEnabled(self._current_answer() is not None)
        elif session.is_last:
            self._primary_btn.setText("Pogledaj rezultat")
            self._primary_btn.setEnabled(True)
        else:
            self._primary_btn.setText("Sledeće pitanje")
            self._primary_btn.setEnabled(True)

    def _on_primary(self) -> None:
        session = self._session
        if session is None or not self._primary_btn.isEnabled():
            return
        if self._pages.currentIndex() == 1:
            self.accept()
        elif not session.is_answered():
            self._check_answer()
        elif session.next():
            self._show_question()
        else:
            self._show_summary()

    def _check_answer(self) -> None:
        answer = self._current_answer()
        if answer is None:
            return
        session = self._session
        q = session.current.question
        result = session.answer(answer)
        c = current_theme().colors

        # Oboji ponuđene odgovore: tačan zeleno, pogrešno izabran crveno.
        correct_index = session.current.correct_display_index
        for button in self._option_group.buttons():
            button_id = self._option_group.id(button)
            button.setEnabled(False)
            if button_id == correct_index:
                button.setStyleSheet(f"color: {c['success']}; font-weight: 600;")
            elif button_id == answer:
                button.setStyleSheet(f"color: {c['error']}; text-decoration: line-through;")
        self._text_answer.setReadOnly(True)

        if result.correct:
            title, kind = "Tačno!", "success"
            body = html.escape(result.explanation)
        else:
            title, kind = "Nije tačno.", "error"
            body = "Tačan odgovor:" + _code_html(result.correct_text)
            if result.explanation:
                body += f"<br><br>{html.escape(result.explanation)}"
        self._feedback.show_feedback(kind, title, body)
        self._run_row.setVisible(q.kind is not QuestionKind.CHOICE)
        self._run_output.setPlainText("Klikni „Pokreni program i proveri“ da vidiš šta program zaista ispisuje.")
        self._scroll_to_bottom()
        self._progress.setValue(session.index + 1)
        self._update_buttons()

    def _run_code(self) -> None:
        if self._runner.is_running() or self._session is None:
            return
        self._run_output_parts.clear()
        self._run_output.setPlainText("Pokretanje…")
        self._run_btn.setEnabled(False)
        self._runner.run(self._session.current.question.code, stdin_text="")

    def _on_run_finished(self, result: RunResult) -> None:
        self._run_btn.setEnabled(True)
        text = "".join(self._run_output_parts).rstrip("\n")
        if result.status is not RunStatus.SUCCESS and result.status is not RunStatus.ERROR:
            text += f"\n({result.status.label})"
        self._run_output.setPlainText(text if text else "(program nije ništa ispisao)")
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        bar = self._question_scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _show_summary(self) -> None:
        session = self._session
        c = current_theme().colors
        self.result_score = session.score
        self.result_total = session.total
        self.result_passed = session.passed
        if self._on_finished is not None:
            self._on_finished(session.score, session.total, session.passed)

        self._pages.setCurrentIndex(1)
        self._counter.setText("Rezultat")
        self._progress.setValue(session.total)
        self._summary_icon.setPixmap(pixmap(
            "award" if session.passed else "rotate-ccw",
            c["success"] if session.passed else c["warning"], 48))
        self._summary_score.setText(f"{session.score} / {session.total}")
        if session.passed:
            self._summary_text.setText(
                "Kviz je položen! Odlično razumeš gradivo ove lekcije.")
        else:
            self._summary_text.setText(
                f"Za prolaz je potrebno bar {session.required} tačnih odgovora. Pročitaj ponovo "
                "objašnjenja pitanja na koja nisi tačno odgovorio i pokušaj još jednom — "
                "odgovori će biti drugačije poređani.")

        while self._review_layout.count():
            item = self._review_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for index, (presented, result) in enumerate(zip(session.questions, session.results), start=1):
            row = QFrame()
            row.setObjectName("Card")
            row.setProperty("kind", "success" if result and result.correct else "error")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 8, 10, 8)
            mark = QLabel()
            mark.setPixmap(pixmap("check-circle" if result and result.correct else "x-circle",
                                  c["success"] if result and result.correct else c["error"], 16))
            text = QLabel(f"<b>{index}.</b> {html.escape(presented.question.question)}"
                          + ("" if result and result.correct else
                             f"<br><span style='color:{c['text_muted']}'>Tačno: "
                             f"{html.escape(presented.question.correct_text).replace(chr(10), ' ⏎ ')}</span>"))
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.RichText)
            rl.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
            rl.addWidget(text, 1)
            self._review_layout.addWidget(row)
        self._review_layout.addStretch(1)
        self._update_buttons()

    # ================================================================== zatvaranje
    def done(self, result: int) -> None:  # noqa: D401 - Qt API
        self._runner.shutdown()
        super().done(result)
