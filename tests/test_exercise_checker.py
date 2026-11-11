# pyqt6_learning_studio/tests/test_exercise_checker.py
"""Testovi za proveru zadataka: kriterijumi, poređenje izlaza i stvarne lekcije kursa."""

from __future__ import annotations

import pytest

from config.settings import COURSE_FILE
from core.code_runner import RunResult, RunStatus
from core.exercise_checker import count_comments, evaluate, normalize_output, strip_comments
from core.lesson_manager import LessonManager
from models.exercise import CheckCriteria, CodeRule
from tests.conftest import run_check, run_code


def _result(stdout: str = "", status: RunStatus = RunStatus.SUCCESS, stderr: str = "") -> RunResult:
    return RunResult(status, 0 if status is RunStatus.SUCCESS else 1, stdout, stderr, 0.01)


def test_normalize_output_ignores_trailing_whitespace():
    assert normalize_output("a  \r\nb\n\n\n") == "a\nb"


def test_strip_and_count_comments():
    code = '# opis\nprint("#nije komentar")  # komentar\n'
    assert count_comments(code) == 2
    assert "#nije komentar" in strip_comments(code)
    assert "opis" not in strip_comments(code)


def test_success_is_not_enough():
    criteria = CheckCriteria(expected_output="Zdravo")
    report = evaluate('print("Nesto drugo")', _result("Nesto drugo\n"), criteria)
    assert not report.passed
    assert any("Red 1" in item.detail for item in report.items)


def test_expected_output_pass():
    criteria = CheckCriteria(expected_output="A\nB")
    report = evaluate('print("A")\nprint("B")', _result("A\nB\n"), criteria)
    assert report.passed


def test_case_difference_is_explained():
    criteria = CheckCriteria(expected_output="Python")
    report = evaluate('print("python")', _result("python\n"), criteria)
    assert not report.passed
    assert "velikim i malim" in " ".join(i.detail for i in report.items)


def test_code_rules_ignore_comments():
    rule = CodeRule(pattern="print(", message="koristi print", min_count=2)
    criteria = CheckCriteria(code_contains=(rule,), must_succeed=False)
    report = evaluate('print("a")\n# print("b")', _result("a\n"), criteria)
    assert not report.passed


def test_code_not_contains():
    rule = CodeRule(pattern="Print(", message="bez Print")
    criteria = CheckCriteria(code_not_contains=(rule,), must_succeed=False)
    assert not evaluate('Print("x")', _result(status=RunStatus.ERROR), criteria).passed
    assert evaluate('print("x")', _result("x\n"), criteria).passed


def test_error_run_fails_when_success_required():
    criteria = CheckCriteria(output_contains=("a",))
    report = evaluate('print("a")\n1/0', _result("a\n", RunStatus.ERROR, "ZeroDivisionError"), criteria)
    assert not report.passed
    assert "ispravi grešku" in report.next_step


def test_timeout_is_failure():
    report = evaluate("while True: pass", _result(status=RunStatus.TIMEOUT), CheckCriteria())
    assert not report.passed


def test_empty_code_is_failure():
    report = evaluate("# samo komentar\n", _result(), CheckCriteria())
    assert not report.passed


# ---------------------------------------------------------------------------
# Provera stvarnih lekcija: rešenje mora proći, početni kod ne sme.
# ---------------------------------------------------------------------------
_MANAGER = LessonManager(COURSE_FILE)
_LESSON_IDS = [info.lesson_id for info in _MANAGER.available_lessons]


@pytest.mark.parametrize("lesson_id", _LESSON_IDS)
def test_lesson_solution_passes(qt_app, lesson_id):
    lesson = _MANAGER.load(lesson_id)
    report, results = run_check(lesson.exercise.solution, lesson.exercise.criteria)
    assert len(results) == len(lesson.exercise.criteria.effective_cases())
    assert report.passed, [(i.message, i.detail) for i in report.items if not i.ok]


@pytest.mark.parametrize("lesson_id", _LESSON_IDS)
def test_lesson_starter_code_does_not_pass(qt_app, lesson_id):
    lesson = _MANAGER.load(lesson_id)
    report, _ = run_check(lesson.exercise.starter_code, lesson.exercise.criteria)
    assert not report.passed


def test_lesson_4_deleting_line_is_not_accepted(qt_app):
    """Brisanje linije umesto zakomentarisanja ne sme proći."""
    lesson = _MANAGER.load("m01_l04")
    code = '# Spisak\n# komentar\nprint("Kupi hleb")\nprint("Kupi mleko")\nprint("Kupi jaja")\n'
    result = run_code(code)
    assert not evaluate(code, result, lesson.exercise.criteria).passed


# ---------------------------------------------------------------------------
# Više test slučajeva: „ručno upisan“ odgovor ne sme da prođe.
# ---------------------------------------------------------------------------
def test_hardcoded_answer_fails_input_lesson(qt_app):
    lesson = _MANAGER.load("m02_l06")
    cheat = (
        'ime = input("Ime? ")\ngodine = int(input("Godine? "))\n'
        'print("Zdravo, Ana!")\nprint("Za 10 godina imaćeš 35 godina.")\n'
    )
    report, results = run_check(cheat, lesson.exercise.criteria)
    assert len(results) == 3
    assert not report.passed
    assert report.items[0].ok and not report.items[1].ok


