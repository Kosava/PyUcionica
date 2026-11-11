# pyqt6_learning_studio/tests/test_quiz_dialog.py
"""Test toka kviz dijaloga (bez prikaza na ekranu): odgovori, bodovanje, ponavljanje."""

from __future__ import annotations

import random

from config.settings import COURSE_FILE
from core.lesson_manager import LessonManager
from models.quiz import QuestionKind


def _answer_all(dialog, wrong: set[int]) -> None:
    session = dialog._session
    for index in range(session.total):
        presented = session.current
        if presented.kind is QuestionKind.OUTPUT:
            text = "pogrešno" if index in wrong else presented.question.answer_text
            dialog._text_answer.setPlainText(text)
        else:
            target = presented.correct_display_index
            if index in wrong:
                target = (target + 1) % len(presented.options)
            dialog._option_group.button(target).setChecked(True)
            dialog._update_buttons()
        assert dialog._primary_btn.isEnabled()
        dialog._on_primary()          # Proveri odgovor
        assert session.is_answered()
        dialog._on_primary()          # Sledeće pitanje / Pogledaj rezultat


def test_quiz_dialog_scores_and_reports(qt_app):
    from ui.quiz_dialog import QuizDialog

    lesson = LessonManager(COURSE_FILE).load("m03_l04")
    reported: list[tuple[int, int, bool]] = []
    dialog = QuizDialog("Test", lesson.quiz, lambda *r: reported.append(r), rng=random.Random(3))
    _answer_all(dialog, wrong={1})
    total = len(lesson.quiz)
    assert reported == [(total - 1, total, True)]
    assert dialog._pages.currentIndex() == 1
    assert dialog.result_passed

    dialog.start()                    # Ponovi kviz
    _answer_all(dialog, wrong={0, 2})
    assert reported[-1] == (total - 2, total, False)
    dialog.done(0)


def test_check_button_disabled_without_answer(qt_app):
    from ui.quiz_dialog import QuizDialog

    lesson = LessonManager(COURSE_FILE).load("m01_l01")
    dialog = QuizDialog("Test", lesson.quiz, rng=random.Random(0))
    assert not dialog._primary_btn.isEnabled()
    dialog.done(0)
