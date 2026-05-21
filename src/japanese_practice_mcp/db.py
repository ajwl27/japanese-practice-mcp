import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS wk_subjects (
    id           INTEGER PRIMARY KEY,
    object       TEXT NOT NULL,
    characters   TEXT,
    slug         TEXT,
    level        INTEGER,
    meanings     TEXT NOT NULL,
    readings     TEXT NOT NULL,
    data_json    TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wk_subjects_object ON wk_subjects(object);
CREATE INDEX IF NOT EXISTS idx_wk_subjects_characters ON wk_subjects(characters);

CREATE TABLE IF NOT EXISTS wk_assignments (
    id           INTEGER PRIMARY KEY,
    subject_id   INTEGER NOT NULL,
    srs_stage    INTEGER NOT NULL,
    data_json    TEXT NOT NULL,
    cached_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wk_assignments_subject ON wk_assignments(subject_id);
CREATE INDEX IF NOT EXISTS idx_wk_assignments_srs ON wk_assignments(srs_stage);

CREATE TABLE IF NOT EXISTS wk_cache_meta (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grammar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grammar_point TEXT NOT NULL UNIQUE,
    reading       TEXT,
    jlpt_level    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'unknown'
                  CHECK(status IN ('unknown','learning','known','mastered')),
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_grammar_status ON grammar(status);
CREATE INDEX IF NOT EXISTS idx_grammar_level ON grammar(jlpt_level);

CREATE TABLE IF NOT EXISTS stuck_phrases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase      TEXT NOT NULL,
    context     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS production_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt          TEXT NOT NULL,
    my_answer       TEXT NOT NULL,
    correct_answer  TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS unknown_words (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word        TEXT NOT NULL,
    context     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name       TEXT NOT NULL,
    arguments_json  TEXT,
    result_summary  TEXT,
    error           TEXT,
    duration_ms     INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_tool ON tool_audit(tool_name);

CREATE TABLE IF NOT EXISTS walk_state (
    id                  INTEGER PRIMARY KEY CHECK(id = 1),
    filter_hash         TEXT,
    current_grammar_id  INTEGER,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
