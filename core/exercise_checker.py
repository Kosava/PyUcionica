# pyqt6_learning_studio/core/exercise_checker.py
"""Provera rešenja zadataka prema unapred definisanim kriterijumima.

Provera je podeljena u dva koraka:

1. :class:`~core.code_runner.CodeRunner` izvrši kod (sa unapred zadatim
   unosom, ako ga zadatak zahteva).
2. :func:`evaluate` uporedi kod i rezultat izvršavanja sa kriterijumima.

Drugi korak je čista funkcija bez Qt-a, pa se lako testira. Zadatak se nikada
ne proglašava tačnim samo zato što se kod izvršio bez greške.
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Sequence
from dataclasses import dataclass, field

from core.code_runner import RunResult, RunStatus
from models.exercise import CheckCriteria, CodeRule, TestCase


@dataclass(frozen=True)
class CheckItem:
    """Rezultat jednog kriterijuma."""

    ok: bool
    message: str
    detail: str = ""


@dataclass(frozen=True)
class CheckReport:
    """Ukupan rezultat provere zadatka.

    Attributes:
        passed: Da li su ispunjeni svi kriterijumi.
        items: Pojedinačni rezultati (šta je tačno, šta nedostaje).
        summary: Kratka poruka za korisnika.
        next_step: Predlog šta da korisnik pokuša sledeće.
    """

    passed: bool
    items: tuple[CheckItem, ...] = field(default_factory=tuple)
    summary: str = ""
    next_step: str = ""


# ---------------------------------------------------------------------------
# Pomoćne funkcije
# ---------------------------------------------------------------------------
def normalize_output(text: str) -> str:
    """Uklanja razlike koje nisu bitne: \\r, razmake na kraju redova, prazne redove na kraju."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in lines]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def strip_comments(code: str) -> str:
    """Vraća kod bez komentara. Ako kod ne može da se tokenizuje, koristi jednostavniju metodu."""
    try:
        tokens = [
            tok for tok in tokenize.generate_tokens(io.StringIO(code).readline)
            if tok.type != tokenize.COMMENT
        ]
        return tokenize.untokenize(tokens)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return "\n".join(line.split("#", 1)[0] for line in code.splitlines())


def count_comments(code: str) -> int:
    """Broji komentare (# ...) u kodu, ne računajući znak # unutar teksta."""
    try:
        return sum(
            1 for tok in tokenize.generate_tokens(io.StringIO(code).readline)
            if tok.type == tokenize.COMMENT and tok.string.lstrip("#").strip()
        )
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return sum(1 for line in code.splitlines() if line.strip().startswith("#") and line.strip("# \t"))


def _rule_matches(code: str, rule: CodeRule) -> bool:
    source = strip_comments(code) if rule.ignore_comments else code
    if rule.regex:
        count = len(re.findall(rule.pattern, source, flags=re.MULTILINE))
    else:
        count = source.count(rule.pattern)
    return count >= rule.min_count


_PUNCTUATION = ".,!?:;"


def describe_line_difference(expected: str, actual: str) -> str:
    """Kratko objašnjenje zašto se dva reda razlikuju (ili prazno ako uzrok nije očigledan)."""
    if expected.lower() == actual.lower():
        return "razlika je u velikim i malim slovima"
    if expected.replace(" ", "") == actual.replace(" ", ""):
        return "razlika je u razmacima"
    if actual.strip("\"'") == expected and actual != expected:
        return "tvoj program ispisuje i navodnike — navodnici samo označavaju tekst u kodu"
    if expected.rstrip(_PUNCTUATION) == actual.rstrip(_PUNCTUATION):
        return "razlika je u znaku interpunkcije na kraju reda"
    if expected.startswith(actual):
        return f"nedostaje kraj reda: „{expected[len(actual):]}“"
    if actual.startswith(expected):
        return f"višak na kraju reda: „{actual[len(expected):]}“"
    return ""


