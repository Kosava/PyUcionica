# pyqt6_learning_studio/ui/widgets/feedback_card.py
"""Kartica sa povratnom informacijom: objašnjenje greške ili rezultat provere zadatka."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icons import pixmap
from ui.theme import current_theme, repolish


@dataclass(frozen=True)
class FeedbackLine:
    """Jedna stavka u kartici (npr. jedan kriterijum provere)."""

    ok: bool
    text: str
    detail: str = ""


_KIND_ICON = {
    "error": ("x-circle", "error"),
    "success": ("check-circle", "success"),
    "warning": ("alert-triangle", "warning"),
    "info": ("info", "accent"),
}


class FeedbackCard(QFrame):
    """Kartica sa naslovom, tekstom, opcionim stavkama i opcionim dugmetom.

    Signals:
        action_clicked: Kliknuto je dugme akcije (npr. „Idi na liniju 3“).
    """

    action_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("kind", "info")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._icon = QLabel()
        self._icon.setFixedSize(18, 18)
        self._title = QLabel()
        self._title.setObjectName("CardTitle")
        self._title.setWordWrap(True)
        header.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self._title, 1)
        root.addLayout(header)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._body)

        self._lines_box = QVBoxLayout()
        self._lines_box.setSpacing(4)
        root.addLayout(self._lines_box)

        self._footer = QLabel()
        self._footer.setWordWrap(True)
        self._footer.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self._footer)

        self._action = QPushButton()
        self._action.clicked.connect(self.action_clicked)
        action_row = QHBoxLayout()
        action_row.addWidget(self._action)
        action_row.addStretch(1)
        root.addLayout(action_row)
        self.hide()

    def _clear_lines(self) -> None:
        while self._lines_box.count():
            item = self._lines_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                layout = item.layout()
                while layout.count():
                    child = layout.takeAt(0).widget()
                    if child is not None:
                        child.deleteLater()

    def show_feedback(
        self,
        kind: str,
        title: str,
        body_html: str = "",
        lines: list[FeedbackLine] | None = None,
        footer_html: str = "",
        action_text: str = "",
    ) -> None:
        """Prikazuje karticu.

        Args:
            kind: ``"error"``, ``"success"``, ``"warning"`` ili ``"info"``.
            title: Naslov.
            body_html: Glavni tekst (HTML).
            lines: Stavke sa oznakom tačno/netačno.
            footer_html: Tekst na dnu (npr. predlog sledećeg koraka).
            action_text: Tekst dugmeta akcije; prazno = bez dugmeta.
        """
        theme = current_theme()
        c = theme.colors
        icon_name, color_key = _KIND_ICON.get(kind, _KIND_ICON["info"])
        self.setProperty("kind", kind)
        repolish(self)
        self._icon.setPixmap(pixmap(icon_name, c[color_key], 18))
        self._title.setText(title)
        self._title.setStyleSheet(f"color: {c[color_key]};")
        self._body.setText(body_html)
        self._body.setVisible(bool(body_html))

        self._clear_lines()
        for line in lines or []:
            row = QHBoxLayout()
            row.setSpacing(6)
            mark = QLabel()
            mark.setFixedSize(16, 16)
            mark.setPixmap(pixmap("check" if line.ok else "x-circle",
                                  c["success"] if line.ok else c["error"], 16))
            text = QLabel(line.text if not line.detail
                          else f"{line.text}<br><span style='color:{c['text_muted']}'>{line.detail}</span>")
            text.setTextFormat(Qt.TextFormat.RichText)
            text.setWordWrap(True)
            row.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(text, 1)
            self._lines_box.addLayout(row)

        self._footer.setText(footer_html)
        self._footer.setVisible(bool(footer_html))
        self._action.setText(action_text)
        self._action.setVisible(bool(action_text))
        self.show()

    def clear(self) -> None:
        self._clear_lines()
        self.hide()
