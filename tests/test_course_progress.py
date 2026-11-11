# pyqt6_learning_studio/tests/test_course_progress.py
"""Testovi za pregled napretka i preporuku sledeće lekcije."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import COURSE_FILE
from core.course_progress import LessonState, build_overview, lesson_state, module_entry_lesson, recommend_next
from core.lesson_manager import LessonManager
from core.progress_manager import ProgressManager
from database.database_manager import DatabaseManager


def _first_unavailable_module(lessons: LessonManager):
    """Prvi modul bez ijedne dostupne lekcije (kurs se puni postepeno)."""
    for module in lessons.modules:
        if not any(info.file for info in module.lessons):
            return module
    pytest.skip("svi moduli već imaju lekcije")


@pytest.fixture
def lessons() -> LessonManager:
    return LessonManager(COURSE_FILE)


@pytest.fixture
def progress(tmp_path: Path):
    with DatabaseManager(tmp_path / "t.db") as db:
        yield ProgressManager(db)


def test_new_user_starts_with_first_lesson(lessons, progress):
    assert recommend_next(lessons, progress) == "m01_l01"
    overview = build_overview(lessons, progress)
    assert not overview.started
    assert overview.percent == 0
    assert overview.available == len(lessons.available_lessons) >= 18


def test_unfinished_current_lesson_is_recommended(lessons, progress):
    progress.set_completed("m01_l01")
    progress.set_current_lesson("m01_l04")
    assert recommend_next(lessons, progress) == "m01_l04"


def test_after_finished_current_next_unfinished_is_recommended(lessons, progress):
    for lid in ("m01_l01", "m01_l02", "m01_l03"):
        progress.set_completed(lid)
    progress.set_current_lesson("m01_l02")
    assert recommend_next(lessons, progress) == "m01_l04"


def test_wraps_around_to_skipped_lessons(lessons, progress):
    available = [i.lesson_id for i in lessons.available_lessons]
    for lid in available:
        if lid != "m01_l02":
            progress.set_completed(lid)
    progress.set_current_lesson(available[-1])
    assert recommend_next(lessons, progress) == "m01_l02"


def test_all_done_returns_none(lessons, progress):
    for info in lessons.available_lessons:
        progress.set_completed(info.lesson_id)
    assert recommend_next(lessons, progress) is None
    assert build_overview(lessons, progress).all_available_done


def test_overview_percent_is_of_whole_course(lessons, progress):
    for lid in ("m01_l01", "m01_l02", "m01_l03"):
        progress.set_completed(lid)
    overview = build_overview(lessons, progress)
    assert overview.completed == 3
    assert overview.percent == round(100 * 3 / 78)
    m1 = overview.modules[0]
    assert (m1.completed, m1.available, m1.total) == (3, 5, 5)
    locked = _first_unavailable_module(lessons)
    assert not overview.modules[locked.number - 1].is_available


def test_lesson_states(lessons, progress):
    progress.record_attempt("m01_l02", solved=True)
    progress.set_completed("m01_l03")
    assert lesson_state(lessons.info("m01_l01"), progress) is LessonState.NOT_STARTED
    assert lesson_state(lessons.info("m01_l02"), progress) is LessonState.SOLVED
    assert lesson_state(lessons.info("m01_l03"), progress) is LessonState.COMPLETED
    locked = _first_unavailable_module(lessons)
    assert lesson_state(locked.lessons[0], progress) is LessonState.LOCKED


def test_module_entry_lesson(lessons, progress):
    assert module_entry_lesson(lessons, progress, "m02") == "m02_l01"
    progress.set_completed("m02_l01")
    assert module_entry_lesson(lessons, progress, "m02") == "m02_l02"
    assert module_entry_lesson(lessons, progress, _first_unavailable_module(lessons).module_id) is None
