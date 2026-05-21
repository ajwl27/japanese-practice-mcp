from pathlib import Path

import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.grammar import (
    list_known_grammar,
    mark_grammar,
    walk_grammar,
)


def _seed(conn) -> None:
    pts = [
        ("は", "N5"), ("も", "N5"), ("が", "N5"),
        ("ない", "N4"), ("ながら", "N4"),
        ("について", "N3"),
    ]
    for gp, level in pts:
        conn.execute(
            "INSERT INTO grammar (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )


def test_mark_grammar_updates_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = mark_grammar(conn, "は", "known")
    assert out["grammar_point"] == "は"
    assert out["status"] == "known"
    row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point='は'"
    ).fetchone()
    assert row["status"] == "known"


def test_mark_grammar_rejects_bad_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(ValueError, match="status"):
        mark_grammar(conn, "は", "fluent")


def test_mark_grammar_unknown_point_raises(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(LookupError):
        mark_grammar(conn, "もうない", "known")


def test_mark_grammar_with_note(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "ながら", "learning", note="keep practicing")
    row = conn.execute(
        "SELECT note FROM grammar WHERE grammar_point='ながら'"
    ).fetchone()
    assert row["note"] == "keep practicing"


def test_list_known_grammar_filters_by_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "は", "known")
    mark_grammar(conn, "も", "known")
    out = list_known_grammar(conn, status_filter=["known"])
    assert {x["grammar_point"] for x in out} == {"は", "も"}


def test_list_known_grammar_filters_by_level(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = list_known_grammar(conn, level_filter=["N4"])
    assert {x["grammar_point"] for x in out} == {"ない", "ながら"}


def test_walk_grammar_streams_one_at_a_time(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    first = walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    assert first["done"] is False
    assert first["item"]["jlpt_level"] == "N5"
    second = walk_grammar(
        conn, level_filter=["N5"], status_filter=["unknown"], previous_response="k"
    )
    assert second["item"]["grammar_point"] != first["item"]["grammar_point"]
    prev_row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point=?",
        (first["item"]["grammar_point"],),
    ).fetchone()
    assert prev_row["status"] == "known"


def test_walk_grammar_done_when_no_more(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    while True:
        out = walk_grammar(
            conn, level_filter=["N3"], status_filter=["unknown"], previous_response="k"
        )
        if out["done"]:
            break
    row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point='について'"
    ).fetchone()
    assert row["status"] == "known"


def test_walk_grammar_skip_response(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    first = walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    walk_grammar(
        conn, level_filter=["N5"], status_filter=["unknown"], previous_response="s"
    )
    row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point=?",
        (first["item"]["grammar_point"],),
    ).fetchone()
    assert row["status"] == "unknown"
