import sqlite3
from pathlib import Path

SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wk_subjects (
    id INTEGER PRIMARY KEY, object TEXT NOT NULL, characters TEXT, slug TEXT,
    level INTEGER, meanings TEXT NOT NULL, readings TEXT NOT NULL,
    data_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wk_subjects_object ON wk_subjects(object);
CREATE INDEX IF NOT EXISTS idx_wk_subjects_characters ON wk_subjects(characters);

CREATE TABLE IF NOT EXISTS wk_assignments (
    id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, srs_stage INTEGER NOT NULL,
    data_json TEXT NOT NULL, cached_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wk_assignments_subject ON wk_assignments(subject_id);
CREATE INDEX IF NOT EXISTS idx_wk_assignments_srs ON wk_assignments(srs_stage);

CREATE TABLE IF NOT EXISTS wk_cache_meta (
    key TEXT PRIMARY KEY, value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grammar_seed (
    grammar_point TEXT PRIMARY KEY,
    jlpt_level    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grammar_seed_level ON grammar_seed(jlpt_level);

CREATE TABLE IF NOT EXISTS grammar_state (
    grammar_point TEXT PRIMARY KEY,
    status        TEXT NOT NULL CHECK(status IN ('learning','known','mastered')),
    note          TEXT,
    marked_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_grammar_state_status ON grammar_state(status);

CREATE TABLE IF NOT EXISTS expressions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    form      TEXT NOT NULL,
    context   TEXT,
    note      TEXT,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mined_words (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    word      TEXT NOT NULL,
    context   TEXT,
    note      TEXT,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wk_overrides (
    subject_id      INTEGER PRIMARY KEY,
    override_status TEXT NOT NULL CHECK(override_status IN ('fading','struggling','priority','buried')),
    note            TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stuck_phrases (
    id INTEGER PRIMARY KEY AUTOINCREMENT, phrase TEXT NOT NULL, context TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS production_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL, my_answer TEXT NOT NULL,
    correct_answer TEXT NOT NULL, verdict TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL, arguments_json TEXT, result_summary TEXT,
    error TEXT, duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_tool ON tool_audit(tool_name);

CREATE TABLE IF NOT EXISTS walk_state (
    id                  INTEGER PRIMARY KEY CHECK(id = 1),
    filter_hash         TEXT,
    last_grammar_point  TEXT,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grammar_practice_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grammar_point TEXT NOT NULL,
    attempt_id    INTEGER NOT NULL,
    verdict       TEXT NOT NULL,
    attempted_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (attempt_id) REFERENCES production_attempts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gpe_point_time ON grammar_practice_events(grammar_point, attempted_at);

CREATE TABLE IF NOT EXISTS vocabulary_practice_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id   INTEGER,
    word_form    TEXT,
    attempt_id   INTEGER NOT NULL,
    verdict      TEXT NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (attempt_id) REFERENCES production_attempts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_vpe_subject_time ON vocabulary_practice_events(subject_id, attempted_at);
CREATE INDEX IF NOT EXISTS idx_vpe_word_time ON vocabulary_practice_events(word_form, attempted_at);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Apply pending migrations. Idempotent. Use this in all new code."""
    from japanese_practice_mcp.migrations import run_migrations
    run_migrations(conn)
