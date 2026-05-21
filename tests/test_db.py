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
        "grammar_seed", "grammar_state",
        "expressions", "mined_words", "wk_overrides",
        "stuck_phrases", "production_attempts",
        "tool_audit", "walk_state", "schema_version",
    }
    assert expected.issubset(names), f"missing: {expected - names}"
    assert "grammar" not in names, "legacy grammar table should not exist"
    assert "unknown_words" not in names, "legacy unknown_words table should not exist"


def test_init_schema_is_idempotent(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    init_schema(conn)


def test_grammar_state_status_check(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    conn.execute("INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES ('x', 'N5')")
    try:
        conn.execute("INSERT INTO grammar_state (grammar_point, status) VALUES ('x', 'bogus')")
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected IntegrityError on bad status")


def test_wk_override_status_check(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    try:
        conn.execute(
            "INSERT INTO wk_overrides (subject_id, override_status) VALUES (1, 'bogus')"
        )
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected IntegrityError on bad override_status")
