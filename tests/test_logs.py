from pathlib import Path

import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.logs import (
    log_production_attempt,
    log_stuck_phrase,
    log_unknown_word,
)


def test_log_stuck_phrase(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    out = log_stuck_phrase(conn, phrase="the dispute escalated", context="news article")
    assert out["id"] >= 1
    row = conn.execute("SELECT phrase, context FROM stuck_phrases").fetchone()
    assert row["phrase"] == "the dispute escalated"
    assert row["context"] == "news article"


def test_log_stuck_phrase_no_context(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_stuck_phrase(conn, phrase="x")
    row = conn.execute("SELECT context FROM stuck_phrases").fetchone()
    assert row["context"] is None


def test_log_production_attempt(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    out = log_production_attempt(
        conn,
        prompt="Say 'I went to the store yesterday'",
        my_answer="昨日店に行きました",
        correct_answer="昨日店に行きました",
        verdict="correct",
    )
    assert out["id"] >= 1
    row = conn.execute(
        "SELECT prompt, my_answer, correct_answer, verdict FROM production_attempts"
    ).fetchone()
    assert row["verdict"] == "correct"


def test_log_unknown_word(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_unknown_word(conn, word="紛争", context="news headline")
    row = conn.execute("SELECT word, context FROM unknown_words").fetchone()
    assert row["word"] == "紛争"
    assert row["context"] == "news headline"


def test_log_empty_phrase_rejected(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    with pytest.raises(ValueError):
        log_stuck_phrase(conn, phrase="   ")
