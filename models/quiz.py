# pyqt6_learning_studio/models/quiz.py
"""Model kviz pitanja koje prati svaku lekciju.

Postoje tri vrste pitanja:

* ``choice``  — „Izaberi tačan odgovor“: pitanje i ponuđeni odgovori.
* ``predict`` — „Predvidi rezultat“: kratak program i ponuđeni mogući izlazi.
* ``output``  — „Upiši šta program ispisuje“: kratak program, a odgovor se kuca.

Kod pitanja ``predict`` i ``output`` korisnik posle odgovora može da pokrene
program i vidi stvarni rezultat.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class QuestionKind(str, Enum):
    """Vrsta kviz pitanja."""

    CHOICE = "choice"
    PREDICT = "predict"
    OUTPUT = "output"

    @property
    def label(self) -> str:
        return {
            QuestionKind.CHOICE: "Izaberi tačan odgovor",
            QuestionKind.PREDICT: "Predvidi rezultat",
            QuestionKind.OUTPUT: "Upiši šta program ispisuje",
        }[self]

    @property
    def has_options(self) -> bool:
        return self is not QuestionKind.OUTPUT


def normalize_answer_text(text: str) -> str:
    """Uklanja razlike koje nisu bitne pri poređenju upisanog izlaza.

    Zanemaruju se razmaci na krajevima redova i prazni redovi na početku i kraju.
    Velika i mala slova, razmaci unutar reda i interpunkcija SU bitni — kao i
    kod pravog izlaza programa.
    """
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines)


@dataclass(frozen=True)
class QuizQuestion:
    """Jedno kviz pitanje.

    Attributes:
        question: Tekst pitanja.
        kind: Vrsta pitanja.
        options: Ponuđeni odgovori (za ``choice`` i ``predict``).
        correct_index: Indeks tačnog odgovora u ``options`` (ili ``-1`` za ``output``).
        explanation: Objašnjenje zašto je odgovor tačan.
        code: Program uz pitanje (za ``predict`` i ``output``).
        answer_text: Tačan izlaz koji se upisuje (za ``output``).
    """

    question: str
    options: tuple[str, ...] = ()
    correct_index: int = -1
    explanation: str = ""
    kind: QuestionKind = QuestionKind.CHOICE
    code: str = ""
    answer_text: str = ""

    def __post_init__(self) -> None:
        if self.kind.has_options:
            if len(self.options) < 2:
                raise ValueError(f"Pitanje mora imati bar dva ponuđena odgovora: {self.question!r}")
            if not 0 <= self.correct_index < len(self.options):
                raise ValueError(
                    f"Indeks tačnog odgovora {self.correct_index} je van opsega "
                    f"za pitanje: {self.question!r}"
                )
        elif not normalize_answer_text(self.answer_text):
            raise ValueError(f"Pitanje tipa „output“ mora imati tačan odgovor: {self.question!r}")
        if self.kind is not QuestionKind.CHOICE and not self.code.strip():
            raise ValueError(f"Pitanje tipa „{self.kind.value}“ mora imati kod: {self.question!r}")

    @property
    def correct_text(self) -> str:
        """Tačan odgovor kao tekst (za prikaz)."""
        if self.kind.has_options:
            return self.options[self.correct_index]
        return normalize_answer_text(self.answer_text)

    def is_correct(self, answer: int | str) -> bool:
        """Da li je odgovor tačan.

        Args:
            answer: Indeks izabranog odgovora (``choice``/``predict``) ili
                upisani tekst (``output``).
        """
        if self.kind.has_options:
            return isinstance(answer, int) and answer == self.correct_index
        return isinstance(answer, str) and normalize_answer_text(answer) == normalize_answer_text(self.answer_text)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuizQuestion":
        kind = QuestionKind(data.get("type", "choice"))
        return cls(
            question=str(data["question"]),
            options=tuple(str(o) for o in data.get("options", [])),
            correct_index=int(data.get("correct", -1)),
            explanation=str(data.get("explanation", "")),
            kind=kind,
            code=str(data.get("code", "")),
            answer_text=str(data.get("answer", "")),
        )