def _first_difference(expected: str, actual: str) -> str:
    if not actual.strip():
        return "Program nije ništa ispisao. Da li si zaboravio print()?"
    exp_lines = expected.split("\n")
    act_lines = actual.split("\n")
    for index in range(max(len(exp_lines), len(act_lines))):
        exp = exp_lines[index] if index < len(exp_lines) else None
        act = act_lines[index] if index < len(act_lines) else None
        if exp != act:
            if act is None:
                return f"Red {index + 1}: očekivano „{exp}“, ali tvoj program tu više ništa ne ispisuje."
            if exp is None:
                return f"Red {index + 1}: tvoj program ispisuje višak — „{act}“."
            why = describe_line_difference(exp, act)
            hint = f" ({why})" if why else ""
            return f"Red {index + 1}: očekivano „{exp}“, dobijeno „{act}“{hint}."
    return ""


def _missing_fragment_detail(fragment: str, output: str) -> str:
    """Savet kada traženi tekst nije u izlazu — da li postoji „skoro isti“?"""
    if not output.strip():
        return "Program nije ništa ispisao."
    if fragment.lower() in output.lower():
        return "Tekst postoji, ali se razlikuje u velikim i malim slovima."
    if fragment.replace(" ", "") in output.replace(" ", ""):
        return "Tekst postoji, ali se razlikuje u razmacima."
    stripped = fragment.rstrip(_PUNCTUATION)
    if stripped and stripped != fragment and stripped in output:
        return "Tekst postoji, ali bez znaka interpunkcije na kraju."
    last_line = output.strip().split("\n")[-1]
    return f"Poslednji red koji je program ispisao: „{last_line[:80]}“."


# ---------------------------------------------------------------------------
# Provera izlaza jednog pokretanja
# ---------------------------------------------------------------------------
_ABORTED = (RunStatus.TIMEOUT, RunStatus.OUTPUT_LIMIT, RunStatus.STOPPED, RunStatus.FAILED_TO_START)


def _output_items(result: RunResult, case: TestCase, case_sensitive: bool) -> list[CheckItem]:
    """Proverava izlaz jednog pokretanja prema očekivanjima slučaja."""
    items: list[CheckItem] = []
    output = normalize_output(result.stdout)
    compare_out = output if case_sensitive else output.lower()

    def norm(text: str) -> str:
        return text if case_sensitive else text.lower()

    if case.expected_output is not None:
        expected = normalize_output(case.expected_output)
        same = compare_out == norm(expected)
        items.append(CheckItem(
            same,
            "Izlaz programa je tačno onakav kakav se očekuje." if same
            else "Izlaz programa se razlikuje od očekivanog.",
            "" if same else _first_difference(expected, output),
        ))
    for fragment in case.output_contains:
        found = norm(fragment) in compare_out
        items.append(CheckItem(
            found, f"Izlaz sadrži „{fragment}“." if found else f"U izlazu nedostaje „{fragment}“.",
            "" if found else _missing_fragment_detail(fragment, output)))
    for fragment in case.output_not_contains:
        absent = norm(fragment) not in compare_out
        items.append(CheckItem(
            absent, f"Izlaz ne sadrži „{fragment}“." if absent
            else f"Izlaz ne bi smeo da sadrži „{fragment}“."))
    if case.output_line_count is not None:
        count = len([line for line in output.split("\n") if line.strip()]) if output else 0
        ok = count == case.output_line_count
        items.append(CheckItem(
            ok,
            f"Program ispisuje {case.output_line_count} red(a)." if ok
            else f"Program treba da ispiše {case.output_line_count} red(a), a ispisuje {count}.",
        ))
    return items


def _code_items(code: str, criteria: CheckCriteria) -> list[CheckItem]:
    items: list[CheckItem] = []
    for rule in criteria.code_contains:
        ok = _rule_matches(code, rule)
        items.append(CheckItem(ok, rule.message, "" if ok else "Ovo pravilo još nije ispunjeno."))
    for rule in criteria.code_not_contains:
        ok = not _rule_matches(code, rule)
        items.append(CheckItem(ok, rule.message, "" if ok else "Ovo pravilo još nije ispunjeno."))
    if criteria.min_comment_lines:
        count = count_comments(code)
        ok = count >= criteria.min_comment_lines
        items.append(CheckItem(
            ok,
            f"Kod ima najmanje {criteria.min_comment_lines} komentar(a)." if ok
            else f"Kod treba da ima najmanje {criteria.min_comment_lines} komentar(a), a ima {count}.",
        ))
    return items


