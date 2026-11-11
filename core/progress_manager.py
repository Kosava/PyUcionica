# pyqt6_learning_studio/core/progress_manager.py
"""Napredak korisnika u SQLite bazi: lekcije, sačuvan kod, istorija provera i kvizova.

Javni interfejs je isti kao u Fazama 1–3 (kada se napredak čuvao u JSON
fajlu), pa ostatak aplikacije nije morao da se menja. Stari ``progress.json``
se jednom automatski prenosi u bazu (:meth:`ProgressManager.import_legacy_json`).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from database.database_manager import DatabaseManager, now_iso

log = logging.getLogger(__name__)

EXPORT_FORMAT_VERSION = 1


@dataclass(frozen=True)
class QuizRecord:
    """Rezultati kviza jedne lekcije.

    Attributes:
        best: Najbolji rezultat (broj tačnih odgovora).
        last: Rezultat poslednjeg pokušaja.
        total: Broj pitanja u kvizu.
        attempts: Koliko puta je kviz rađen.
        passed: Da li je kviz bar jednom položen.
    """

    best: int
    last: int
    total: int
    attempts: int
    passed: bool


@dataclass(frozen=True)
class LessonStatus:
    """Detalji napretka jedne lekcije (za prikaz u lekciji)."""

    attempts: int
    solved_at: str | None
    completed_at: str | None
    code_saved_at: str | None


class ProgressManager:
    """Napredak korisnika.

    Args:
        db: Otvorena baza.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    @property
    def storage_file(self) -> Path | str:
        return self._db.path

    @property
    def database(self) -> DatabaseManager:
        return self._db

    # ------------------------------------------------------------------ pomoćno
    def _ensure_row(self, conn, lesson_id: str) -> None:
        conn.execute("INSERT OR IGNORE INTO lesson_progress (lesson_id) VALUES (?)", (lesson_id,))

    def _state(self, key: str) -> str | None:
        row = self._db.query_one("SELECT value FROM app_state WHERE key = ?", (key,))
        return row["value"] if row else None

    def _set_state(self, conn, key: str, value: str | None) -> None:
        conn.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # ------------------------------------------------------------------ trenutna lekcija
    @property
    def current_lesson_id(self) -> str | None:
        return self._state("current_lesson")

    @property
    def last_module_id(self) -> str | None:
        """Poslednji otvoreni modul."""
        return self._state("last_module")

    def set_current_lesson(self, lesson_id: str, module_id: str | None = None) -> None:
        with self._db.transaction() as conn:
            self._set_state(conn, "current_lesson", lesson_id)
            if module_id is not None:
                self._set_state(conn, "last_module", module_id)
            self._ensure_row(conn, lesson_id)
            conn.execute("UPDATE lesson_progress SET last_opened_at = ? WHERE lesson_id = ?",
                         (now_iso(), lesson_id))

    # ------------------------------------------------------------------ završene lekcije
    def is_completed(self, lesson_id: str) -> bool:
        row = self._db.query_one("SELECT completed FROM lesson_progress WHERE lesson_id = ?", (lesson_id,))
        return bool(row and row["completed"])

    def set_completed(self, lesson_id: str, completed: bool = True) -> None:
        with self._db.transaction() as conn:
            self._ensure_row(conn, lesson_id)
            if completed:
                conn.execute(
                    "UPDATE lesson_progress SET completed = 1, "
                    "completed_at = COALESCE(completed_at, ?) WHERE lesson_id = ?",
                    (now_iso(), lesson_id))
            else:
                conn.execute(
                    "UPDATE lesson_progress SET completed = 0, completed_at = NULL WHERE lesson_id = ?",
                    (lesson_id,))

    def completed_ids(self) -> set[str]:
        return {r["lesson_id"] for r in self._db.query_all(
            "SELECT lesson_id FROM lesson_progress WHERE completed = 1")}

    def completed_count(self, among: list[str] | tuple[str, ...] | None = None) -> int:
        done = self.completed_ids()
        return len(done if among is None else done.intersection(among))

    # ------------------------------------------------------------------ zadaci
    def record_attempt(self, lesson_id: str, solved: bool) -> int:
        """Beleži proveru zadatka i vraća ukupan broj provera za lekciju."""
        stamp = now_iso()
        with self._db.transaction() as conn:
            self._ensure_row(conn, lesson_id)
            conn.execute("INSERT INTO check_attempts (lesson_id, passed, created_at) VALUES (?, ?, ?)",
                         (lesson_id, int(solved), stamp))
            if solved:
                conn.execute(
                    "UPDATE lesson_progress SET solved = 1, solved_at = COALESCE(solved_at, ?) "
                    "WHERE lesson_id = ?", (stamp, lesson_id))
        return self.attempts(lesson_id)

    def attempts(self, lesson_id: str) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS n FROM check_attempts WHERE lesson_id = ?", (lesson_id,))
        return int(row["n"]) if row else 0

    def is_solved(self, lesson_id: str) -> bool:
        row = self._db.query_one("SELECT solved FROM lesson_progress WHERE lesson_id = ?", (lesson_id,))
        return bool(row and row["solved"])

    def solved_ids(self) -> set[str]:
        return {r["lesson_id"] for r in self._db.query_all(
            "SELECT lesson_id FROM lesson_progress WHERE solved = 1")}

    def lesson_status(self, lesson_id: str) -> LessonStatus:
        row = self._db.query_one(
            "SELECT solved_at, completed_at, code_saved_at FROM lesson_progress WHERE lesson_id = ?",
            (lesson_id,))
        return LessonStatus(
            attempts=self.attempts(lesson_id),
            solved_at=row["solved_at"] if row else None,
            completed_at=row["completed_at"] if row else None,
            code_saved_at=row["code_saved_at"] if row else None,
        )

    # ------------------------------------------------------------------ sačuvan kod
    def saved_code(self, lesson_id: str) -> str | None:
        row = self._db.query_one("SELECT saved_code FROM lesson_progress WHERE lesson_id = ?", (lesson_id,))
        return row["saved_code"] if row else None

    def save_code(self, lesson_id: str, code: str) -> None:
        with self._db.transaction() as conn:
            self._ensure_row(conn, lesson_id)
            conn.execute("UPDATE lesson_progress SET saved_code = ?, code_saved_at = ? WHERE lesson_id = ?",
                         (code, now_iso(), lesson_id))

    def delete_saved_code(self, lesson_id: str) -> None:
        self._db.execute(
            "UPDATE lesson_progress SET saved_code = NULL, code_saved_at = NULL WHERE lesson_id = ?",
            (lesson_id,))

    # ------------------------------------------------------------------ kvizovi
    def record_quiz(self, lesson_id: str, score: int, total: int, passed: bool) -> QuizRecord:
        """Beleži završen kviz i vraća ažurirane zbirne rezultate."""
        stamp = now_iso()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO quiz_attempts (lesson_id, score, total, passed, created_at) VALUES (?, ?, ?, ?, ?)",
                (lesson_id, score, total, int(passed), stamp))
            conn.execute(
                "INSERT INTO quiz_results (lesson_id, best, last, total, attempts, passed, updated_at) "
                "VALUES (?, ?, ?, ?, 1, ?, ?) "
                "ON CONFLICT(lesson_id) DO UPDATE SET "
                "best = MAX(best, excluded.best), last = excluded.last, total = excluded.total, "
                "attempts = attempts + 1, passed = MAX(passed, excluded.passed), "
                "updated_at = excluded.updated_at",
                (lesson_id, score, score, total, int(passed), stamp))
        record = self.quiz_record(lesson_id)
        assert record is not None
        return record

    def quiz_record(self, lesson_id: str) -> QuizRecord | None:
        row = self._db.query_one(
            "SELECT best, last, total, attempts, passed FROM quiz_results WHERE lesson_id = ?", (lesson_id,))
        if row is None:
            return None
        return QuizRecord(int(row["best"]), int(row["last"]), int(row["total"]),
                          int(row["attempts"]), bool(row["passed"]))

    def passed_quiz_ids(self) -> set[str]:
        return {r["lesson_id"] for r in self._db.query_all(
            "SELECT lesson_id FROM quiz_results WHERE passed = 1")}

    def quiz_history(self, lesson_id: str) -> list[tuple[int, int, bool, str]]:
        """Svi pokušaji kviza lekcije: (rezultat, ukupno, položen, vreme), od najstarijeg."""
        return [(int(r["score"]), int(r["total"]), bool(r["passed"]), r["created_at"])
                for r in self._db.query_all(
                    "SELECT score, total, passed, created_at FROM quiz_attempts "
                    "WHERE lesson_id = ? ORDER BY id", (lesson_id,))]

    # ------------------------------------------------------------------ omiljene lekcije
    def is_favorite(self, lesson_id: str) -> bool:
        return self._db.query_one("SELECT 1 FROM favorites WHERE lesson_id = ?", (lesson_id,)) is not None

    def set_favorite(self, lesson_id: str, favorite: bool = True) -> None:
        if favorite:
            self._db.execute("INSERT OR IGNORE INTO favorites (lesson_id, created_at) VALUES (?, ?)",
                             (lesson_id, now_iso()))
        else:
            self._db.execute("DELETE FROM favorites WHERE lesson_id = ?", (lesson_id,))

    def favorite_ids(self) -> list[str]:
        """Omiljene lekcije, redom kojim su dodate."""
        return [r["lesson_id"] for r in self._db.query_all(
            "SELECT lesson_id FROM favorites ORDER BY created_at, rowid")]

    # ------------------------------------------------------------------ celina
    def has_any_progress(self) -> bool:
        return not (self._db.is_empty("lesson_progress") and self._db.is_empty("quiz_results")
                    and self._db.is_empty("check_attempts"))

    def export_dict(self) -> dict[str, Any]:
        """Sav napredak kao rečnik (za izvoz u JSON)."""
        def rows(sql: str) -> list[dict[str, Any]]:
            return [dict(r) for r in self._db.query_all(sql)]

        return {
            "format": "pyqt6-learning-studio-progress",
            "version": EXPORT_FORMAT_VERSION,
            "exported_at": now_iso(),
            "state": {r["key"]: r["value"] for r in self._db.query_all("SELECT key, value FROM app_state")},
            "lessons": rows("SELECT * FROM lesson_progress ORDER BY lesson_id"),
            "check_attempts": rows("SELECT lesson_id, passed, created_at FROM check_attempts ORDER BY id"),
            "quiz_results": rows("SELECT * FROM quiz_results ORDER BY lesson_id"),
            "quiz_attempts": rows("SELECT lesson_id, score, total, passed, created_at FROM quiz_attempts ORDER BY id"),
            "favorites": rows("SELECT lesson_id, created_at FROM favorites ORDER BY created_at"),
        }

    def export_json(self, target: Path) -> None:
        Path(target).write_text(json.dumps(self.export_dict(), ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")

    def reset_all(self) -> None:
        """Briše sav napredak (podešavanja i omiljene lekcije ostaju)."""
        with self._db.transaction() as conn:
            for table in ("lesson_progress", "check_attempts", "quiz_results", "quiz_attempts", "app_state"):
                conn.execute(f"DELETE FROM {table}")
        log.info("Napredak je obrisan.")

    # ------------------------------------------------------------------ prenos starih podataka
    def import_legacy_json(self, path: Path) -> bool:
        """Prenosi napredak iz ``progress.json`` (Faze 1–3) u bazu.

        Prenos se radi samo ako baza još nema napretka. Posle uspešnog prenosa
        fajl se preimenuje u ``progress.json.migrated`` (ne briše se).

        Returns:
            ``True`` ako je prenos obavljen.
        """
        path = Path(path)
        if not path.exists() or self.has_any_progress():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("očekivan JSON objekat")
        except (OSError, ValueError) as exc:
            log.error("Stari fajl napretka %s ne može da se pročita: %s", path, exc)
            return False

        stamp = now_iso()
        completed = set(data.get("completed", []))
        solved = set(data.get("solved", []))
        attempts: dict[str, int] = {k: int(v) for k, v in data.get("attempts", {}).items()}
        saved_code: dict[str, str] = data.get("saved_code", {})
        quiz: dict[str, dict] = data.get("quiz", {})
        lesson_ids = completed | solved | set(attempts) | set(saved_code)

        with self._db.transaction() as conn:
            for lesson_id in lesson_ids:
                conn.execute(
                    "INSERT INTO lesson_progress (lesson_id, completed, completed_at, solved, solved_at, "
                    "saved_code, code_saved_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (lesson_id,
                     int(lesson_id in completed), stamp if lesson_id in completed else None,
                     int(lesson_id in solved), stamp if lesson_id in solved else None,
                     saved_code.get(lesson_id), stamp if lesson_id in saved_code else None))
                for index in range(attempts.get(lesson_id, 0)):
                    passed = lesson_id in solved and index == attempts[lesson_id] - 1
                    conn.execute(
                        "INSERT INTO check_attempts (lesson_id, passed, created_at) VALUES (?, ?, ?)",
                        (lesson_id, int(passed), stamp))
            for lesson_id, entry in quiz.items():
                conn.execute(
                    "INSERT INTO quiz_results (lesson_id, best, last, total, attempts, passed, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (lesson_id, int(entry.get("best", 0)), int(entry.get("last", 0)),
                     int(entry.get("total", 0)), int(entry.get("attempts", 1)),
                     int(bool(entry.get("passed", False))), stamp))
            if data.get("current_lesson"):
                self._set_state(conn, "current_lesson", str(data["current_lesson"]))

        try:
            path.replace(path.with_name(path.name + ".migrated"))
        except OSError:
            log.warning("Prenos je uspeo, ali %s nije mogao da se preimenuje.", path)
        log.info("Napredak iz %s je prenet u bazu (%d lekcija).", path, len(lesson_ids))
        return True
