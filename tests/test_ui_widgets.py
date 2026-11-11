# pyqt6_learning_studio/tests/test_ui_widgets.py
"""Testovi pojedinačnih widget-a: dijalog pretrage i rezervni editor koda (bez QScintille)."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest

from config.settings import COURSE_FILE
from core.lesson_manager import LessonManager
from core.lesson_search import LessonSearch

LESSONS = LessonManager(COURSE_FILE)


def _modules():
    return {m.module_id: m.title for m in LESSONS.modules}


def test_lessons_label_plural():
    from ui.search_dialog import lessons_label

    assert [lessons_label(n) for n in (1, 2, 5, 12, 21, 22)] == [
        "1 lekcija", "2 lekcije", "5 lekcija", "12 lekcija", "21 lekcija", "22 lekcije"]


def test_highlight_escapes_and_marks():
    from ui.search_dialog import highlight

    html = highlight("a <b> c", ((2, 5),))
    assert "&lt;b&gt;" in html and "<span" in html


def test_search_dialog_keyboard_flow(qt_app):
    from ui.search_dialog import SearchDialog

    dialog = SearchDialog(LessonSearch(LESSONS), _modules())
    selected: list[str] = []
    dialog.lesson_selected.connect(selected.append)
    assert "Pretraga obuhvata" in dialog._info.text()

    dialog.set_query("nepostojecarec")
    assert "Nema rezultata" in dialog._info.text() and dialog._results.count() == 0

    dialog._input.setText("print")        # bez čekanja: Enter pokreće pretragu odmah
    QTest.keyClick(dialog._input, Qt.Key.Key_Down)
    QTest.keyClick(dialog._input, Qt.Key.Key_Up)
    assert dialog._results.count() > 1 and dialog._results.currentRow() == 0
    QTest.keyClick(dialog._input, Qt.Key.Key_Down)
    expected = dialog._results.item(1).data(Qt.ItemDataRole.UserRole)
    QTest.keyClick(dialog._input, Qt.Key.Key_Return)
    assert selected == [expected]


def _fallback(text: str = ""):
    from ui.code_editor import CodeEditor

    editor = CodeEditor(force_fallback=True)
    editor.resize(500, 300)
    editor.show()
    editor.set_text(text)
    return editor


def test_fallback_editor_indentation(qt_app):
    editor = _fallback()
    backend = editor._backend
    editor.setFocus()
    QTest.keyClicks(backend, "if x:")
    QTest.keyClick(backend, Qt.Key.Key_Return)
    QTest.keyClicks(backend, "y = 1")
    QTest.keyClick(backend, Qt.Key.Key_Return)
    QTest.keyClick(backend, Qt.Key.Key_Backspace)    # briše ceo nivo uvlačenja
    QTest.keyClicks(backend, "z")
    QTest.keyClick(backend, Qt.Key.Key_Tab)
    assert editor.text() == "if x:\n    y = 1\nz    "
    QTest.keyClick(backend, Qt.Key.Key_Backtab)
    editor.close()


def test_fallback_editor_shortcuts_and_marks(qt_app):
    editor = _fallback('print(1)\nprint(2)\n')
    runs: list[int] = []
    editor.run_requested.connect(lambda: runs.append(1))
    backend = editor._backend
    backend.setFocus()
    QTest.keyClick(backend, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert runs == [1]
    QTest.keyClick(backend, Qt.Key.Key_Slash, Qt.KeyboardModifier.ControlModifier)
    assert editor.text().startswith("# print(1)")
    QTest.keyClick(backend, Qt.Key.Key_Slash, Qt.KeyboardModifier.ControlModifier)
    assert editor.text().startswith("print(1)")

    editor.mark_error_line(2)
    assert backend._error_line == 2
    editor.set_line_numbers_visible(False)
    assert backend.line_number_width() == 0
    editor.set_line_numbers_visible(True)
    assert backend.line_number_width() > 0
    editor.clear_error_marks()
    assert backend._error_line is None
    editor.grab()                                       # iscrtavanje brojeva linija i bojenja

    from ui.code_editor import editor_font, set_default_font_size
    set_default_font_size(14)
    editor.set_editor_font(editor_font())
    assert backend.font().pointSize() == 14
    set_default_font_size(11)
    editor.close()


def test_editor_modified_state_and_restore(qt_app):
    editor = _fallback("a = 1\n")
    changes: list[bool] = []
    editor.modified_changed.connect(changes.append)
    editor._backend.insertPlainText("# x\n")
    assert editor.is_modified() and changes[-1] is True
    editor.restore_state("b = 2\n", "a = 1\n")
    assert editor.text() == "b = 2\n" and editor.baseline == "a = 1\n" and editor.is_modified()
    editor.mark_clean()
    assert not editor.is_modified() and changes[-1] is False
    editor.close()


def test_read_only_editor_ignores_comment_shortcut(qt_app):
    from ui.code_editor import CodeEditor

    editor = CodeEditor(read_only=True, force_fallback=True)
    editor.set_text("x = 1\n")
    editor.toggle_comment()
    assert editor.text() == "x = 1\n"
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Slash, Qt.KeyboardModifier.ControlModifier)
    editor.eventFilter(editor._backend, event)
    assert editor.text() == "x = 1\n"
