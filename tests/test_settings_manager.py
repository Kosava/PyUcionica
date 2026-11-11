# pyqt6_learning_studio/tests/test_settings_manager.py
"""Testovi za korisnička podešavanja u bazi."""

from __future__ import annotations

import pytest

from core.settings_manager import SETTINGS, USER_SETTINGS, SettingsManager
from database.database_manager import DatabaseManager


@pytest.fixture
def settings():
    with DatabaseManager(":memory:") as db:
        yield SettingsManager(db)


def test_defaults(settings):
    for key, spec in SETTINGS.items():
        assert settings.get(key) == spec.default


def test_set_and_get_types(settings):
    settings.set("editor/font_size", 14)
    settings.set("editor/line_numbers", False)
    settings.set("layout/lesson_size", "expanded")
    settings.set("window/geometry", b"\x01\x02\xff")
    assert settings.get("editor/font_size") == 14
    assert settings.get("editor/line_numbers") is False
    assert settings.get("layout/lesson_size") == "expanded"
    assert settings.get("window/geometry") == b"\x01\x02\xff"


def test_values_are_clamped(settings):
    assert settings.set("runner/timeout_s", 999) == 120
    assert settings.set("editor/font_size", 2) == 8


def test_wrong_types_are_rejected(settings):
    with pytest.raises(TypeError):
        settings.set("editor/line_numbers", "da")
    with pytest.raises(TypeError):
        settings.set("editor/font_size", True)
    with pytest.raises(ValueError):
        settings.set("layout/lesson_size", "ogroman")
    with pytest.raises(KeyError):
        settings.set("nepostoji", 1)


def test_broken_stored_value_falls_back_to_default(settings):
    settings._db.execute("INSERT INTO settings (key, value) VALUES ('editor/font_size', '\"abc\"')")
    assert settings.get("editor/font_size") == SETTINGS["editor/font_size"].default


def test_reset_user_settings_keeps_layout(settings):
    settings.set("editor/font_size", 16)
    settings.set("window/geometry", b"abc")
    settings.reset_user_settings()
    assert settings.get("editor/font_size") == 11
    assert settings.get("window/geometry") == b"abc"
    assert "window/geometry" not in USER_SETTINGS


def test_import_legacy(settings):
    count = settings.import_legacy({
        "editor/line_numbers": "false",
        "layout/lesson_size": "compact",
        "layout/browser_visible": True,
        "nepoznato": 5,
        "layout/main_split": b"\x00\x01",
    })
    assert count == 4
    assert settings.get("editor/line_numbers") is False
    assert settings.get("layout/main_split") == b"\x00\x01"
