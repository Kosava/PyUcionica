-- pyqt6_learning_studio/database/schema.sql
-- Šema SQLite baze PyQt6 Learning Studija (verzija 2).
-- Svi CREATE iskazi su idempotentni (IF NOT EXISTS), pa se šema može
-- primeniti pri svakom pokretanju.

-- Metapodaci baze (npr. verzija šeme).
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Napredak po lekciji: završena, rešen zadatak, sačuvan kod.
CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_id      TEXT PRIMARY KEY,
    completed      INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    completed_at   TEXT,
    solved         INTEGER NOT NULL DEFAULT 0 CHECK (solved IN (0, 1)),
    solved_at      TEXT,
    saved_code     TEXT,
    code_saved_at  TEXT,
    last_opened_at TEXT
);

-- Istorija provera zadataka (svaki klik na „Proveri zadatak“).
CREATE TABLE IF NOT EXISTS check_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id  TEXT    NOT NULL,
    passed     INTEGER NOT NULL CHECK (passed IN (0, 1)),
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_check_attempts_lesson ON check_attempts (lesson_id);

-- Zbirni rezultat kviza po lekciji.
CREATE TABLE IF NOT EXISTS quiz_results (
    lesson_id  TEXT PRIMARY KEY,
    best       INTEGER NOT NULL,
    last       INTEGER NOT NULL,
    total      INTEGER NOT NULL,
    attempts   INTEGER NOT NULL,
    passed     INTEGER NOT NULL CHECK (passed IN (0, 1)),
    updated_at TEXT    NOT NULL
);

-- Istorija svih pokušaja kviza.
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id  TEXT    NOT NULL,
    score      INTEGER NOT NULL,
    total      INTEGER NOT NULL,
    passed     INTEGER NOT NULL CHECK (passed IN (0, 1)),
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_lesson ON quiz_attempts (lesson_id);

-- Stanje aplikacije (trenutna lekcija, poslednji modul...).
CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Korisnička podešavanja; vrednosti su JSON tekst.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Verzija 2: omiljene lekcije.
CREATE TABLE IF NOT EXISTS favorites (
    lesson_id  TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
