# pyqt6_learning_studio/ui/lesson_browser.py
"""Bočni panel „Sadržaj kursa“: stablo modula i lekcija sa stanjem svake lekcije.

Klik na dostupnu lekciju emituje ``lesson_activated``; glavni prozor odlučuje
da li sme da je otvori (npr. posle pitanja o nesačuvanom kodu). Lekcije koje
su još u pripremi prikazane su sivo, sa katancem, i ne mogu se otvoriti.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from core.course_progress import LessonState, lesson_state
from core.lesson_manager import LessonManager
from core.lesson_search import fold
from core.progress_manager import ProgressManager
from ui.icons import icon, pixmap
from ui.theme import current_theme

ROLE_LESSON_ID = Qt.ItemDataRole.UserRole
ROLE_MODULE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_FAVORITE = Qt.ItemDataRole.UserRole + 2
ROLE_TITLE = Qt.ItemDataRole.UserRole + 3

_STATE_ICON = {
    LessonState.COMPLETED: ("check-circle", "success"),
    LessonState.SOLVED: ("clipboard-check", "accent"),
    LessonState.NOT_STARTED: ("circle", "text_faint"),
    LessonState.LOCKED: ("lock", "text_faint"),
}


class LessonBrowser(QFrame):
    """Stablo kursa.

    Signals:
        lesson_activated(str): Korisnik je izabrao dostupnu lekciju.
    """

    lesson_activated = pyqtSignal(str)

    def __init__(self, lessons: LessonManager, progress: ProgressManager,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._lessons = lessons
        self._progress = progress
        self._current_id: str | None = None
        self._favorites_only = False
        c = current_theme().colors

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("PanelHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 9, 12, 9)
        h.setSpacing(8)
        title_icon = QLabel()
        title_icon.setPixmap(pixmap("layers", c["icon"], 16))
        title = QLabel("Sadržaj kursa")
        title.setObjectName("PanelTitle")
        self._summary = QLabel()
        self._summary.setObjectName("Faint")
        h.addWidget(title_icon)
        h.addWidget(title)
        h.addStretch(1)
        h.addWidget(self._summary)
        root.addWidget(header)

        filter_box = QWidget()
        f = QHBoxLayout(filter_box)
        f.setContentsMargins(10, 8, 10, 4)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtriraj po naslovu…")
        self._filter.setClearButtonEnabled(True)
        self._filter.addAction(icon("search", c["text_faint"]), QLineEdit.ActionPosition.LeadingPosition)
        self._filter.textChanged.connect(self._apply_filter)
        self._fav_btn = QToolButton()
        self._fav_btn.setCheckable(True)
        self._fav_btn.setIcon(icon("star", c["icon"]))
        self._fav_btn.setToolTip("Prikaži samo omiljene lekcije")
        self._fav_btn.toggled.connect(self._on_favorites_only)
        f.addWidget(self._filter, 1)
        f.addWidget(self._fav_btn)
        root.addWidget(filter_box)

        self._tree = QTreeWidget()
        self._tree.setObjectName("CourseTree")
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setIndentation(14)
        self._tree.setUniformRowHeights(True)
        self._tree.setFrameShape(QFrame.Shape.NoFrame)
        self._tree.setMouseTracking(True)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemActivated.connect(self._on_item_clicked)
        root.addWidget(self._tree, 1)

        legend = QLabel("Klikni lekciju da je otvoriš. Sivo = u pripremi.")
        legend.setObjectName("Faint")
        legend.setWordWrap(True)
        legend.setContentsMargins(12, 6, 12, 8)
        root.addWidget(legend)

        self._build_tree()

    # ------------------------------------------------------------------ izgradnja
    def _build_tree(self) -> None:
        self._tree.clear()
        bold = QFont()
        bold.setWeight(QFont.Weight.DemiBold)
        for module in self._lessons.modules:
            m_item = QTreeWidgetItem([f"{module.number}. {module.title}"])
            m_item.setData(0, ROLE_MODULE_ID, module.module_id)
            m_item.setFont(0, bold)
            m_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._tree.addTopLevelItem(m_item)
            for info in module.lessons:
                l_item = QTreeWidgetItem([f"{info.number}. {info.title}"])
                l_item.setData(0, ROLE_LESSON_ID, info.lesson_id)
                l_item.setData(0, ROLE_TITLE, fold(f"{info.number}. {info.title}"))
                m_item.addChild(l_item)

    def refresh(self, current_id: str | None = None) -> None:
        """Osvežava stanja lekcija (posle provere, označavanja, promene lekcije)."""
        if current_id is not None:
            self._current_id = current_id
        c = current_theme().colors
        faint = QBrush(QColor(c["text_faint"]))
        normal = QBrush(QColor(c["text"]))
        current_bg = QBrush(QColor(c["accent_soft"]))
        clear_bg = QBrush(Qt.GlobalColor.transparent)

        favorites = set(self._progress.favorite_ids())
        completed_total = 0
        available_total = 0
        for m_index in range(self._tree.topLevelItemCount()):
            m_item = self._tree.topLevelItem(m_index)
            module = self._lessons.module(m_item.data(0, ROLE_MODULE_ID))
            done = 0
            available = 0
            for l_index in range(m_item.childCount()):
                l_item = m_item.child(l_index)
                info = self._lessons.info(l_item.data(0, ROLE_LESSON_ID))
                state = lesson_state(info, self._progress)
                icon_name, color_key = _STATE_ICON[state]
                is_current = info.lesson_id == self._current_id
                if is_current:
                    icon_name, color_key = "play-circle", "accent"
                l_item.setIcon(0, icon(icon_name, c[color_key]))
                l_item.setForeground(0, faint if state is LessonState.LOCKED else normal)
                l_item.setBackground(0, current_bg if is_current else clear_bg)
                font = l_item.font(0)
                font.setWeight(QFont.Weight.DemiBold if is_current else QFont.Weight.Normal)
                l_item.setFont(0, font)
                tip = state.label if not is_current else f"Trenutna lekcija · {state.label}"
                is_favorite = info.lesson_id in favorites
                l_item.setData(0, ROLE_FAVORITE, is_favorite)
                l_item.setText(0, f"{info.number}. {info.title}" + ("  ★" if is_favorite else ""))
                l_item.setToolTip(0, f"{info.title}\n{tip}" + ("\nOmiljena lekcija" if is_favorite else ""))
                if state is not LessonState.LOCKED:
                    available += 1
                if state is LessonState.COMPLETED:
                    done += 1
                if is_current:
                    m_item.setExpanded(True)
            completed_total += done
            available_total += available
            if available:
                m_item.setText(0, f"{module.number}. {module.title}  ·  {done}/{available}")
                m_item.setForeground(0, normal)
                if available and done == available:
                    m_item.setIcon(0, icon("check-circle", c["success"]))
                else:
                    m_item.setIcon(0, icon("layers", c["icon"]))
            else:
                m_item.setText(0, f"{module.number}. {module.title}")
                m_item.setForeground(0, faint)
                m_item.setIcon(0, icon("lock", c["text_faint"]))
                m_item.setToolTip(0, "Lekcije ovog modula su u pripremi.")
        self._summary.setText(f"{completed_total}/{available_total}")
        self._summary.setToolTip(f"Završeno {completed_total} od {available_total} dostupnih lekcija")
        self._apply_filter(self._filter.text())
        self.scroll_to_current()

    def scroll_to_current(self) -> None:
        item = self._find_item(self._current_id)
        if item is not None:
            self._tree.scrollToItem(item)

    def _find_item(self, lesson_id: str | None) -> QTreeWidgetItem | None:
        if lesson_id is None:
            return None
        iterator = QTreeWidgetItemIterator(self._tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, ROLE_LESSON_ID) == lesson_id:
                return item
            iterator += 1
        return None

    # ------------------------------------------------------------------ događaji
    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        lesson_id = item.data(0, ROLE_LESSON_ID)
        if lesson_id is None:
            item.setExpanded(not item.isExpanded())
            return
        if self._lessons.has_lesson(lesson_id):
            self.lesson_activated.emit(lesson_id)

    def _on_favorites_only(self, checked: bool) -> None:
        self._favorites_only = checked
        self._apply_filter(self._filter.text())

    def _apply_filter(self, text: str | None = None) -> None:
        """Filtrira stablo po naslovu (bez obzira na kvačice) i/ili samo na omiljene lekcije."""
        needle = fold((text if text is not None else self._filter.text()).strip())
        active = bool(needle) or self._favorites_only
        for m_index in range(self._tree.topLevelItemCount()):
            m_item = self._tree.topLevelItem(m_index)
            module_match = bool(needle) and needle in fold(m_item.text(0))
            any_visible = False
            for l_index in range(m_item.childCount()):
                l_item = m_item.child(l_index)
                visible = not needle or module_match or needle in (l_item.data(0, ROLE_TITLE) or "")
                if self._favorites_only and not l_item.data(0, ROLE_FAVORITE):
                    visible = False
                l_item.setHidden(not visible)
                any_visible = any_visible or visible
            m_item.setHidden(active and not any_visible)
            if active and any_visible:
                m_item.setExpanded(True)

    def focus_filter(self) -> None:
        self._filter.setFocus()
        self._filter.selectAll()
