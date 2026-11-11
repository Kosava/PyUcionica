# pyqt6_learning_studio/tests/test_database.py
"""Testovi za SQLite bazu: šema, transakcije, rezervna kopija, oporavak oštećene baze."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from database.database_manager import SCHEMA_VERSION, DatabaseError, DatabaseManager


def test_schema_is_created(tmp_path: Path):
    db = DatabaseManager(tmp_path / "a.db")
    tables = {r["name"] for r in db.query_all("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "lesson_progress", "check_attempts", "quiz_results", "quiz_attempts",
            "app_state", "settings"} <= tables
    assert db.schema_version == SCHEMA_VERSION


def test_reopen_keeps_data(tmp_path: Path):
    db = DatabaseManager(tmp_path / "a.db")
    db.execute("INSERT INTO app_state (key, value) VALUES ('x', '1')")
    db.close()
    db = DatabaseManager(tmp_path / "a.db")
    assert db.query_one("SELECT value FROM app_state WHERE key='x'")["value"] == "1"


def test_transaction_rolls_back_on_error(tmp_path: Path):
    db = DatabaseManager(tmp_path / "a.db")
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO app_state (key, value) VALUES ('a', '1')")
            conn.execute("INSERT INTO lesson_progress (lesson_id, completed) VALUES ('b', 7)")
    assert db.query_one("SELECT 1 FROM app_state WHERE key='a'") is None


def test_backup_copy_is_complete(tmp_path: Path):
    db = DatabaseManager(tmp_path / "a.db")
    db.execute("INSERT INTO settings (key, value) VALUES ('k', '\"v\"')")
    db.backup_to(tmp_path / "kopija" / "b.db")
    copy = DatabaseManager(tmp_path / "kopija" / "b.db")
    assert copy.query_one("SELECT value FROM settings WHERE key='k'")["value"] == '"v"'


def test_corrupted_file_is_moved_aside(tmp_path: Path):
    path = tmp_path / "a.db"
    path.write_bytes(b"ovo nije sqlite baza" * 100)
    db = DatabaseManager(path)
    assert db.recovered_from is not None and db.recovered_from.exists()
    assert db.is_empty("lesson_progress")
    assert path.exists()


def test_newer_schema_is_refused(tmp_path: Path):
    db = DatabaseManager(tmp_path / "a.db")
    db.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION + 1),))
    db.close()
    with pytest.raises(DatabaseError, match="novijom verzijom"):
        DatabaseManager(tmp_path / "a.db")


def test_memory_database():
    db = DatabaseManager(":memory:")
    assert db.is_empty("settings")


def test_upgrade_from_schema_v1(tmp_path: Path):
    """Baza iz Faze 4 (šema 1, bez tabele favorites) nadograđuje se bez gubitka podataka."""
    path = tmp_path / "stara.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE lesson_progress (lesson_id TEXT PRIMARY KEY, completed INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT, solved INTEGER NOT NULL DEFAULT 0, solved_at TEXT, saved_code TEXT,
            code_saved_at TEXT, last_opened_at TEXT);
        INSERT INTO lesson_progress (lesson_id, completed) VALUES ('m01_l01', 1);
    """)
    conn.commit()
    conn.close()
    db = DatabaseManager(path)
    assert db.schema_version == SCHEMA_VERSION == 2
    assert db.query_one("SELECT completed FROM lesson_progress WHERE lesson_id='m01_l01'")["completed"] == 1
    assert db.is_empty("favorites")