def _case_title(index: int, case: TestCase) -> str:
    label = f"Test {index}"
    if case.gui_script:
        label = f"Provera prozora {index}" + (f" ({case.name})" if case.name else "")
    elif case.test_label:
        label += f" ({case.test_label})"
    elif case.input_label:
        label += f" (unos: {case.input_label})"
    elif case.name:
        label += f" ({case.name})"
    return label


# ---------------------------------------------------------------------------
# Glavna funkcija
# ---------------------------------------------------------------------------
def evaluate(
    code: str,
    results: RunResult | Sequence[RunResult],
    criteria: CheckCriteria,
) -> CheckReport:
    """Upoređuje kod i rezultat(e) izvršavanja sa kriterijumima zadatka.

    Args:
        code: Kod koji je proveravan.
        results: Rezultat jednog pokretanja, ili lista rezultata — po jedan za
            svaki slučaj iz ``criteria.effective_cases()``, istim redosledom.
            Ako je rezultata manje nego slučajeva (provera je prekinuta),
            nedostajući slučajevi se računaju kao neuspešni.
        criteria: Kriterijumi zadatka.
    """
    result_list = [results] if isinstance(results, RunResult) else list(results)
    cases = criteria.effective_cases()

    if not code.strip() or not strip_comments(code).strip():
        return CheckReport(
            passed=False,
            items=(CheckItem(False, "Editor ne sadrži kod koji može da se izvrši."),),
            summary="Nema koda za proveru.",
            next_step="Napiši rešenje u editoru, pa ponovo klikni „Proveri zadatak“.",
        )

    aborted = next((r for r in result_list if r.status in _ABORTED), None)
    if aborted is not None:
        return CheckReport(
            passed=False,
            items=(CheckItem(False, "Program nije završio rad normalno.", aborted.status.label),),
            summary=aborted.status.label + ".",
            next_step="Proveri da li program ima petlju koja se nikad ne završava, čeka unos koji "
                      "ne postoji ili ispisuje previše teksta.",
        )

    items: list[CheckItem] = []
    all_ran_ok = all(r.status is RunStatus.SUCCESS for r in result_list) and len(result_list) == len(cases)

    if not criteria.cases:
        # Jedno pokretanje: detaljne stavke, jedna po kriterijumu.
        result = result_list[0] if result_list else None
        ran_ok = result is not None and result.status is RunStatus.SUCCESS
        if criteria.must_succeed:
            items.append(CheckItem(
                ran_ok,
                "Program se izvršava bez greške." if ran_ok else "Program se završio greškom.",
                "" if ran_ok else "Pogledaj objašnjenje greške u panelu sa rezultatom.",
            ))
        if result is not None:
            items.extend(_output_items(result, cases[0], criteria.case_sensitive))
    else:
        # Više pokretanja: po jedna stavka za svaki test slučaj.
        for index, case in enumerate(cases, start=1):
            title = _case_title(index, case)
            if index > len(result_list):
                items.append(CheckItem(False, f"{title}: nije pokrenut.", "Provera je prekinuta."))
                continue
            result = result_list[index - 1]
            problems: list[str] = []
            if criteria.must_succeed and result.status is not RunStatus.SUCCESS:
                problems.append("program se završio greškom")
            problems.extend(
                item.message + (f" {item.detail}" if item.detail else "")
                for item in _output_items(result, case, criteria.case_sensitive) if not item.ok
            )
            if problems:
                items.append(CheckItem(False, f"{title}: nije prošao.", " ".join(problems)))
            else:
                items.append(CheckItem(True, f"{title}: prošao."))

    items.extend(_code_items(code, criteria))

    passed = all(item.ok for item in items)
    failed = [item for item in items if not item.ok]
    if passed:
        summary = "Bravo! Zadatak je uspešno rešen."
        next_step = "Označi lekciju kao završenu i pređi na sledeću."
    else:
        summary = f"Još malo — ispunjeno {len(items) - len(failed)} od {len(items)} kriterijuma."
        if not all_ran_ok:
            next_step = "Prvo ispravi grešku koju je Python prijavio, pa ponovo proveri."
        elif criteria.cases:
            next_step = ("Pokreni program sam i upiši unos iz testa koji nije prošao, pa uporedi "
                         "šta program ispisuje sa onim što se očekuje.")
        else:
            next_step = "Pogledaj stavke označene kao neispunjene. Ako zapneš, klikni „Nagoveštaj“."
    return CheckReport(passed, tuple(items), summary, next_step)
