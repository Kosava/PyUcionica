# pyqt6_learning_studio/tests/test_startup.py
"""Testovi pokretanja aplikacije (main.main) i obrade grešaka pri pokretanju."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

import main as app_main


@pytest.fixture
def startup(monkeypatch, tmp_path: Path, qt_app):
    """Pokreće main() sa podacima u tmp_path; prozor se zatvara čim se pojavi."""
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(app_main, "_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_main, "_import_legacy_qsettings", lambda settings: None)
    for name in ("critical", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name,
                            staticmethod(lambda parent, title, text, *a, _n=name, **k: messages.append((_n, title))))

    def run() -> int:
        before = set(QApplication.topLevelWidgets())

        def close_windows():
            # Zatvara samo prozore koje je napravio ovaj main(), ne prozore drugih testova.
            for widget in QApplication.topLevelWidgets():
                if widget not in before and widget.inherits("QMainWindow") and widget.isVisible():
                    widget.close()
            QApplication.instance().quit()

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(close_windows)
        timer.start(300)
        try:
            return app_main.main()
        finally:
            timer.stop()  # main() se možda završio ranije (greška) — tajmer ne sme da ostane živ

    return run, messages, tmp_path


def test_normal_start_creates_database(startup):
    run, messages, data = startup
    assert run() == 0
    assert (data / app_main.DATABASE_NAME).exists()
    assert not [m for m in messages if m[0] == "critical"]


def test_legacy_progress_is_migrated_on_start(startup):
    run, _, data = startup
    (data / "progress.json").write_text(json.dumps({"completed": ["m01_l01"], "current_lesson": "m01_l02"}),
                                        encoding="utf-8")
    assert run() == 0
    assert (data / "progress.json.migrated").exists()
    conn = sqlite3.connect(data / app_main.DATABASE_NAME)
    try:
        assert conn.execute("SELECT completed FROM lesson_progress WHERE lesson_id='m01_l01'").fetchone()[0] == 1
    finally:
        conn.close()


def test_corrupted_database_is_reported(startup):
    run, messages, data = startup
    (data / app_main.DATABASE_NAME).write_bytes(b"x" * 4096)
    assert run() == 0
    assert ("warning", "Baza podataka je obnovljena") in messages
    assert list(data.glob("*.corrupt-*"))


def test_newer_database_stops_with_message(startup):
    run, messages, data = startup
    conn = sqlite3.connect(data / app_main.DATABASE_NAME)
    conn.executescript("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                       "INSERT INTO meta VALUES ('schema_version', '99');")
    conn.commit()
    conn.close()
    assert run() == 1
    assert messages[0] == ("critical", "Baza podataka")


def test_broken_course_file_stops_with_message(startup, monkeypatch, tmp_path: Path):
    run, messages, _ = startup
    broken = tmp_path / "course.json"
    broken.write_text("{ ovo nije json", encoding="utf-8")
    monkeypatch.setattr(app_main, "COURSE_FILE", broken)
    assert run() == 1
    assert messages[0] == ("critical", "Kurs nije učitan")


def test_embedded_run_flag_is_ignored_without_script():
    from core.python_locator import run_embedded_script

    assert run_embedded_script(["main.py"]) is None
    assert run_embedded_script(["main.py", "--debug"]) is None


def test_self_test_passes(qt_app):
    import io

    from core.self_test import run_self_test

    out = io.StringIO()
    assert run_self_test(qt_app, out) == 0, out.getvalue()
    assert "Samoprovera uspešna." in out.getvalue()
    assert out.getvalue().count("[OK]") == 6


def test_app_icon_exists_and_renders(qt_app):
    from PyQt6.QtGui import QIcon

    from config.settings import APP_ICON

    assert APP_ICON.is_file()
    assert not QIcon(str(APP_ICON)).pixmap(64, 64).isNull()
