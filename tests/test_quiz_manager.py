# pyqt6_learning_studio/tests/test_quiz_manager.py
"""Testovi za kviz: vrste pitanja, mešanje odgovora, bodovanje i čuvanje rezultata."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from core.progress_manager import ProgressManager
from database.database_manager import DatabaseManager
from core.quiz_manager import QuizSession, required_to_pass
from models.quiz import QuestionKind, QuizQuestion, normalize_answer_text


def _choice(correct: int = 1) -> QuizQuestion:
    return QuizQuestion("Pitanje?", ("a", "b", "c"), correct, "jer")


def _output() -> QuizQuestion:
    return QuizQuestion("Šta ispisuje?", kind=QuestionKind.OUTPUT, code="print(1)\nprint(2)\n", answer_text="1\n2")


def test_required_to_pass():
    assert required_to_pass(3) == 3
    assert required_to_pass(4) == 3
    assert required_to_pass(5) == 4
    assert required_to_pass(10) == 7


def test_shuffle_keeps_correct_answer():
    for seed in range(20):
        session = QuizSession([_choice(2)], rng=random.Random(seed))
        presented = session.current
        assert presented.options[presented.correct_display_index] == "c"
        result = session.answer(presented.correct_display_index)
        assert result.correct


def test_wrong_answer_and_score():
    session = QuizSession([_choice(0), _choice(0)], shuffle_options=False)
    assert session.answer(0).correct
    assert session.next()
    result = session.answer(2)
    assert not result.correct
    assert result.correct_text == "a"
    assert not session.next()
    assert session.finished and session.score == 1 and not session.passed


def test_cannot_answer_twice():
    session = QuizSession([_choice()], shuffle_options=False)
    session.answer(1)
    with pytest.raises(RuntimeError):
        session.answer(1)


def test_output_question_normalizes_whitespace():
    q = _output()
    assert q.is_correct("1  \n2\n\n")
    assert not q.is_correct("1 2")
    assert not q.is_correct("1\n3")
    session = QuizSession([q])
    with pytest.raises(ValueError):
        session.answer("   ")
    assert session.answer("\n1\n2").correct


def test_normalize_answer_text_keeps_case():
    assert normalize_answer_text("Ana") != normalize_answer_text("ana")


def test_invalid_questions_rejected():
    with pytest.raises(ValueError):
        QuizQuestion("?", ("a",), 0)
    with pytest.raises(ValueError):
        QuizQuestion("?", ("a", "b"), 5)
    with pytest.raises(ValueError):
        QuizQuestion("?", kind=QuestionKind.OUTPUT, code="print(1)")
    with pytest.raises(ValueError):
        QuizQuestion("?", ("a", "b"), 0, kind=QuestionKind.PREDICT)


def test_from_dict_kinds():
    q = QuizQuestion.from_dict({"type": "predict", "question": "?", "code": "print(5)",
                                "options": ["5", "x"], "correct": 0})
    assert q.kind is QuestionKind.PREDICT and q.is_correct(0)
    q = QuizQuestion.from_dict({"type": "output", "question": "?", "code": "print(5)", "answer": "5"})
    assert q.kind is QuestionKind.OUTPUT and q.is_correct("5")


def test_quiz_results_persist(tmp_path: Path):
    pm = ProgressManager(DatabaseManager(tmp_path / "t.db"))
    pm.record_quiz("a", 2, 4, passed=False)
    record = pm.record_quiz("a", 4, 4, passed=True)
    assert (record.best, record.last, record.attempts, record.passed) == (4, 4, 2, True)
    pm.database.close()
    pm = ProgressManager(DatabaseManager(tmp_path / "t.db"))
    record = pm.record_quiz("a", 1, 4, passed=False)
    assert record.best == 4 and record.passed and record.last == 1
    assert pm.quiz_record("x") is None
    assert [h[0] for h in pm.quiz_history("a")] == [2, 4, 1]
