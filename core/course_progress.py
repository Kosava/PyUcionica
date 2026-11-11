# pyqt6_learning_studio/core/course_progress.py
"""Pregled napretka kroz kurs i preporuka sledeće lekcije.

Spaja plan kursa (:class:`~core.lesson_manager.LessonManager`) i napredak
korisnika (:class:`~core.progress_manager.ProgressManager`) u podatke koje
prikazuju početna strana i pregled kursa. Bez Qt-a, pa se lako testira.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.lesson_manager import LessonManager
from core.progress_manager import ProgressManager
from models.lesson import LessonInfo, Module


class LessonState(str, Enum):
    """Stanje lekcije iz ugla korisnika."""

    LOCKED = "locked"          # Sadržaj još nije napisan (u pripremi).
    NOT_STARTED = "not_started"
    SOLVED = "solved"          # Zadatak rešen, lekcija nije označena kao završena.
    COMPLETED = "completed"

    @property
    def label(self) -> str:
        return {
            LessonState.LOCKED: "U pripremi",
            LessonState.NOT_STARTED: "Nije započeta",
            LessonState.SOLVED: "Zadatak rešen",
            LessonState.COMPLETED: "Završena",
        }[self]


@dataclass(frozen=True)
class ModuleStats:
    """Napredak kroz jedan modul."""

    module: Module
    total: int
    available: int
    completed: int

    @property
    def is_available(self) -> bool:
        return self.available > 0

    @property
    def is_done(self) -> bool:
        return self.available > 0 and self.completed >= self.available

    @property
    def percent(self) -> int:
        return round(100 * self.completed / self.available) if self.available else 0


@dataclass(frozen=True)
class CourseOverview:
    """Sve što je potrebno za početnu stranu.

    Attributes:
        total: Broj lekcija u celom planu kursa.
        available: Broj lekcija koje imaju sadržaj.
        completed: Završene lekcije (među dostupnim).
        solved: Lekcije sa rešenim zadatkom (među dostupnim).
        quizzes_passed: Lekcije sa položenim kvizom (među dostupnim).
        percent: Procenat završenosti celog kursa.
        current: Poslednja otvorena lekcija, ili ``None``.
        recommended: Preporučena sledeća lekcija, ili ``None`` ako je sve završeno.
        modules: Napredak po modulima.
        favorites: Omiljene lekcije (samo dostupne), redom kojim su dodate.
    """

    total: int
    available: int
    completed: int
    solved: int
    quizzes_passed: int
    percent: int
    current: LessonInfo | None
    recommended: LessonInfo | None
    modules: tuple[ModuleStats, ...]
    favorites: tuple[LessonInfo, ...] = ()

    @property
    def started(self) -> bool:
        return self.current is not None or self.completed > 0

    @property
    def all_available_done(self) -> bool:
        return self.available > 0 and self.completed >= self.available


def lesson_state(info: LessonInfo, progress: ProgressManager) -> LessonState:
    if not info.available:
        return LessonState.LOCKED
    if progress.is_completed(info.lesson_id):
        return LessonState.COMPLETED
    if progress.is_solved(info.lesson_id):
        return LessonState.SOLVED
    return LessonState.NOT_STARTED


def recommend_next(lessons: LessonManager, progress: ProgressManager) -> str | None:
    """Preporučuje lekciju na kojoj korisnik treba da nastavi.

    Pravila, redom:
    1. Trenutna lekcija, ako postoji i nije završena.
    2. Prva nezavršena dostupna lekcija posle trenutne.
    3. Prva nezavršena dostupna lekcija od početka kursa.
    4. ``None`` — sve dostupne lekcije su završene.
    """
    available = [info.lesson_id for info in lessons.available_lessons]
    done = progress.completed_ids()
    current = progress.current_lesson_id
    if current in available and current not in done:
        return current
    start = available.index(current) + 1 if current in available else 0
    for lesson_id in available[start:] + available[:start]:
        if lesson_id not in done:
            return lesson_id
    return None


def module_entry_lesson(lessons: LessonManager, progress: ProgressManager, module_id: str) -> str | None:
    """Lekcija kojom se ulazi u modul: prva nezavršena, ili prva dostupna ako je modul završen."""
    infos = [info for info in lessons.module(module_id).lessons if info.available]
    for info in infos:
        if not progress.is_completed(info.lesson_id):
            return info.lesson_id
    return infos[0].lesson_id if infos else None


def build_overview(lessons: LessonManager, progress: ProgressManager) -> CourseOverview:
    available_ids = [info.lesson_id for info in lessons.available_lessons]
    done = progress.completed_ids()
    solved = progress.solved_ids()
    modules = tuple(
        ModuleStats(
            module=module,
            total=len(module.lessons),
            available=sum(1 for info in module.lessons if info.available),
            completed=sum(1 for info in module.lessons if info.available and info.lesson_id in done),
        )
        for module in lessons.modules
    )
    completed = len(done.intersection(available_ids))
    total = len(lessons.all_lessons)
    current_id = progress.current_lesson_id
    recommended_id = recommend_next(lessons, progress)
    return CourseOverview(
        total=total,
        available=len(available_ids),
        completed=completed,
        solved=len(solved.intersection(available_ids)),
        quizzes_passed=len(progress.passed_quiz_ids().intersection(available_ids)),
        percent=round(100 * completed / total) if total else 0,
        current=lessons.info(current_id) if current_id and lessons.has_lesson(current_id) else None,
        recommended=lessons.info(recommended_id) if recommended_id else None,
        modules=modules,
        favorites=tuple(lessons.info(lid) for lid in progress.favorite_ids() if lessons.has_lesson(lid)),
    )
