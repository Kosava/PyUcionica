# pyqt6_learning_studio/models/lesson.py
"""Modeli podataka za kurs: moduli, stavke plana kursa i kompletne lekcije.

Plan kursa (``course.json``) sadrži sve module i naslove lekcija. Lekcija čiji je
sadržaj napisan ima putanju do svog JSON fajla; ostale su označene kao „u pripremi“.
Tako se kurs proširuje samo dodavanjem JSON fajlova, bez izmene koda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.exercise import Exercise
from models.quiz import QuizQuestion


@dataclass(frozen=True)
class Term:
    """Novi pojam koji lekcija uvodi (npr. „funkcija“)."""

    term: str
    definition: str


@dataclass(frozen=True)
class CodeStep:
    """Deo primera koda sa objašnjenjem („kod deo po deo“)."""

    code: str
    explanation: str


@dataclass(frozen=True)
class LessonInfo:
    """Stavka plana kursa — naslov lekcije i (opciono) putanja do sadržaja.

    Attributes:
        lesson_id: Jedinstveni identifikator (npr. ``"m01_l01"``).
        number: Redni broj lekcije u celom kursu (1, 2, 3...).
        title: Naslov lekcije.
        module_id: Identifikator modula kome lekcija pripada.
        file: Relativna putanja do JSON fajla lekcije, ili ``None`` ako lekcija
            još nije napisana.
    """

    lesson_id: str
    number: int
    title: str
    module_id: str
    file: str | None = None

    @property
    def available(self) -> bool:
        """Da li lekcija ima napisan sadržaj."""
        return self.file is not None


@dataclass(frozen=True)
class Module:
    """Modul kursa (npr. „Modul 1 — Uvod u programiranje“)."""

    module_id: str
    number: int
    title: str
    lessons: tuple[LessonInfo, ...] = ()


@dataclass(frozen=True)
class Lesson:
    """Kompletna lekcija sa svim delovima koje zahteva nastavni plan.

    Attributes:
        info: Stavka plana kursa za ovu lekciju.
        module: Modul kome lekcija pripada.
        goal: Kratak cilj lekcije („Na kraju lekcije znaćeš da...“).
        explanation: Objašnjenje jednostavnim jezikom — lista pasusa.
        terms: Novi pojmovi.
        example_code: Primer koda.
        example_steps: Objašnjenje primera deo po deo.
        exercise: Zadatak.
        quiz: Kratak kviz.
    """

    info: LessonInfo
    module: Module
    goal: str
    explanation: tuple[str, ...]
    terms: tuple[Term, ...]
    example_code: str
    example_steps: tuple[CodeStep, ...]
    exercise: Exercise
    quiz: tuple[QuizQuestion, ...] = field(default_factory=tuple)

    @property
    def lesson_id(self) -> str:
        return self.info.lesson_id

    @property
    def number(self) -> int:
        return self.info.number

    @property
    def title(self) -> str:
        return self.info.title

    @classmethod
    def from_dict(cls, data: dict[str, Any], info: LessonInfo, module: Module) -> "Lesson":
        """Pravi lekciju iz rečnika učitanog iz JSON fajla.

        Raises:
            KeyError: Ako nedostaje obavezno polje.
            ValueError: Ako je neko polje neispravno.
        """
        if data.get("id") and data["id"] != info.lesson_id:
            raise ValueError(
                f"ID u fajlu lekcije ({data['id']}) ne odgovara planu kursa ({info.lesson_id})."
            )
        return cls(
            info=info,
            module=module,
            goal=str(data["goal"]),
            explanation=tuple(str(p) for p in data["explanation"]),
            terms=tuple(Term(str(t["term"]), str(t["definition"])) for t in data.get("terms", [])),
            example_code=str(data.get("example_code", "")),
            example_steps=tuple(
                CodeStep(str(s["code"]), str(s["explanation"]))
                for s in data.get("example_steps", [])
            ),
            exercise=Exercise.from_dict(data["exercise"]),
            quiz=tuple(QuizQuestion.from_dict(q) for q in data.get("quiz", [])),
        )
