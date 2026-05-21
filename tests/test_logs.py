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


def test_log_attempt_records_grammar_events(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    out = log_production_attempt(
        conn,
        prompt="...", my_answer="...", correct_answer="...",
        verdict="correct",
        grammar_points=["〜ても", "〜ながら"],
    )
    rows = conn.execute(
        "SELECT grammar_point, verdict, attempt_id FROM grammar_practice_events"
    ).fetchall()
    points = {r["grammar_point"] for r in rows}
    assert points == {"〜ても", "〜ながら"}
    assert all(r["attempt_id"] == out["id"] for r in rows)
    assert all(r["verdict"] == "correct" for r in rows)


def test_log_attempt_records_vocabulary_events(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_production_attempt(
        conn,
        prompt="...", my_answer="...", correct_answer="...",
        verdict="incorrect",
        vocabulary=["猫", "犬"],
    )
    rows = conn.execute(
        "SELECT word_form, verdict FROM vocabulary_practice_events"
    ).fetchall()
    words = {r["word_form"] for r in rows}
    assert words == {"猫", "犬"}
    assert all(r["verdict"] == "incorrect" for r in rows)


def test_log_attempt_vocabulary_by_subject_id(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_production_attempt(
        conn,
        prompt="...", my_answer="...", correct_answer="...",
        verdict="correct",
        vocabulary=[42, 99],
    )
    rows = conn.execute(
        "SELECT subject_id, word_form FROM vocabulary_practice_events"
    ).fetchall()
    assert {r["subject_id"] for r in rows} == {42, 99}
    assert all(r["word_form"] is None for r in rows)


def test_log_attempt_per_item_verdicts(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_production_attempt(
        conn,
        prompt="...", my_answer="...", correct_answer="...",
        verdict="partial",
        grammar_points=["〜ても", "〜ながら"],
        per_item_verdicts={"〜ても": "correct", "〜ながら": "incorrect"},
    )
    rows = conn.execute(
        "SELECT grammar_point, verdict FROM grammar_practice_events"
    ).fetchall()
    verdicts = {r["grammar_point"]: r["verdict"] for r in rows}
    assert verdicts == {"〜ても": "correct", "〜ながら": "incorrect"}


def test_log_attempt_no_links_no_events(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_production_attempt(
        conn,
        prompt="...", my_answer="...", correct_answer="...",
        verdict="correct",
    )
    n_g = conn.execute("SELECT COUNT(*) FROM grammar_practice_events").fetchone()[0]
    n_v = conn.execute("SELECT COUNT(*) FROM vocabulary_practice_events").fetchone()[0]
    assert n_g == 0
    assert n_v == 0
