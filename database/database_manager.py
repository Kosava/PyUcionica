# pyqt6_learning_studio/database/database_manager.py
"""Otvaranje SQLite baze, primena šeme, transakcije, rezervne kopije i oporavak.

Ostatak aplikacije ne piše SQL za kreiranje tabela niti brine o verziji šeme —
to radi ova klasa. Ako je fajl baze oštećen, premešta se u rezervni fajl
(``*.corrupt-<vreme>``) i pravi se nova, prazna baza; aplikacija tada može da
obavesti korisnika (vidi :attr:`DatabaseManager.recovered_from`).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 2
"""Istorija verzija šeme:

1. Faza 4 — napredak, provere, kvizovi, stanje, podešavanja.
2. Faza 5 — tabela ``favorites`` (omiljene lekcije).

Sve tabele se prave sa ``CREATE TABLE IF NOT EXISTS``, pa se nadogradnja sa
starije verzije svodi na ponovno izvršavanje šeme. Izmene postojećih tabela
(ALTER TABLE) dodavale bi se u :meth:`DatabaseManager._apply_schema`.
"""


def now_iso() -> str:
    """Trenutno lokalno vreme u ISO formatu, na sekund (npr. 2026-10-30T07:46:12)."""
    return datetime.now().isoformat(timespec="seconds")


class DatabaseError(RuntimeError):
    """Greška koju aplikacija može da prikaže korisniku."""


class DatabaseManager:
    """Veza ka SQLite bazi.

    Args:
        path: Putanja do fajla baze; ``":memory:"`` za bazu u memoriji (testovi).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = path if path == ":memory:" else Path(path)
        self.recovered_from: Path | None = None
        self._conn = self._open()

    # ------------------------------------------------------------------ otvaranje
    def _connect(self) -> sqlite3.Connection:
        if isinstance(self._path, Path):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _open(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = None
        try:
            conn = self._connect()
            result = conn.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                raise sqlite3.DatabaseError(f"quick_check: {result}")
            self._apply_schema(conn)
            return conn
        except (sqlite3.DatabaseError, DatabaseError) as exc:
            if conn is not None:
                conn.close()
            if isinstance(exc, DatabaseError):
                raise
            if not isinstance(self._path, Path) or not self._path.exists():
                raise DatabaseError(f"Baza ne može da se otvori: {exc}") from exc
            backup = self._path.with_name(
                f"{self._path.name}.corrupt-{datetime.now():%Y%m%d-%H%M%S}")
            log.error("Baza %s je oštećena (%s) — premeštam je u %s i pravim novu.",
                      self._path, exc, backup)
            self._path.replace(backup)
            for suffix in ("-wal", "-shm", "-journal"):
                extra = self._path.with_name(self._path.name + suffix)
                if extra.exists():
                    extra.unlink()
            self.recovered_from = backup
            conn = self._connect()
            self._apply_schema(conn)
            return conn

    def _apply_schema(self, conn: sqlite3.Connection) -> None:
        version = self._schema_version(conn)
        if version > SCHEMA_VERSION:
            raise DatabaseError(
                f"Baza je napravljena novijom verzijom aplikacije (šema {version}, "
                f"ova aplikacija podržava {SCHEMA_VERSION}). Ažuriraj aplikaciju.")
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        if 0 < version < SCHEMA_VERSION:
            log.info("Baza je nadograđena sa verzije šeme %d na %d.", version, SCHEMA_VERSION)
        with conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )
            conn.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('created_at', ?)", (now_iso(),))

    @staticmethod
    def _schema_version(conn: sqlite3.Connection) -> int:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
        if not exists:
            return 0
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------ upiti
    @property
    def path(self) -> Path | str:
        return self._path

    @property
    def schema_version(self) -> int:
        return self._schema_version(self._conn)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Izvršava jedan iskaz u sopstvenoj transakciji."""
        with self._conn:
            return self._conn.execute(sql, params)

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Više iskaza kao jedna celina: ili se izvrše svi, ili nijedan."""
        with self._conn:
            yield self._conn

    def is_empty(self, table: str) -> bool:
        if not table.isidentifier():
            raise ValueError(f"Neispravan naziv tabele: {table!r}")
        return self._conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is None

    # ------------------------------------------------------------------ održavanje
    def backup_to(self, target: Path) -> None:
        """Pravi doslednu kopiju cele baze u ``target`` (radi i dok je baza otvorena)."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        dest = sqlite3.connect(str(target))
        try:
            self._conn.backup(dest)
        finally:
            dest.close()

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            log.exception("Greška pri zatvaranju baze.")

    def __enter__(self) -> "DatabaseManager":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
