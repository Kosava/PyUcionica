# pyqt6_learning_studio/ui/output_panel.py
"""Donji desni panel: rezultat izvršavanja, status, vreme, objašnjenje grešaka i unos za input().

Panel samo prikazuje podatke; pokretanje koda i provera zadataka su u
``core`` sloju, a povezuje ih glavni prozor.
"""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.code_runner import RunResult, RunStatus
from core.error_explainer import ErrorInfo
from core.exercise_checker import CheckReport
from ui.code_editor import editor_font
from ui.icons import icon, pixmap
from ui.theme import current_theme, repolish
from ui.widgets.feedback_card import FeedbackCard, FeedbackLine


class OutputPanel(QFrame):
    """Prikaz rezultata pokretanja.

    Signals:
        input_submitted(str): Korisnik je poslao red unosa programu.
        stop_requested: Kliknuto je „Zaustavi“.
        go_to_line_requested(int): Korisnik želi da vidi liniju sa greškom.
        complete_and_next_requested: Posle uspešne provere — završi lekciju i pređi dalje.
    """

    input_submitted = pyqtSignal(str)
    stop_requested = pyqtSignal()
    go_to_line_requested = pyqtSignal(int)
    complete_and_next_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._error_line: int | None = None
        self._card_action: str = ""
        c = current_theme().colors

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- zaglavlje
        header = QFrame()
        header.setObjectName("PanelHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 8, 8, 8)
        h.setSpacing(8)
        title_icon = QLabel()
        title_icon.setPixmap(pixmap("terminal", c["icon"], 16))
        title = QLabel("Rezultat")
        title.setObjectName("PanelTitle")
        self._status = QLabel()
        self._status.setObjectName("StatusBadge")
        self._time = QLabel("")
        self._time.setObjectName("Faint")
        self._time.setToolTip("Vreme izvršavanja (bez vremena čekanja na unos)")
        self._stop_btn = QPushButton(icon("stop", c["error"]), "Zaustavi")
        self._stop_btn.setObjectName("DangerButton")
        self._stop_btn.setToolTip("Prekini program koji se izvršava")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested)
        self._clear_btn = QPushButton(icon("trash", c["icon"]), "Očisti")
        self._clear_btn.setToolTip("Obriši prikazani izlaz")
        self._clear_btn.clicked.connect(self.clear)
        h.addWidget(title_icon)
        h.addWidget(title)
        h.addSpacing(4)
        h.addWidget(self._status)
        h.addWidget(self._time)
        h.addStretch(1)
        h.addWidget(self._stop_btn)
        h.addWidget(self._clear_btn)
        root.addWidget(header)

        # --- izlaz + kartica sa objašnjenjem (podesiva visina)
        self._view = QPlainTextEdit()
        self._view.setObjectName("OutputView")
        self._view.setReadOnly(True)
        self._view.setFont(editor_font())
        self._view.setUndoRedoEnabled(False)
        self._view.setPlaceholderText(
            "Ovde se prikazuje rezultat programa.\n\n"
            "Napiši kod u editoru levo i klikni „Pokreni“ (ili pritisni Ctrl+Enter)."
        )
        self._view.document().setDocumentMargin(10)

        self._card = FeedbackCard()
        self._card.action_clicked.connect(self._on_card_action)
        card_holder = QWidget()
        card_holder.setObjectName("CardHolder")
        card_layout = QVBoxLayout(card_holder)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.addWidget(self._card)
        card_layout.addStretch(1)
        self._card_scroll = QScrollArea()
        self._card_scroll.setObjectName("CardScroll")
        self._card_scroll.setWidgetResizable(True)
        self._card_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._card_scroll.setWidget(card_holder)
        self._card_scroll.hide()

        self._split = QSplitter(Qt.Orientation.Vertical)
        self._split.setChildrenCollapsible(False)
        self._split.setHandleWidth(5)
        self._split.addWidget(self._view)
        self._split.addWidget(self._card_scroll)
        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 2)
        root.addWidget(self._split, 1)

        # --- unos za input()
        self._input_bar = QFrame()
        self._input_bar.setObjectName("InputBar")
        self._input_bar.setProperty("waiting", "false")
        ib = QHBoxLayout(self._input_bar)
        ib.setContentsMargins(10, 6, 8, 6)
        ib.setSpacing(8)
        input_label = QLabel("Unos za program:")
        input_label.setObjectName("Muted")
        self._input = QLineEdit()
        self._input.setPlaceholderText("Aktivno samo kada program pozove input()")
        self._input.returnPressed.connect(self._submit_input)
        self._send_btn = QPushButton(icon("send", c["icon"]), "Pošalji")
        self._send_btn.clicked.connect(self._submit_input)
        ib.addWidget(input_label)
        ib.addWidget(self._input, 1)
        ib.addWidget(self._send_btn)
        root.addWidget(self._input_bar)

        self._formats = self._make_formats()
        self.set_running(False)
        self._set_status("idle", "Spreman")

    # ------------------------------------------------------------------ formati
    def _make_formats(self) -> dict[str, QTextCharFormat]:
        c = current_theme().colors
        formats = {}
        for key, color in (("stdout", c["out_stdout"]), ("stderr", c["out_stderr"]),
                           ("info", c["out_info"]), ("input", c["out_input"])):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if key == "input":
                fmt.setFontWeight(600)
            if key == "info":
                fmt.setFontItalic(True)
            formats[key] = fmt
        return formats

    def _append(self, text: str, kind: str) -> None:
        cursor = self._view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, self._formats[kind])
        self._view.setTextCursor(cursor)
        self._view.ensureCursorVisible()

    def _ensure_newline(self) -> None:
        text = self._view.toPlainText()
        if text and not text.endswith("\n"):
            self._append("\n", "info")

    # ------------------------------------------------------------------ status
    def _set_status(self, state: str, text: str) -> None:
        self._status.setText(text)
        self._status.setProperty("state", state)
        repolish(self._status)

    def set_running(self, running: bool, interactive: bool = True) -> None:
        self._stop_btn.setEnabled(running)
        self._input.setEnabled(running and interactive)
        self._send_btn.setEnabled(running and interactive)
        if not running:
            self._set_waiting(False)

    def _set_waiting(self, waiting: bool) -> None:
        self._input_bar.setProperty("waiting", "true" if waiting else "false")
        repolish(self._input_bar)
        self._input.setPlaceholderText(
            "Program čeka unos — upiši odgovor i pritisni Enter" if waiting
            else "Aktivno samo kada program pozove input()"
        )

    # ------------------------------------------------------------------ javni API
    def start_run(self, title: str = "Pokretanje programa") -> None:
        """Priprema panel za novo pokretanje (briše stari izlaz i karticu)."""
        self._view.clear()
        self._hide_card()
        self._time.setText("")
        self._append(f"{title}…\n\n", "info")
        self._set_status("running", "Izvršava se…")
        self.set_running(True)

    def start_check(self) -> None:
        """Priprema panel za proveru zadatka (unos zadaje aplikacija, ne korisnik)."""
        self.start_run("Provera zadatka")
        self.set_running(True, interactive=False)

    def begin_check_case(self, index: int, total: int, input_label: str) -> None:
        """Naslov jednog test slučaja u izlazu."""
        if total <= 1:
            return
        self._ensure_newline()
        if index > 1:
            self._append("\n", "info")
        label = f"Test {index}/{total}"
        if input_label:
            label += f" · unos: {input_label}"
        self._append(f"── {label} ──\n", "info")

    def append_preset_input(self, text: str) -> None:
        """Prikazuje unos koji je aplikacija poslala programu tokom provere."""
        self._append(text + "\n", "input")

    def finish_check(self, results: list[RunResult], passed: bool) -> None:
        """Završni status provere sa više pokretanja."""
        self.set_running(False)
        total_time = sum(r.duration_s for r in results)
        self._time.setText(f"{total_time:.2f} s")
        self._ensure_newline()
        aborted = next((r for r in results if r.status not in (RunStatus.SUCCESS, RunStatus.ERROR)), None)
        if aborted is not None:
            self._set_status("warning", aborted.status.label)
        elif any(r.status is RunStatus.ERROR for r in results):
            self._set_status("error", "Provera: greška u programu")
        elif passed:
            self._set_status("success", "Zadatak rešen")
        else:
            self._set_status("warning", "Provera: nije prošla")
        runs = "pokretanje" if len(results) == 1 else "pokretanja"
        self._append(f"\nProvera je završena ({len(results)} {runs}, {total_time:.2f} s).\n", "info")

    def append_stdout(self, text: str) -> None:
        self._append(text, "stdout")

    def append_stderr(self, text: str) -> None:
        self._append(text, "stderr")

    def show_waiting_for_input(self) -> None:
        self._set_status("input", "Čeka unos")
        self._set_waiting(True)
        self._input.setFocus()

    def _submit_input(self) -> None:
        if not self._input.isEnabled():
            return
        text = self._input.text()
        self._input.clear()
        self._append(text + "\n", "input")
        self._set_waiting(False)
        self._set_status("running", "Izvršava se…")
        self.input_submitted.emit(text)

    def finish(self, result: RunResult) -> None:
        """Prikazuje završni status izvršavanja."""
        self.set_running(False)
        self._time.setText(f"{result.duration_s:.2f} s")
        state = {
            RunStatus.SUCCESS: "success",
            RunStatus.ERROR: "error",
            RunStatus.FAILED_TO_START: "error",
        }.get(result.status, "warning")
        self._set_status(state, result.status.label)
        self._ensure_newline()
        if result.status is RunStatus.SUCCESS:
            if not result.stdout:
                self._append("(Program se izvršio, ali nije ništa ispisao.)\n", "info")
            self._append(f"\nProgram je završen za {result.duration_s:.2f} s.\n", "info")
        elif result.status is RunStatus.ERROR and result.exit_code not in (None, 1):
            self._append(f"Program je završen sa povratnim kodom {result.exit_code}.\n", "info")
        elif result.status is RunStatus.TIMEOUT:
            self._append("\nProgram je radio predugo i automatski je zaustavljen.\n", "info")
            self._show_status_card(
                "warning", "Program je prekoračio dozvoljeno vreme",
                "Najčešći uzrok je petlja koja se nikada ne završava. Proveri uslove petlji "
                "i da li se promenljive u njima menjaju.",
            )
        elif result.status is RunStatus.STOPPED:
            self._append("\nProgram je prekinut na tvoj zahtev.\n", "info")
        elif result.status is RunStatus.OUTPUT_LIMIT:
            self._append("\nProgram je ispisao previše teksta i zaustavljen je.\n", "info")
            self._show_status_card(
                "warning", "Previše izlaza",
                "Program je ispisao više teksta nego što je dozvoljeno — verovatno print() "
                "unutar petlje koja se ne završava.",
            )
        elif result.status is RunStatus.FAILED_TO_START:
            self._append(result.message + "\n", "stderr")

    def show_error(self, info: ErrorInfo, in_test_code: bool = False) -> None:
        """Prikazuje objašnjenje greške razumljivo početniku.

        Args:
            info: Objašnjena greška.
            in_test_code: Greška je nastala u kodu koji je aplikacija dodala radi
                provere (npr. poziv tvoje funkcije), a ne u tvojim linijama.
        """
        line = None if in_test_code else info.line
        self._error_line = line
        self._card_action = "line" if line else ""
        if in_test_code:
            where = ("Greška je nastala dok je aplikacija testirala tvoj kod (npr. pozivom tvoje "
                     "funkcije). Proveri da li funkcija postoji i da li se tačno tako zove, "
                     "i koliko vrednosti prima. ")
        else:
            where = f"Greška je u liniji <b>{info.line}</b>. " if info.line else ""
        body = (
            f"{where}{html.escape(info.explanation)}"
            f"<br><br><b>Šta da probaš:</b> {html.escape(info.tip)}"
            f"<br><br><span style='color:{current_theme().colors['text_muted']}'>"
            f"Python kaže: <code>{html.escape(info.exc_type)}"
            f"{': ' + html.escape(info.message) if info.message else ''}</code></span>"
        )
        self._card.show_feedback(
            "error", info.title, body,
            action_text=f"Idi na liniju {line}" if line else "",
        )
        self._show_card()

    def show_check_report(self, report: CheckReport, attempts: int | None = None,
                          next_action: str = "") -> None:
        """Prikazuje rezultat provere zadatka.

        Args:
            report: Izveštaj provere.
            attempts: Broj pokušaja (prikazuje se ispod).
            next_action: Tekst dugmeta posle uspešne provere (npr. „Završi lekciju
                i pređi na sledeću“); prazno = bez dugmeta.
        """
        self._error_line = None
        self._card_action = "next" if report.passed and next_action else ""
        lines = [FeedbackLine(item.ok, html.escape(item.message), html.escape(item.detail))
                 for item in report.items]
        footer = f"<b>Sledeći korak:</b> {html.escape(report.next_step)}" if report.next_step else ""
        if attempts:
            footer += f"<br><span style='color:{current_theme().colors['text_muted']}'>Pokušaj broj {attempts}.</span>"
        self._card.show_feedback(
            "success" if report.passed else "warning",
            report.summary, "", lines, footer,
            action_text=next_action if self._card_action == "next" else "",
        )
        self._show_card()

    def show_message(self, kind: str, title: str, body: str) -> None:
        self._show_status_card(kind, title, body)

    def _show_status_card(self, kind: str, title: str, body: str) -> None:
        self._error_line = None
        self._card_action = ""
        self._card.show_feedback(kind, title, html.escape(body))
        self._show_card()

    def _show_card(self) -> None:
        if not self._card_scroll.isVisible():
            self._card_scroll.show()
            total = max(200, self._split.height())
            self._split.setSizes([int(total * 0.55), int(total * 0.45)])

    def _hide_card(self) -> None:
        self._card.clear()
        self._card_scroll.hide()
        self._error_line = None
        self._card_action = ""

    def _on_card_action(self) -> None:
        if self._card_action == "line" and self._error_line:
            self.go_to_line_requested.emit(self._error_line)
        elif self._card_action == "next":
            self.complete_and_next_requested.emit()

    def set_output_font(self, font) -> None:
        self._view.setFont(font)

    def clear(self) -> None:
        """Briše izlaz i karticu i vraća status na „Spreman“ (ako program ne radi)."""
        self._view.clear()
        self._hide_card()
        if not self._stop_btn.isEnabled():
            self._time.setText("")
            self._set_status("idle", "Spreman")
