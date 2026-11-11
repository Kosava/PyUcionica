# pyqt6_learning_studio/tests/test_editor_utils.py
"""Testovi za pomoćne funkcije editora (uključivanje/isključivanje komentara)."""

from __future__ import annotations

from ui.code_editor import toggle_comment_lines


def test_comment_adds_hash_at_min_indent():
    assert toggle_comment_lines(["print(1)", "    x = 2"]) == ["# print(1)", "#     x = 2"]


def test_uncomment_removes_hash():
    assert toggle_comment_lines(["# print(1)", "    # x = 2"]) == ["print(1)", "    x = 2"]


def test_mixed_lines_are_commented():
    assert toggle_comment_lines(["# a", "b"]) == ["# # a", "# b"]


def test_empty_lines_are_untouched():
    assert toggle_comment_lines(["a", "", "b"]) == ["# a", "", "# b"]
