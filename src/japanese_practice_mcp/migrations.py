"""Schema migration runner.

Migration numbering:
  1 = v0.1 initial schema (legacy)
  2 = v0.2 strip-metadata overhaul (split grammar, rename unknown_words,
       add expressions + wk_overrides)

`run_migrations(conn)` applies any pending migrations. On a fresh DB it goes
straight to the latest target schema (no need to replay history). On a v0.1 DB
it carries existing data forward.
"""
import sqlite3
from typing import Callable

from japanese_practice_mcp.db import SCHEMA_V2


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )


def _current_version(conn: sqlite3.Connection) -> int:
    _ensure_version_table(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def _has_legacy_grammar_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='grammar'"
    ).fetchone()
    if not row:
        return False
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(grammar)").fetchall()}
    return {"reading", "jlpt_level", "status"}.issubset(cols)


def migration_002_strip_metadata(conn: sqlite3.Connection) -> None:
    """v0.1 → v0.2: split grammar, rename unknown_words → mined_words, add new tables."""
    conn.executescript(SCHEMA_V2)

    if _has_legacy_grammar_table(conn):
        conn.execute(
            "INSERT OR IGNORE INTO grammar_seed (grammar_point, jlpt_level) "
            "SELECT grammar_point, jlpt_level FROM grammar"
        )
        conn.execute(
            "INSERT OR IGNORE INTO grammar_state (grammar_point, status, note, marked_at) "
            "SELECT grammar_point, status, note, COALESCE(updated_at, datetime('now')) "
            "FROM grammar WHERE status != 'unknown'"
        )
        conn.execute("DROP TABLE grammar")

    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='unknown_words'"
    ).fetchone()
    if row:
        conn.execute(
            "INSERT INTO mined_words (id, word, context, note, logged_at) "
            "SELECT id, word, context, NULL, created_at FROM unknown_words"
        )
        conn.execute("DROP TABLE unknown_words")

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(walk_state)").fetchall()}
    if "current_grammar_id" in cols:
        conn.execute("DROP TABLE walk_state")
        conn.executescript(SCHEMA_V2)


MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (2, migration_002_strip_metadata),
]


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply all migrations newer than the DB's current version."""
    current = _current_version(conn)
    if current == 0 and not _has_legacy_grammar_table(conn):
        conn.executescript(SCHEMA_V2)
        target = max(v for v, _ in MIGRATIONS)
        conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (target,))
        return
    for version, fn in MIGRATIONS:
        if version > current:
            fn(conn)
            conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (version,))
