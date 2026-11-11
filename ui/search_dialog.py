# pyqt6_learning_studio/ui/search_dialog.py
"""Dijalog „Pretraži lekcije“: pretraga kroz ceo sadržaj kursa, sa isečcima i istaknutim pogocima.

Pretraga se pokreće dok korisnik kuca (sa kratkim zastojem). Enter ili klik na
rezultat otvara lekciju.
"""

from __future__ import annotations

import html

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.lesson_search import LessonSearch, SearchHit
from ui.icons import icon
from ui.theme import current_theme

ROLE_LESSON_ID = Qt.ItemDataRole.UserRole


def lessons_label(count: int) -> str:
    """„1 lekcija“, „3 lekcije“, „5 lekcija“, „21 lekcija“, „12 lekcija“."""
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} lekcije"
    return f"{count} lekcija"


def highlight(snippet: str, spans: tuple[tuple[int, int], ...]) -> str:
    """HTML isečka sa istaknutim pogocima."""
    c = current_theme().colors
    parts: list[str] = []
    last = 0
    for start, end in spans:
        parts.append(html.escape(snippet[last:start]))
        parts.append(f"<span style='background:{c['warning_soft']}; color:{c['text']}; "
                     f"font-weight:600;'>{html.escape(snippet[start:end])}</span>")
        last = end
    parts.append(html.escape(snippet[last:]))
    return "".join(parts)


class SearchDialog(QDialog):
    """Pretraga lekcija.

    Signals:
        lesson_selected(str): Korisnik je izabrao lekciju.
    """

    lesson_selected = pyqtSignal(str)

    def __init__(self, search: LessonSearch, module_titles: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pretraži lekcije")
        self.resize(680, 560)
        self._search = search
        self._module_titles = module_titles
        c = current_theme().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self._input = QLineEdit()
        self._input.setObjectName("SearchInput")
        self._input.setPlaceholderText("Upiši pojam, npr. „f-string“, „deljenje“, „input“…")
        self._input.setClearButtonEnabled(True)
        self._input.addAction(icon("search", c["text_faint"]), QLineEdit.ActionPosition.LeadingPosition)
        self._input.installEventFilter(self)
        layout.addWidget(self._input)

        self._info = QLabel()
        self._info.setObjectName("Muted")
        layout.addWidget(self._info)

        self._results = QListWidget()
        self._results.setObjectName("SearchResults")
        self._results.setSpacing(2)
        self._results.itemActivated.connect(self._open_item)
        self._results.itemClicked.connect(self._open_item)
        layout.addWidget(self._results, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._run_search)
        self._input.textChanged.connect(lambda _t: self._timer.start())
        self._run_search()

    def set_query(self, text: str) -> None:
        self._input.setText(text)
        self._run_search()

    def _run_search(self) -> None:
        query = self._input.text().strip()
        self._results.clear()
        if not query:
            self._info.setText("Pretraga obuhvata naslove, objašnjenja, pojmove, primere, zadatke i kvizove "
                               "svih dostupnih lekcija. Kvačice nisu bitne: „secer“ pronalazi „šećer“.")
            return
        hits = self._search.search(query)
        if not hits:
            self._info.setText(f"Nema rezultata za „{query}“. Probaj kraću ili drugačiju reč.")
            return
        self._info.setText(f"Pronađeno: {lessons_label(len(hits))}. Enter ili klik otvara lekciju.")
        for hit in hits:
            self._add_hit(hit)
        self._results.setCurrentRow(0)

    def _add_hit(self, hit: SearchHit) -> None:
        c = current_theme().colors
        item = QListWidgetItem()
        item.setData(ROLE_LESSON_ID, hit.info.lesson_id)
        module = self._module_titles.get(hit.info.module_id, "")
        label = QLabel(
            f"<div style='margin:2px 0;'><b>{hit.info.number}. {html.escape(hit.info.title)}</b>"
            f"<br><span style='color:{c['text_muted']}; font-size:9pt;'>{html.escape(module)} · "
            f"pronađeno u: {html.escape(hit.field)}</span>"
            f"<br><span style='color:{c['text_muted']};'>{highlight(hit.snippet, hit.spans)}</span></div>")
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setContentsMargins(8, 6, 8, 6)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        width = max(300, self._results.viewport().width() - 20)
        item.setSizeHint(QSize(width, label.heightForWidth(width) + 4))
        self._results.addItem(item)
        self._results.setItemWidget(item, label)

    def _open_item(self, item: QListWidgetItem) -> None:
        lesson_id = item.data(ROLE_LESSON_ID)
        if lesson_id:
            self.lesson_selected.emit(lesson_id)
            self.accept()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        """Strelice gore/dole iz polja za unos pomeraju izbor u rezultatima; Enter otvara."""
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            navigation = (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Return, Qt.Key.Key_Enter)
            if key in navigation and self._timer.isActive():
                # Korisnik je kucao brže od zastoja — prvo završi pretragu.
                self._timer.stop()
                self._run_search()
            row = self._results.currentRow()
            if key == Qt.Key.Key_Down and self._results.count():
                self._results.setCurrentRow(min(row + 1, self._results.count() - 1))
                return True
            if key == Qt.Key.Key_Up and self._results.count():
                self._results.setCurrentRow(max(row - 1, 0))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._results.currentItem()
                if item is not None:
                    self._open_item(item)
                return True
        return super().eventFilter(obj, event)
