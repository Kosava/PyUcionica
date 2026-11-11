# pyqt6_learning_studio/tests/test_progress_manager.py
"""Testovi za napredak u SQLite bazi i prenos starog progress.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.progress_manager import ProgressManager
from database.database_manager import DatabaseManager


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "t.db"


def _pm(path: Path) -> ProgressManager:
    return ProgressManager(DatabaseManager(path))


def test_progress_persists_between_instances(db_path: Path):
    pm = _pm(db_path)
    pm.set_current_lesson("m01_l02", "m01")
    pm.set_completed("m01_l01")
    pm.save_code("m01_l02", 'print("ćao")\n')
    assert pm.record_attempt("m01_l02", solved=False) == 1
    assert pm.record_attempt("m01_l02", solved=True) == 2
    pm.database.close()

    again = _pm(db_path)
    assert again.current_lesson_id == "m01_l02"
    assert again.last_module_id == "m01"
    assert again.is_completed("m01_l01")
    assert again.saved_code("m01_l02") == 'print("ćao")\n'
    assert again.attempts("m01_l02") == 2
    assert again.is_solved("m01_l02")
    status = again.lesson_status("m01_l02")
    assert status.attempts == 2 and status.solved_at and status.code_saved_at


def test_solved_at_keeps_first_time(db_path: Path):
    pm = _pm(db_path)
    pm.record_attempt("a", True)
    first = pm.lesson_status("a").solved_at
    pm.record_attempt("a", False)
    pm.record_attempt("a", True)
    assert pm.lesson_status("a").solved_at == first
    assert pm.is_solved("a")


def test_uncomplete_and_delete_code(db_path: Path):
    pm = _pm(db_path)
    pm.set_completed("a")
    pm.set_completed("a", False)
    assert not pm.is_completed("a")
    assert pm.lesson_status("a").completed_at is None
    pm.save_code("a", "x")
    pm.delete_saved_code("a")
    assert pm.saved_code("a") is None


def test_completed_count_among(db_path: Path):
    pm = _pm(db_path)
    for lid in ("a", "b", "c"):
        pm.set_completed(lid)
    assert pm.completed_count() == 3
    assert pm.completed_count(["a", "x"]) == 1


def test_export_and_reset(db_path: Path, tmp_path: Path):
    pm = _pm(db_path)
    pm.set_completed("a")
    pm.record_attempt("a", True)
    pm.record_quiz("a", 4, 5, True)
    target = tmp_path / "export.json"
    pm.export_json(target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["format"] == "pyqt6-learning-studio-progress"
    assert data["lessons"][0]["lesson_id"] == "a"
    assert len(data["check_attempts"]) == 1 and len(data["quiz_attempts"]) == 1

    assert pm.has_any_progress()
    pm.reset_all()
    assert not pm.has_any_progress()
    assert pm.completed_ids() == set() and pm.quiz_record("a") is None


def _legacy_file(tmp_path: Path) -> Path:
    legacy = tmp_path / "progress.json"
    legacy.write_text(json.dumps({
        "version": 1,
        "current_lesson": "m01_l03",
        "completed": ["m01_l01", "m01_l02"],
        "solved": ["m01_l02"],
        "attempts": {"m01_l02": 3},
        "saved_code": {"m01_l03": "print(1)\n"},
        "quiz": {"m01_l01": {"best": 4, "last": 3, "total": 5, "attempts": 2, "passed": True}},
    }), encoding="utf-8")
    return legacy


def test_import_legacy_json(db_path: Path, tmp_path: Path):
    legacy = _legacy_file(tmp_path)
    pm = _pm(db_path)
    assert pm.import_legacy_json(legacy)
    assert not legacy.exists()
    assert (tmp_path / "progress.json.migrated").exists()
    assert pm.current_lesson_id == "m01_l03"
    assert pm.completed_ids() == {"m01_l01", "m01_l02"}
    assert pm.is_solved("m01_l02") and pm.attempts("m01_l02") == 3
    assert pm.saved_code("m01_l03") == "print(1)\n"
    record = pm.quiz_record("m01_l01")
    assert (record.best, record.last, record.total, record.attempts, record.passed) == (4, 3, 5, 2, True)


def test_import_skipped_when_db_has_progress(db_path: Path, tmp_path: Path):
    legacy = _legacy_file(tmp_path)
    pm = _pm(db_path)
    pm.set_completed("x")
    assert not pm.import_legacy_json(legacy)
    assert legacy.exists()


def test_import_of_broken_json_is_safe(db_path: Path, tmp_path: Path):
    legacy = tmp_path / "progress.json"
    legacy.write_text("{oštećeno", encoding="utf-8")
    pm = _pm(db_path)
    assert not pm.import_legacy_json(legacy)
    assert legacy.exists()
    assert not pm.has_any_progress()


def test_favorites(db_path: Path):
    pm = _pm(db_path)
    pm.set_favorite("b")
    pm.set_favorite("a")
    pm.set_favorite("a")
    assert pm.favorite_ids() == ["b", "a"]
    assert pm.is_favorite("a")
    pm.set_favorite("b", False)
    assert pm.favorite_ids() == ["a"]
    pm.set_completed("a")
    pm.reset_all()
    assert pm.favorite_ids() == ["a"], "Brisanje napretka ne briše omiljene lekcije."
