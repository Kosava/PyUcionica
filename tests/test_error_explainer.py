# pyqt6_learning_studio/tests/test_error_explainer.py
"""Testovi za prevođenje Python grešaka u objašnjenja za početnike."""

from __future__ import annotations

from core.error_explainer import explain_error, parse_traceback
from tests.conftest import run_code


def test_parse_name_error():
    tb = (
        "Traceback (most recent call last):\n"
        '  File "main.py", line 2, in <module>\n'
        '    Print("x")\n'
        "NameError: name 'Print' is not defined. Did you mean: 'print'?\n"
    )
    exc, msg, line = parse_traceback(tb)
    assert exc == "NameError"
    assert line == 2
    assert "Print" in msg


def test_no_error_returns_none():
    assert explain_error("") is None
    assert explain_error("samo neki tekst\n") is None


def test_name_error_suggests_correct_name(qt_app):
    info = explain_error(run_code('Print("x")\n').stderr)
    assert info is not None
    assert info.exc_type == "NameError"
    assert info.line == 1
    assert "print" in info.tip


def test_unterminated_string(qt_app):
    info = explain_error(run_code('print("a)\n').stderr)
    assert info.exc_type == "SyntaxError"
    assert info.line == 1
    assert "navodnik" in info.explanation


def test_unclosed_parenthesis(qt_app):
    info = explain_error(run_code('print("a"\n').stderr)
    assert info.exc_type == "SyntaxError"
    assert "zagrad" in info.explanation


def test_unexpected_indent(qt_app):
    info = explain_error(run_code('print("a")\n    print("b")\n').stderr)
    assert info.exc_type == "IndentationError"
    assert info.line == 2


def test_type_error_concatenation(qt_app):
    info = explain_error(run_code('print("Godine: " + 30)\n').stderr)
    assert info.exc_type == "TypeError"
    assert "str(" in info.tip


def test_zero_division(qt_app):
    info = explain_error(run_code("print(1)\nprint(1 / 0)\n").stderr)
    assert info.exc_type == "ZeroDivisionError"
    assert info.line == 2


def test_error_inside_function_points_to_last_user_line(qt_app):
    code = "def f():\n    return 1 / 0\n\nf()\n"
    info = explain_error(run_code(code).stderr)
    assert info.line == 2


def test_unknown_error_type_has_generic_explanation():
    info = explain_error("MyCustomError: nesto\n")
    assert info is not None
    assert "MyCustomError" in info.title
