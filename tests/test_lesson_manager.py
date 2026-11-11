# pyqt6_learning_studio/tests/test_lesson_manager.py
"""Testovi za učitavanje plana kursa, lekcija i navigaciju."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import COURSE_FILE
from core.lesson_manager import LessonLoadError, LessonManager


@pytest.fixture
def manager() -> LessonManager:
    return LessonManager(COURSE_FILE)


def test_course_plan_has_78_lessons_in_10_modules(manager):
    assert len(manager.modules) == 10
    assert len(manager.all_lessons) == 78
    assert [info.number for info in manager.all_lessons] == list(range(1, 79))


def test_all_available_lessons_are_valid(manager):
    assert manager.validate_all() == []
    assert len(manager.available_lessons) >= 5


def test_every_lesson_has_all_required_parts(manager):
    for info in manager.available_lessons:
        lesson = manager.load(info.lesson_id)
        assert lesson.goal
        assert lesson.explanation
        assert lesson.terms
        assert lesson.example_code.strip()
        assert lesson.example_steps
        assert lesson.exercise.description
        assert lesson.exercise.hints
        assert lesson.exercise.solution.strip()
        assert lesson.exercise.criteria.describe()
        assert len(lesson.quiz) >= 3


def test_navigation(manager):
    first = manager.first_lesson_id()
    assert first == "m01_l01"
    assert manager.previous_id(first) is None
    second = manager.next_id(first)
    assert second == "m01_l02"
    assert manager.previous_id(second) == first
    last = manager.available_lessons[-1].lesson_id
    assert manager.next_id(last) is None


def test_unavailable_lesson_cannot_be_loaded(manager):
    future = next(info for info in manager.all_lessons if not info.available)
    with pytest.raises(LessonLoadError):
        manager.load(future.lesson_id)


def test_lesson_cache(manager):
    assert manager.load("m01_l01") is manager.load("m01_l01")


def test_invalid_json_gives_clear_error(tmp_path: Path):
    (tmp_path / "course.json").write_text("{ nije json", encoding="utf-8")
    with pytest.raises(LessonLoadError, match="Neispravan JSON"):
        LessonManager(tmp_path / "course.json")


def test_new_lessons_are_added_by_data_only(tmp_path: Path):
    """Kurs se proširuje samo dodavanjem JSON fajlova — bez izmene koda."""
    lesson = json.loads((COURSE_FILE.parent / "modul_01" / "lekcija_01.json").read_text("utf-8"))
    lesson["id"] = "x_l01"
    (tmp_path / "l1.json").write_text(json.dumps(lesson), encoding="utf-8")
    course = {"title": "Test", "modules": [
        {"id": "x", "title": "Probni modul", "lessons": [
            {"id": "x_l01", "title": "Probna", "file": "l1.json"},
            {"id": "x_l02", "title": "U pripremi"},
        ]},
    ]}
    (tmp_path / "course.json").write_text(json.dumps(course), encoding="utf-8")
    manager = LessonManager(tmp_path / "course.json")
    assert manager.load("x_l01").title == "Probna"
    assert len(manager.available_lessons) == 1
