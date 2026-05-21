import sqlite3
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.migrations import _current_version


V1_SCHEMA = """
CREATE TABLE grammar (
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
CREATE TABLE unknown_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT NOT NULL, context TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE walk_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    filter_hash TEXT, current_grammar_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _create_v1(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(V1_SCHEMA)
    return conn


def test_fresh_db_jumps_to_latest(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    assert _current_version(conn) == 2
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "grammar_seed" in names
    assert "grammar" not in names


def test_v1_db_migrates_grammar_data(tmp_db_path: Path) -> None:
    conn = _create_v1(tmp_db_path)
    conn.execute("INSERT INTO grammar (grammar_point, jlpt_level, status, note) VALUES ('は', 'N5', 'known', 'topic marker')")
    conn.execute("INSERT INTO grammar (grammar_point, jlpt_level) VALUES ('も', 'N5')")
    conn.execute("INSERT INTO grammar (grammar_point, jlpt_level, status) VALUES ('ない', 'N4', 'learning')")

    init_schema(conn)

    seed_rows = {r["grammar_point"]: r["jlpt_level"] for r in conn.execute("SELECT * FROM grammar_seed")}
    assert seed_rows == {"は": "N5", "も": "N5", "ない": "N4"}

    state_rows = {r["grammar_point"]: r["status"] for r in conn.execute("SELECT * FROM grammar_state")}
    assert state_rows == {"は": "known", "ない": "learning"}

    note_row = conn.execute(
        "SELECT note FROM grammar_state WHERE grammar_point = 'は'"
    ).fetchone()
    assert note_row["note"] == "topic marker"


def test_v1_db_migrates_unknown_words(tmp_db_path: Path) -> None:
    conn = _create_v1(tmp_db_path)
    conn.execute("INSERT INTO unknown_words (word, context) VALUES ('紛争', 'news')")

    init_schema(conn)

    row = conn.execute("SELECT word, context, note FROM mined_words").fetchone()
    assert row["word"] == "紛争"
    assert row["context"] == "news"
    assert row["note"] is None
    legacy = conn.execute(
        "SELECT name FROM sqlite_master WHERE name = 'unknown_words'"
    ).fetchone()
    assert legacy is None


def test_migration_is_idempotent(tmp_db_path: Path) -> None:
    conn = _create_v1(tmp_db_path)
    init_schema(conn)
    init_schema(conn)
    assert _current_version(conn) == 2
