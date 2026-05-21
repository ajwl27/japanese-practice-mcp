from pathlib import Path

import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.logs import (
    log_expression,
    log_mined_word,
    log_production_attempt,
    log_stuck_phrase,
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
        "SELECT prompt, verdict FROM production_attempts"
    ).fetchone()
    assert row["verdict"] == "correct"


def test_log_mined_word(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    out = log_mined_word(conn, word="紛争", context="news headline")
    assert out["id"] >= 1
    row = conn.execute("SELECT word, context FROM mined_words").fetchone()
    assert row["word"] == "紛争"
    assert row["context"] == "news headline"


def test_log_expression(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    out = log_expression(conn, form="足を引っ張る", context="learned from Mariko")
    assert out["id"] >= 1
    row = conn.execute("SELECT form, context FROM expressions").fetchone()
    assert row["form"] == "足を引っ張る"
    assert row["context"] == "learned from Mariko"


def test_log_expression_no_context(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_expression(conn, form="一石二鳥")
    row = conn.execute("SELECT context FROM expressions").fetchone()
    assert row["context"] is None


def test_log_empty_form_rejected(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    with pytest.raises(ValueError):
        log_expression(conn, form="   ")
