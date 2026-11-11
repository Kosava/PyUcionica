# pyqt6_learning_studio/tests/test_settings_ui.py
"""Testovi dijaloga podešavanja i njihove primene u glavnom prozoru (bez prikaza na ekranu)."""

from __future__ import annotations

from config.settings import COURSE_FILE
from core.lesson_manager import LessonManager
from core.progress_manager import ProgressManager
from core.settings_manager import SETTINGS, USER_SETTINGS, SettingsManager
from database.database_manager import DatabaseManager


def _managers():
    db = DatabaseManager(":memory:")
    return db, SettingsManager(db), ProgressManager(db)


def test_dialog_values_roundtrip_and_defaults(qt_app):
    from ui.settings_dialog import SettingsDialog

    _, settings, progress = _managers()
    values = {key: settings.get(key) for key in USER_SETTINGS}
    values["editor/font_size"] = 16
    values["runner/timeout_s"] = 5
    dialog = SettingsDialog(values, progress)
    assert dialog.values() == values
    dialog._restore_defaults()
    assert dialog.values() == {key: SETTINGS[key].default for key in USER_SETTINGS}
    dialog.done(0)


def test_main_window_applies_and_saves_settings(qt_app):
    from ui.main_window import MainWindow

    _, settings, progress = _managers()
    settings.set_many({"runner/timeout_s": 4, "runner/max_output_kchars": 20,
                       "editor/font_size": 14, "editor/line_numbers": False,
                       "lesson/confirm_solution": False})
    window = MainWindow(LessonManager(COURSE_FILE), progress, settings)
    assert window._runner.limits.timeout_ms == 4000
    assert window._runner.limits.max_output_chars == 20_000
    assert window.output_panel._view.font().pointSize() == 14
    assert not window.editor_panel.line_numbers_visible()
    assert window.lesson_panel._confirm_solution is False

    window._request_lesson("m01_l03")
    assert progress.current_lesson_id == "m01_l03"
    assert progress.last_module_id == "m01"
    window.close()
    assert settings.get("window/geometry")
    assert settings.get("layout/workspace_split")
