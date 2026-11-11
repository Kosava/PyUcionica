# pyqt6_learning_studio/tests/test_quiz_content.py
"""Provera sadržaja kvizova: tačan odgovor na pitanja sa programom mora biti ono
što program ZAISTA ispisuje. Tako se greške u pitanjima otkrivaju automatski."""

from __future__ import annotations

import pytest

from config.settings import COURSE_FILE
from core.code_runner import RunStatus
from core.error_explainer import parse_traceback
from core.lesson_manager import LessonManager
from core.quiz_manager import required_to_pass
from models.quiz import QuestionKind, normalize_answer_text
from tests.conftest import run_code

_MANAGER = LessonManager(COURSE_FILE)
_CODE_QUESTIONS = [
    pytest.param(info.lesson_id, index, id=f"{info.lesson_id}-q{index + 1}")
    for info in _MANAGER.available_lessons
    for index, q in enumerate(_MANAGER.load(info.lesson_id).quiz)
    if q.kind is not QuestionKind.CHOICE
]


def _is_gui_lesson(lesson_id: str) -> bool:
    from core.code_runner import uses_pyqt

    return uses_pyqt(_MANAGER.load(lesson_id).exercise.solution)


def test_every_lesson_has_code_questions():
    """Konzolne lekcije imaju pitanja sa kodom; PyQt6 lekcije samo pitanja sa izborom
    (kod sa prozorom ne može da se pokrene u kvizu)."""
    for info in _MANAGER.available_lessons:
        kinds = {q.kind for q in _MANAGER.load(info.lesson_id).quiz}
        assert QuestionKind.CHOICE in kinds, info.lesson_id
        if not _is_gui_lesson(info.lesson_id):
            assert kinds & {QuestionKind.PREDICT, QuestionKind.OUTPUT}, info.lesson_id


def test_quiz_code_never_opens_windows():
    from core.code_runner import uses_pyqt

    for info in _MANAGER.available_lessons:
        for q in _MANAGER.load(info.lesson_id).quiz:
            assert not uses_pyqt(q.code), info.lesson_id


def test_quizzes_are_passable():
    for info in _MANAGER.available_lessons:
        total = len(_MANAGER.load(info.lesson_id).quiz)
        assert 4 <= total <= 8, info.lesson_id
        assert required_to_pass(total) < total or total <= 3


@pytest.mark.parametrize(("lesson_id", "index"), _CODE_QUESTIONS)
def test_correct_answer_matches_real_output(qt_app, lesson_id, index):
    q = _MANAGER.load(lesson_id).quiz[index]
    result = run_code(q.code)
    output = normalize_answer_text(result.stdout)
    if result.status is RunStatus.SUCCESS:
        assert output == normalize_answer_text(q.correct_text), (q.code, output)
        if q.kind is QuestionKind.PREDICT:
            wrong = [o for i, o in enumerate(q.options) if i != q.correct_index]
            assert output not in [normalize_answer_text(o) for o in wrong]
    else:
        # Program sa greškom: tačan odgovor mora pomenuti grešku i sve što je ispisano pre nje.
        assert q.kind is QuestionKind.PREDICT
        exc_type, _, _ = parse_traceback(result.stderr)
        assert exc_type and exc_type in q.correct_text, (exc_type, q.correct_text)
        for line in output.splitlines():
            assert line in q.correct_text
