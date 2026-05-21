import sqlite3
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema


def test_init_schema_creates_tables(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    expected = {
        "wk_subjects", "wk_assignments", "wk_cache_meta",
        "grammar", "stuck_phrases", "production_attempts",
        "unknown_words", "tool_audit", "walk_state",
    }
    assert expected.issubset(names)


def test_init_schema_is_idempotent(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    init_schema(conn)  # must not raise


def test_grammar_status_check_rejects_bad_value(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    try:
        conn.execute(
            "INSERT INTO grammar (grammar_point, jlpt_level, status) "
            "VALUES ('x', 'N5', 'bogus')"
        )
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected IntegrityError")


def test_walk_state_single_row(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    conn.execute("INSERT INTO walk_state (id) VALUES (1)")
    try:
        conn.execute("INSERT INTO walk_state (id) VALUES (2)")
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected walk_state id=2 to violate CHECK")
