import json
from pathlib import Path

import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.grammar import mark_grammar
from japanese_practice_mcp.tools.logs import log_production_attempt
from japanese_practice_mcp.tools.overrides import override_vocabulary
from japanese_practice_mcp.tools.status import grammar_status, vocabulary_status


def _seed_grammar(conn) -> None:
    for gp in ["〜ても", "〜ながら", "〜たり"]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, 'N4')", (gp,)
        )


def _seed_vocab(conn) -> None:
    for i, (ch, meaning, reading, srs) in enumerate(
        [("猫", "cat", "ねこ", 5),
         ("犬", "dog", "いぬ", 7)],
        start=1,
    ):
        conn.execute(
            "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
            "VALUES (?, 'vocabulary', ?, ?, 1, ?, ?, '{}', '2024-01-01')",
            (i, ch, ch, json.dumps([meaning]), json.dumps([reading])),
        )
        conn.execute(
            "INSERT INTO wk_assignments (id, subject_id, srs_stage, data_json, cached_at) "
            "VALUES (?, ?, ?, '{}', '2024-01-01')",
            (100 + i, i, srs),
        )


def test_grammar_status_returns_manual_and_signal(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    mark_grammar(conn, "〜ても", "known")
    out = grammar_status(conn, "〜ても")
    assert out["grammar_point"] == "〜ても"
    assert out["manual_status"] == "known"
    assert out["practice_signal"] == "untested"
    assert out["effective_status"] == "known"


def test_grammar_status_practice_overrides_manual(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    mark_grammar(conn, "〜ても", "known")
    for _ in range(3):
        log_production_attempt(
            conn, prompt="x", my_answer="y", correct_answer="z",
            verdict="incorrect", grammar_points=["〜ても"],
        )
    out = grammar_status(conn, "〜ても")
    assert out["manual_status"] == "known"
    assert out["practice_signal"] == "weak"
    assert out["effective_status"] == "weak"
    assert out["failures_30d"] == 3


def test_grammar_status_unknown_query(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    with pytest.raises(LookupError):
        grammar_status(conn, "xyzzy-nonexistent")


def test_vocabulary_status_returns_srs_and_signal(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    out = vocabulary_status(conn, "猫")
    assert out["characters"] == "猫"
    assert out["srs_stage"] == 5
    assert out["override_status"] is None
    assert out["practice_signal"] == "untested"
    assert out["effective_status"] == "known"


def test_vocabulary_status_practice_weak_overrides_srs(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    for _ in range(3):
        log_production_attempt(
            conn, prompt="x", my_answer="y", correct_answer="z",
            verdict="incorrect", vocabulary=["猫"],
        )
    out = vocabulary_status(conn, "猫")
    assert out["srs_stage"] == 5
    assert out["practice_signal"] == "weak"
    assert out["effective_status"] == "weak"


def test_vocabulary_status_returns_override(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    override_vocabulary(conn, "猫", "fading")
    out = vocabulary_status(conn, "猫")
    assert out["override_status"] == "fading"
    assert out["effective_status"] == "fading"