def test_calculator_without_zero_check_fails(qt_app):
    lesson = _MANAGER.load("m03_l06")
    code = lesson.exercise.solution.replace(
        '    if b == 0:\n        print("Deljenje nulom nije moguće.")\n    else:\n        print("Rezultat:", a / b)',
        '    print("Rezultat:", a / b)',
    )
    report, _ = run_check(code, lesson.exercise.criteria)
    assert not report.passed


def test_unnested_login_fails(qt_app):
    """Program koji uvek pita za lozinku ne prolazi slučaj nepoznatog korisnika."""
    lesson = _MANAGER.load("m03_l05")
    code = (
        'korisnik = input("Ime: ")\nlozinka = input("Lozinka: ")\n'
        'if korisnik == "admin":\n    if lozinka == "python123":\n        print("Dobro došao!")\n'
        '    else:\n        print("Pogrešna lozinka.")\nelse:\n    print("Nepoznat korisnik.")\n'
    )
    report, _ = run_check(code, lesson.exercise.criteria)
    assert not report.passed


def test_grade_order_matters(qt_app):
    """Pogrešan redosled uslova (prvo >= 50) daje pogrešne ocene."""
    lesson = _MANAGER.load("m03_l04")
    code = (
        'poeni = int(input())\nif poeni >= 50:\n    print("Dovoljan (2)")\nelif poeni >= 60:\n'
        '    print("Dobar (3)")\nelif poeni >= 75:\n    print("Vrlo dobar (4)")\nelif poeni >= 90:\n'
        '    print("Odličan (5)")\nelse:\n    print("Nedovoljan (1)")\n'
    )
    report, _ = run_check(code, lesson.exercise.criteria)
    assert not report.passed


def test_check_session_stops_after_timeout(qt_app):
    from models.exercise import CheckCriteria, TestCase

    criteria = CheckCriteria(cases=(TestCase(stdin="1"), TestCase(stdin="2"), TestCase(stdin="3")))
    report, results = run_check("x = input()\nwhile True:\n    pass\n", criteria)
    assert len(results) == 1
    assert not report.passed


def test_case_descriptions_are_shown():
    lesson = _MANAGER.load("m03_l06")
    lines = lesson.exercise.criteria.describe()
    assert any("6 puta" in line for line in lines)
    assert any("deljenje nulom" in line for line in lines)


# ---------------------------------------------------------------------------
# Testovi funkcija (test_code) i saveti pri razlici u izlazu
# ---------------------------------------------------------------------------
def _function_criteria():
    from models.exercise import CheckCriteria, CodeRule, TestCase

    return CheckCriteria(
        code_contains=(CodeRule(pattern="def saberi", message="Postoji funkcija saberi."),),
        cases=(
            TestCase(test_code="print(saberi(2, 3))", expected_output="5"),
            TestCase(test_code="print(saberi(-1, 1))", expected_output="0"),
        ),
    )


def test_function_tests_pass(qt_app):
    report, results = run_check("def saberi(a, b):\n    return a + b\n", _function_criteria())
    assert report.passed, [(i.message, i.detail) for i in report.items]
    assert "saberi(2, 3)" in report.items[0].message


def test_function_tests_fail_on_wrong_result(qt_app):
    report, _ = run_check("def saberi(a, b):\n    return a * b\n", _function_criteria())
    assert not report.passed
    assert "očekivano „5“, dobijeno „6“" in report.items[0].detail


def test_function_missing_error_is_in_test_code(qt_app):
    from core.error_explainer import explain_error

    code = "def zbir(a, b):\n    return a + b\n"
    report, results = run_check(code, _function_criteria())
    assert not report.passed
    info = explain_error(results[0].stderr)
    assert info.exc_type == "NameError"
    assert info.line > len(code.splitlines())


def test_describe_line_difference_hints():
    from core.exercise_checker import describe_line_difference

    assert "interpunkcije" in describe_line_difference("Zdravo!", "Zdravo")
    assert "navodnike" in describe_line_difference("Zdravo", '"Zdravo"')
    assert "nedostaje kraj" in describe_line_difference("Zdravo, svete", "Zdravo,")
    assert "višak" in describe_line_difference("Ana", "Ana Ana")


def test_empty_output_hint():
    from models.exercise import CheckCriteria

    report = evaluate("x = 5", _result(""), CheckCriteria(expected_output="5"))
    assert "print()" in report.items[1].detail


def test_missing_fragment_case_hint():
    from models.exercise import CheckCriteria, TestCase

    criteria = CheckCriteria(cases=(TestCase(output_contains=("Zdravo, Ana!",)),))
    report = evaluate('print("zdravo, ana!")', [_result("zdravo, ana!\n")], criteria)
    assert "velikim i malim" in report.items[0].detail
