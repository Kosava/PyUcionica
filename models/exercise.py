# pyqt6_learning_studio/models/exercise.py
"""Modeli podataka za zadatke (vežbe) i kriterijume po kojima se oni proveravaju.

Zadatak se nikada ne smatra uspešnim samo zato što se kod izvršio bez greške —
uvek postoje eksplicitni kriterijumi (očekivani izlaz, obavezni delovi koda...).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ExerciseType(str, Enum):
    """Vrste zadataka u editoru koda.

    Zadaci „Predvidi rezultat“ i „Izaberi tačan odgovor“ nisu ovde: to su
    vrste kviz pitanja (``models/quiz.py``), uz mogućnost pokretanja koda.
    """

    WRITE = "write"            # Napiši program prema opisu.
    COMPLETE = "complete"      # Dopuni nedostajući deo koda.
    FIX = "fix"                # Ispravi postojeći kod / pronađi grešku.
    APP = "app"                # Napravi malu aplikaciju.

    @property
    def label(self) -> str:
        """Naziv vrste zadatka za prikaz u interfejsu."""
        return {
            ExerciseType.WRITE: "Napiši program",
            ExerciseType.COMPLETE: "Dopuni kod",
            ExerciseType.FIX: "Pronađi i ispravi grešku",
            ExerciseType.APP: "Napravi malu aplikaciju",
        }[self]


@dataclass(frozen=True)
class CodeRule:
    """Pravilo nad izvornim kodom (npr. „kod mora da sadrži print(“).

    Attributes:
        pattern: Tekst ili regularni izraz koji se traži.
        message: Objašnjenje za korisnika šta pravilo proverava.
        regex: Da li je ``pattern`` regularni izraz.
        min_count: Koliko puta se obrazac mora pojaviti (podrazumevano 1).
        ignore_comments: Da li se komentari uklanjaju pre provere.
    """

    pattern: str
    message: str
    regex: bool = False
    min_count: int = 1
    ignore_comments: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodeRule":
        return cls(
            pattern=str(data["pattern"]),
            message=str(data.get("message", data["pattern"])),
            regex=bool(data.get("regex", False)),
            min_count=int(data.get("min_count", 1)),
            ignore_comments=bool(data.get("ignore_comments", True)),
        )


def _short(text: str, limit: int = 40) -> str:
    text = " / ".join(part for part in text.strip().split("\n"))
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class TestCase:
    """Jedno pokretanje programa tokom provere: unos i očekivanja za izlaz.

    Zadaci koji čitaju unos (input) proveravaju se sa više različitih unosa,
    da program koji samo ispiše „tačan“ tekst ne bi prošao proveru.

    Attributes:
        stdin: Unos koji se šalje programu (redovi odvojeni sa \\n).
        expected_output: Tačan očekivani izlaz, ili ``None``.
        output_contains: Delovi teksta koji moraju postojati u izlazu.
        output_not_contains: Delovi teksta koji NE smeju postojati u izlazu.
        output_line_count: Tačan broj nepraznih redova izlaza, ili ``None``.
        name: Opcioni opis slučaja (npr. „deljenje nulom“).
        test_code: Kod koji aplikacija dodaje POSLE korisnikovog koda pri
            proveri — npr. poziv korisnikove funkcije sa određenim argumentima.
            Tako se proveravaju funkcije, a ne samo ono što program ispiše.
        gui_script: Provera PyQt6 programa: program radi bez prikaza na ekranu,
            a umesto ``app.exec()`` izvršava se ova skripta. Skripta ima pristup
            promenljivama programa i pomoćnim funkcijama ``glavni()``,
            ``nadji(tip, sadrzi)``, ``sve(tip)``, ``tekst(w)``, ``klikni(dugme)``,
            ``upisi(polje, tekst)`` i ``osvezi()``; ono što ispiše proverava se
            kao i običan izlaz.
    """

    __test__ = False  # Nije pytest test (samo se tako zove).

    stdin: str = ""
    expected_output: str | None = None
    output_contains: tuple[str, ...] = ()
    output_not_contains: tuple[str, ...] = ()
    output_line_count: int | None = None
    name: str = ""
    test_code: str = ""
    gui_script: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestCase":
        return cls(
            stdin=str(data.get("stdin", "")),
            expected_output=data.get("expected_output"),
            output_contains=tuple(str(x) for x in data.get("output_contains", [])),
            output_not_contains=tuple(str(x) for x in data.get("output_not_contains", [])),
            output_line_count=data.get("output_line_count"),
            name=str(data.get("name", "")),
            test_code=str(data.get("test_code", "")),
            gui_script=str(data.get("gui_script", "")),
        )

    @property
    def test_label(self) -> str:
        """Prvi red test koda, za prikaz (npr. „print(saberi(2, 3))“)."""
        first = next((line.strip() for line in self.test_code.splitlines() if line.strip()), "")
        return _short(first, 48)

    def program_for(self, user_code: str) -> str:
        """Program koji se zaista pokreće za ovaj slučaj."""
        if not self.test_code.strip():
            return user_code
        return user_code.rstrip("\n") + "\n\n" + self.test_code.rstrip("\n") + "\n"

    @property
    def input_label(self) -> str:
        """Kratak prikaz unosa za korisnika, npr. „5 / + / 3“."""
        return _short(self.stdin) if self.stdin.strip() else ""

    def describe(self) -> str:
        """Jedna rečenica koja opisuje šta se u ovom slučaju očekuje."""
        parts: list[str] = []
        if self.expected_output is not None:
            parts.append("izlaz mora tačno da odgovara očekivanom")
        if self.output_contains:
            parts.append("izlaz sadrži " + ", ".join(f"„{t}“" for t in self.output_contains))
        if self.output_not_contains:
            parts.append("izlaz ne sadrži " + ", ".join(f"„{t}“" for t in self.output_not_contains))
        if self.output_line_count is not None:
            parts.append(f"tačno {self.output_line_count} red(a) izlaza")
        what = "; ".join(parts) if parts else "program radi bez greške"
        if self.gui_script:
            prefix = f"Provera prozora{f' ({self.name})' if self.name else ''}"
            return f"{prefix} → {what}."
        if self.test_label:
            prefix = f"Test {self.test_label}"
        else:
            prefix = f"Unos {self.input_label}" if self.input_label else "Bez unosa"
        if self.name:
            prefix += f" ({self.name})"
        return f"{prefix} → {what}."


@dataclass(frozen=True)
class CheckCriteria:
    """Skup kriterijuma za automatsku proveru zadatka.

    Svi navedeni kriterijumi moraju biti ispunjeni da bi zadatak bio tačan.

    Attributes:
        expected_output: Tačan očekivani izlaz (poredi se bez razmaka na
            krajevima redova i praznih redova na kraju). ``None`` = ne proverava se.
        output_contains: Delovi teksta koji moraju postojati u izlazu.
        output_line_count: Tačan broj (nepraznih) redova izlaza, ili ``None``.
        code_contains: Pravila koja kod mora da ispuni.
        code_not_contains: Pravila koja kod NE sme da ispuni.
        min_comment_lines: Najmanji broj komentara (# ...) u kodu.
        stdin: Tekst koji se šalje programu kao unos tokom provere.
        must_succeed: Da li program mora da se završi bez greške.
        case_sensitive: Da li je poređenje izlaza osetljivo na velika/mala slova.
        cases: Više pokretanja sa različitim unosom. Ako su zadati, polja za
            izlaz iznad (expected_output, output_contains, output_line_count,
            stdin) se ne koriste — svaki slučaj nosi svoja očekivanja.
    """

    expected_output: str | None = None
    output_contains: tuple[str, ...] = ()
    output_line_count: int | None = None
    code_contains: tuple[CodeRule, ...] = ()
    code_not_contains: tuple[CodeRule, ...] = ()
    min_comment_lines: int = 0
    stdin: str = ""
    must_succeed: bool = True
    case_sensitive: bool = True
    cases: tuple[TestCase, ...] = ()

    def effective_cases(self) -> tuple[TestCase, ...]:
        """Slučajevi koji se zaista pokreću (bar jedan)."""
        if self.cases:
            return self.cases
        return (TestCase(
            stdin=self.stdin,
            expected_output=self.expected_output,
            output_contains=self.output_contains,
            output_line_count=self.output_line_count,
        ),)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CheckCriteria":
        data = data or {}
        return cls(
            expected_output=data.get("expected_output"),
            output_contains=tuple(str(x) for x in data.get("output_contains", [])),
            output_line_count=data.get("output_line_count"),
            code_contains=tuple(CodeRule.from_dict(r) for r in data.get("code_contains", [])),
            code_not_contains=tuple(
                CodeRule.from_dict(r) for r in data.get("code_not_contains", [])
            ),
            min_comment_lines=int(data.get("min_comment_lines", 0)),
            stdin=str(data.get("stdin", "")),
            must_succeed=bool(data.get("must_succeed", True)),
            case_sensitive=bool(data.get("case_sensitive", True)),
            cases=tuple(TestCase.from_dict(c) for c in data.get("cases", [])),
        )

    def describe(self) -> list[str]:
        """Vraća listu čitljivih opisa kriterijuma (za prikaz u lekciji)."""
        items: list[str] = []
        if self.must_succeed:
            items.append("Program mora da se izvrši bez greške.")
        if self.expected_output is not None:
            items.append("Izlaz mora tačno da odgovara očekivanom rezultatu.")
        for text in self.output_contains:
            items.append(f"U izlazu mora da se pojavi: „{text}“.")
        if self.output_line_count is not None:
            items.append(f"Program mora da ispiše tačno {self.output_line_count} red(a).")
        for rule in self.code_contains:
            items.append(rule.message)
        for rule in self.code_not_contains:
            items.append(rule.message)
        if self.min_comment_lines:
            items.append(f"Kod mora imati najmanje {self.min_comment_lines} komentar(a).")
        if self.cases:
            times = "jednom" if len(self.cases) == 1 else f"{len(self.cases)} puta"
            items.append(f"Program se pokreće {times}, sa različitim unosom:")
            items.extend("    " + case.describe() for case in self.cases)
        return items


@dataclass(frozen=True)
class Exercise:
    """Zadatak koji korisnik rešava u editoru.

    Attributes:
        type: Vrsta zadatka.
        description: Tekst zadatka (podržava jednostavno formatiranje lekcije).
        starter_code: Početni kod koji se učitava u editor.
        criteria: Kriterijumi provere.
        hints: Nagoveštaji, od najblažeg ka najkonkretnijem.
        solution: Kompletno rešenje (prikazuje se samo na zahtev).
        expected_output_preview: Opcioni prikaz očekivanog izlaza u lekciji.
    """

    type: ExerciseType
    description: str
    starter_code: str
    criteria: CheckCriteria
    hints: tuple[str, ...] = ()
    solution: str = ""
    expected_output_preview: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Exercise":
        return cls(
            type=ExerciseType(data.get("type", "write")),
            description=str(data.get("description", "")),
            starter_code=str(data.get("starter_code", "")),
            criteria=CheckCriteria.from_dict(data.get("criteria")),
            hints=tuple(str(h) for h in data.get("hints", [])),
            solution=str(data.get("solution", "")),
            expected_output_preview=data.get("expected_output_preview"),
        )
