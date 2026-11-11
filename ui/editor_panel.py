# pyqt6_learning_studio/ui/editor_panel.py
"""Donji levi panel: editor koda sa dugmadima „Pokreni“, „Proveri zadatak“,
„Vrati početni kod“ i „Sačuvaj kod“."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.code_editor import CodeEditor
from ui.icons import icon, pixmap
from ui.theme import current_theme


class EditorPanel(QFrame):
    """Okvir oko editora koda.

    Signals:
        run_requested: „Pokreni“ ili Ctrl+Enter.
        check_requested: „Proveri zadatak“.
        reset_requested: „Vrati početni kod“.
        save_requested: „Sačuvaj kod“.
        line_numbers_toggled(bool): Uključeni/isključeni brojevi linija.
    """

    run_requested = pyqtSignal()
    check_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    save_requested = pyqtSignal()
    line_numbers_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        c = current_theme().colors

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("PanelHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 8, 8, 8)
        h.setSpacing(8)
        title_icon = QLabel()
        title_icon.setPixmap(pixmap("code", c["icon"], 16))
        title = QLabel("Editor koda")
        title.setObjectName("PanelTitle")
        self._modified = QLabel("")
        self._modified.setObjectName("Faint")
        self._line_numbers_btn = QToolButton()
        self._line_numbers_btn.setIcon(icon("hash", c["icon"]))
        self._line_numbers_btn.setCheckable(True)
        self._line_numbers_btn.setChecked(True)
        self._line_numbers_btn.setToolTip("Prikaži ili sakrij brojeve linija")
        self._line_numbers_btn.toggled.connect(self._on_line_numbers)
        shortcuts = QLabel("Ctrl+Enter pokreće · Ctrl+/ komentar")
        shortcuts.setObjectName("Faint")
        shortcuts.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        shortcuts.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(title_icon)
        h.addWidget(title)
        h.addWidget(self._modified)
        h.addWidget(shortcuts, 1)
        h.addWidget(self._line_numbers_btn)
        root.addWidget(header)

        self.editor = CodeEditor()
        self.editor.run_requested.connect(self.run_requested)
        self.editor.modified_changed.connect(self._on_modified_changed)
        root.addWidget(self.editor, 1)

        toolbar = QFrame()
        toolbar.setObjectName("InputBar")
        t = QHBoxLayout(toolbar)
        t.setContentsMargins(10, 6, 10, 6)
        t.setSpacing(8)
        self.run_btn = QPushButton(icon("play", c["accent_text"], c["text_faint"]), "Pokreni")
        self.run_btn.setObjectName("PrimaryButton")
        self.run_btn.setToolTip("Pokreni kod (Ctrl+Enter)")
        self.run_btn.clicked.connect(self.run_requested)
        self.check_btn = QPushButton(icon("clipboard-check", c["icon"]), "Proveri zadatak")
        self.check_btn.setToolTip("Pokreni kod i proveri da li ispunjava uslove zadatka")
        self.check_btn.clicked.connect(self.check_requested)
        self.reset_btn = QPushButton(icon("rotate-ccw", c["icon"]), "Vrati početni kod")
        self.reset_btn.setToolTip("Vrati kod zadatka na početno stanje")
        self.reset_btn.clicked.connect(self.reset_requested)
        self.save_btn = QPushButton(icon("save", c["icon"]), "Sačuvaj kod")
        self.save_btn.setToolTip("Sačuvaj kod za ovu lekciju (Ctrl+S)")
        self.save_btn.clicked.connect(self.save_requested)
        t.addWidget(self.run_btn)
        t.addWidget(self.check_btn)
        t.addStretch(1)
        t.addWidget(self.reset_btn)
        t.addWidget(self.save_btn)
        root.addWidget(toolbar)

        if not self.editor.uses_qscintilla:
            self._modified.setToolTip("QScintilla nije instaliran — koristi se osnovni editor.")

    def _on_line_numbers(self, checked: bool) -> None:
        self.editor.set_line_numbers_visible(checked)
        self.line_numbers_toggled.emit(checked)

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._line_numbers_btn.setChecked(visible)
        self.editor.set_line_numbers_visible(visible)

    def line_numbers_visible(self) -> bool:
        return self._line_numbers_btn.isChecked()

    def _on_modified_changed(self, modified: bool) -> None:
        self._modified.setText("• nesačuvane izmene" if modified else "")

    def set_running(self, running: bool) -> None:
        """Dok program radi, ne može se pokrenuti drugi."""
        self.run_btn.setEnabled(not running)
        self.check_btn.setEnabled(not running)
