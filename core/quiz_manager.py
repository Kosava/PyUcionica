# pyqt6_learning_studio/core/quiz_manager.py
"""Tok jednog kviza: redosled pitanja, mešanje ponuđenih odgovora, bodovanje.

Bez Qt-a, pa se lako testira. Interfejs (``ui/quiz_dialog.py``) samo prikazuje
trenutno pitanje i predaje korisnikov odgovor.

Ponuđeni odgovori se mešaju pri svakom pokušaju, da bi korisnik pamtio
odgovor, a ne njegovo mesto na listi.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from models.quiz import QuestionKind, QuizQuestion

PASS_RATIO = 0.7
"""Deo tačnih odgovora potreban za prolaz (70%)."""


def required_to_pass(total: int) -> int:
    """Koliko tačnih odgovora je potrebno za prolaz kviza sa ``total`` pitanja."""
    return max(1, math.ceil(total * PASS_RATIO)) if total else 0


@dataclass(frozen=True)
class PresentedQuestion:
    """Pitanje onako kako se prikazuje: sa (eventualno) promešanim odgovorima.

    Attributes:
        question: Originalno pitanje.
        options: Ponuđeni odgovori u redosledu prikaza.
        order: ``order[i]`` je indeks u originalnom pitanju za prikazani odgovor ``i``.
    """

    question: QuizQuestion
    options: tuple[str, ...]
    order: tuple[int, ...]

    @property
    def kind(self) -> QuestionKind:
        return self.question.kind

    @property
    def correct_display_index(self) -> int:
        """Indeks tačnog odgovora u prikazanom redosledu (ili -1)."""
        if not self.kind.has_options:
            return -1
        return self.order.index(self.question.correct_index)


@dataclass(frozen=True)
class AnswerResult:
    """Rezultat odgovora na jedno pitanje."""

    correct: bool
    correct_text: str
    explanation: str
    given_text: str


class QuizSession:
    """Jedan prolaz kroz kviz.

    Args:
        questions: Pitanja lekcije.
        shuffle_options: Da li da se mešaju ponuđeni odgovori.
        rng: Generator slučajnih brojeva (za ponovljive testove).
    """

    def __init__(self, questions: tuple[QuizQuestion, ...] | list[QuizQuestion],
                 shuffle_options: bool = True, rng: random.Random | None = None) -> None:
        if not questions:
            raise ValueError("Kviz mora imati bar jedno pitanje.")
        rng = rng or random.Random()
        presented: list[PresentedQuestion] = []
        for q in questions:
            order = list(range(len(q.options)))
            if shuffle_options and q.kind.has_options:
                rng.shuffle(order)
            presented.append(PresentedQuestion(q, tuple(q.options[i] for i in order), tuple(order)))
        self._questions = tuple(presented)
        self._index = 0
        self._results: list[AnswerResult | None] = [None] * len(presented)

    # ------------------------------------------------------------------ stanje
    @property
    def total(self) -> int:
        return len(self._questions)

    @property
    def index(self) -> int:
        """Indeks trenutnog pitanja (0..total-1)."""
        return self._index

    @property
    def current(self) -> PresentedQuestion:
        return self._questions[self._index]

    @property
    def questions(self) -> tuple[PresentedQuestion, ...]:
        return self._questions

    @property
    def results(self) -> tuple[AnswerResult | None, ...]:
        return tuple(self._results)

    def is_answered(self, index: int | None = None) -> bool:
        return self._results[self._index if index is None else index] is not None

    @property
    def is_last(self) -> bool:
        return self._index == self.total - 1

    @property
    def finished(self) -> bool:
        return all(r is not None for r in self._results)

    @property
    def score(self) -> int:
        return sum(1 for r in self._results if r is not None and r.correct)

    @property
    def required(self) -> int:
        return required_to_pass(self.total)

    @property
    def passed(self) -> bool:
        return self.finished and self.score >= self.required

    # ------------------------------------------------------------------ akcije
    def answer(self, answer: int | str) -> AnswerResult:
        """Odgovara na trenutno pitanje.

        Args:
            answer: Indeks izabranog odgovora u PRIKAZANOM redosledu, ili upisani tekst.

        Raises:
            RuntimeError: Ako je na pitanje već odgovoreno.
            ValueError: Ako odgovor nije odgovarajućeg oblika.
        """
        if self.is_answered():
            raise RuntimeError("Na ovo pitanje je već odgovoreno.")
        presented = self.current
        q = presented.question
        if q.kind.has_options:
            if not isinstance(answer, int) or not 0 <= answer < len(presented.options):
                raise ValueError("Izaberi jedan od ponuđenih odgovora.")
            correct = q.is_correct(presented.order[answer])
            given = presented.options[answer]
        else:
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Upiši odgovor.")
            correct = q.is_correct(answer)
            given = answer
        result = AnswerResult(correct, q.correct_text, q.explanation, given)
        self._results[self._index] = result
        return result

    def next(self) -> bool:
        """Prelazi na sledeće pitanje. Vraća ``False`` ako je ovo bilo poslednje."""
        if self._index + 1 >= self.total:
            return False
        self._index += 1
        return True
