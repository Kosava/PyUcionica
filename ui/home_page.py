# pyqt6_learning_studio/ui/home_page.py
"""Početna strana: ukupan napredak, poslednja lekcija, preporučena sledeća lekcija i pregled modula.

Strana samo prikazuje :class:`~core.course_progress.CourseOverview`; izbor lekcije
javlja signalom ``lesson_requested``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.course_progress import CourseOverview, ModuleStats
from ui.icons import icon, pixmap
from ui.theme import current_theme


def _label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


class _StatCard(QFrame):
    """Mala kartica sa brojem i opisom (npr. „42% — napredak kursa“)."""

    def __init__(self, icon_name: str, caption: str) -> None:
        super().__init__()
        self.setObjectName("HomeCard")
        c = current_theme().colors
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        badge = QLabel()
        badge.setObjectName("IconBadge")
        badge.setFixedSize(36, 36)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(pixmap(icon_name, c["accent"], 18))
        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        self.value = _label(name="StatValue")
        self.caption = _label(caption, "Muted")
        text_box.addWidget(self.value)
        text_box.addWidget(self.caption)
        layout.addWidget(badge)
        layout.addLayout(text_box, 1)


class _ModuleCard(QFrame):
    """Kartica jednog modula sa napretkom i dugmetom za ulazak."""

    def __init__(self, stats: ModuleStats, on_open) -> None:
        super().__init__()
        self.setObjectName("HomeCard")
        self.setProperty("locked", "false" if stats.is_available else "true")
        c = current_theme().colors
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        number = _label(f"MODUL {stats.module.number}", "ModuleLabel")
        top.addWidget(number)
        top.addStretch(1)
        if stats.is_done:
            done = QLabel()
            done.setPixmap(pixmap("check-circle", c["success"], 16))
            done.setToolTip("Svi dostupni delovi modula su završeni")
            top.addWidget(done)
        elif not stats.is_available:
            lock = QLabel()
            lock.setPixmap(pixmap("lock", c["text_faint"], 14))
            top.addWidget(lock)
        layout.addLayout(top)

        title = _label(stats.module.title, "ModuleCardTitle", wrap=True)
        layout.addWidget(title)

        if stats.is_available:
            detail = f"{stats.completed} od {stats.available} lekcija završeno"
            if stats.available < stats.total:
                detail += f" · još {stats.total - stats.available} u pripremi"
        else:
            detail = f"{stats.total} lekcija · u pripremi"
        layout.addWidget(_label(detail, "Muted", wrap=True))

        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setMaximum(max(1, stats.available))
        bar.setValue(stats.completed)
        bar.setEnabled(stats.is_available)
        layout.addWidget(bar)

        button = QPushButton()
        if not stats.is_available:
            button.setText("Uskoro")
            button.setEnabled(False)
        elif stats.is_done:
            button.setText("Ponovi modul")
        elif stats.completed:
            button.setText("Nastavi modul")
        else:
            button.setText("Započni modul")
        button.setIcon(icon("arrow-right", c["icon"], c["text_faint"]))
        button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        button.clicked.connect(lambda: on_open(stats.module.module_id))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        layout.addLayout(row)


class HomePage(QWidget):
    """Početna strana.

    Signals:
        lesson_requested(str): Otvori ovu lekciju.
        module_requested(str): Otvori modul (glavni prozor bira lekciju).
    """

    lesson_requested = pyqtSignal(str)
    module_requested = pyqtSignal(str)
    search_requested = pyqtSignal()

    def __init__(self, course_title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Central")
        self._overview: CourseOverview | None = None
        c = current_theme().colors

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("HomeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("HomeContent")
        scroll.setWidget(content)
        page = QHBoxLayout(content)
        page.setContentsMargins(24, 24, 24, 24)
        page.addStretch(1)
        column = QVBoxLayout()
        column.setSpacing(16)
        holder = QWidget()
        holder.setLayout(column)
        holder.setMaximumWidth(1100)
        holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        page.addWidget(holder, 100)
        page.addStretch(1)

        # --- naslov
        title_row = QHBoxLayout()
        title_row.addWidget(_label("Dobro došao u PyQt6 Learning Studio", "HomeTitle", wrap=True), 1)
        search_btn = QPushButton(icon("search", c["icon"]), "Pretraži lekcije")
        search_btn.setToolTip("Pretraži sadržaj svih lekcija (Ctrl+K)")
        search_btn.clicked.connect(self.search_requested)
        title_row.addWidget(search_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        column.addLayout(title_row)
        column.addWidget(_label(
            f"Kurs „{course_title}“ — od prvog print-a do sopstvenih desktop aplikacija. "
            "Čitaj lekciju, piši kod, pokreni ga i odmah vidi rezultat.", "Muted", wrap=True))

        # --- kartica „nastavi“
        self._continue_card = QFrame()
        self._continue_card.setObjectName("HeroCard")
        hero = QHBoxLayout(self._continue_card)
        hero.setContentsMargins(20, 18, 20, 18)
        hero.setSpacing(16)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(4)
        self._hero_kicker = _label(name="ModuleLabel")
        self._hero_title = _label(name="HeroTitle", wrap=True)
        self._hero_detail = _label(name="Muted", wrap=True)
        hero_text.addWidget(self._hero_kicker)
        hero_text.addWidget(self._hero_title)
        hero_text.addWidget(self._hero_detail)
        self._hero_button = QPushButton()
        self._hero_button.setObjectName("PrimaryButton")
        self._hero_button.setIcon(icon("play", c["accent_text"]))
        self._hero_button.setMinimumHeight(36)
        self._hero_button.clicked.connect(self._on_hero_clicked)
        self._hero_lesson_id: str | None = None
        hero.addLayout(hero_text, 1)
        hero.addWidget(self._hero_button, 0, Qt.AlignmentFlag.AlignVCenter)
        column.addWidget(self._continue_card)

        # --- statistika
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_percent = _StatCard("award", "napredak celog kursa")
        self._stat_lessons = _StatCard("check-circle", "završenih lekcija")
        self._stat_solved = _StatCard("clipboard-check", "rešenih zadataka")
        self._stat_quizzes = _StatCard("target", "položenih kvizova")
        for card in (self._stat_percent, self._stat_lessons, self._stat_solved, self._stat_quizzes):
            stats_row.addWidget(card, 1)
        column.addLayout(stats_row)

        self._course_bar = QProgressBar()
        self._course_bar.setTextVisible(False)
        column.addWidget(self._course_bar)

        # --- moduli
        self._fav_title = _label("Omiljene lekcije", "SectionTitle")
        column.addWidget(self._fav_title)
        self._fav_grid = QGridLayout()
        self._fav_grid.setHorizontalSpacing(8)
        self._fav_grid.setVerticalSpacing(8)
        column.addLayout(self._fav_grid)
        column.addWidget(_label("Moduli kursa", "SectionTitle"))
        self._modules_grid = QGridLayout()
        self._modules_grid.setHorizontalSpacing(12)
        self._modules_grid.setVerticalSpacing(12)
        column.addLayout(self._modules_grid)
        column.addStretch(1)

    # ------------------------------------------------------------------ prikaz
    def show_overview(self, overview: CourseOverview) -> None:
        self._overview = overview
        rec = overview.recommended
        cur = overview.current

        if overview.all_available_done:
            self._hero_kicker.setText("SVE DOSTUPNE LEKCIJE SU ZAVRŠENE")
            self._hero_title.setText("Odličan posao!")
            self._hero_detail.setText(
                "Završio si sve lekcije koje su trenutno dostupne. Nove lekcije stižu uskoro — "
                "do tada ponovi gradivo ili se vrati na zadatke koji su ti bili teški.")
            target = cur or (overview.modules[0].module.lessons[0] if overview.modules else None)
            self._set_hero_button("Ponovi poslednju lekciju", target.lesson_id if target else None)
        elif rec is not None and not overview.started:
            self._hero_kicker.setText("POČNI OVDE")
            self._hero_title.setText(f"{rec.number}. {rec.title}")
            self._hero_detail.setText(
                "Nije potrebno nikakvo predznanje. Svaka lekcija objašnjava nove pojmove pre nego "
                "što ih upotrebi, a zadatak na kraju proverava šta si naučio.")
            self._set_hero_button("Počni prvu lekciju", rec.lesson_id)
        elif rec is not None:
            same = cur is not None and cur.lesson_id == rec.lesson_id
            self._hero_kicker.setText("NASTAVI GDE SI STAO" if same else "PREPORUČENA SLEDEĆA LEKCIJA")
            self._hero_title.setText(f"{rec.number}. {rec.title}")
            if same:
                detail = "Ova lekcija još nije označena kao završena."
            elif cur is not None:
                detail = f"Poslednja otvorena lekcija: {cur.number}. {cur.title}."
            else:
                detail = "Sledeća lekcija koju još nisi završio."
            self._hero_detail.setText(detail)
            self._set_hero_button("Nastavi" if same else "Otvori lekciju", rec.lesson_id)

        self._stat_percent.value.setText(f"{overview.percent}%")
        self._stat_percent.caption.setText(f"napredak celog kursa ({overview.total} lekcija)")
        self._stat_lessons.value.setText(f"{overview.completed} / {overview.available}")
        self._stat_lessons.caption.setText("završenih od dostupnih lekcija")
        self._stat_solved.value.setText(str(overview.solved))
        self._stat_quizzes.value.setText(str(overview.quizzes_passed))
        self._course_bar.setMaximum(max(1, overview.total))
        self._course_bar.setValue(overview.completed)
        self._course_bar.setToolTip(f"Završeno {overview.completed} od {overview.total} lekcija kursa")

        _clear_layout(self._fav_grid)
        self._fav_title.setVisible(bool(overview.favorites))
        c = current_theme().colors
        for index, info in enumerate(overview.favorites):
            button = QPushButton(icon("star-filled", c["warning"]), f"{info.number}. {info.title}")
            button.setObjectName("FavoriteButton")
            button.setToolTip("Otvori omiljenu lekciju")
            button.clicked.connect(lambda _=False, lid=info.lesson_id: self.lesson_requested.emit(lid))
            self._fav_grid.addWidget(button, index // 3, index % 3)
        for col in range(3):
            self._fav_grid.setColumnStretch(col, 1)

        _clear_layout(self._modules_grid)
        columns = 3
        for index, stats in enumerate(overview.modules):
            card = _ModuleCard(stats, self.module_requested.emit)
            self._modules_grid.addWidget(card, index // columns, index % columns)
        for col in range(columns):
            self._modules_grid.setColumnStretch(col, 1)

    def _set_hero_button(self, text: str, lesson_id: str | None) -> None:
        self._hero_lesson_id = lesson_id
        self._hero_button.setText(text)
        self._hero_button.setEnabled(lesson_id is not None)

    def _on_hero_clicked(self) -> None:
        if self._hero_lesson_id:
            self.lesson_requested.emit(self._hero_lesson_id)
