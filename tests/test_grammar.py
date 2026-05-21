from pathlib import Path

import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.grammar import (
    list_known_grammar,
    mark_grammar,
    walk_grammar,
)


def _seed(conn) -> None:
    for gp, level in [
        ("は", "N5"), ("も", "N5"), ("が", "N5"),
        ("ない", "N4"), ("ながら", "N4"), ("ても", "N4"),
        ("について", "N3"),
    ]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )


def test_mark_grammar_exact_match(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = mark_grammar(conn, "は", "known")
    assert out["resolved"] == "は"
    assert out["status"] == "known"
    row = conn.execute(
        "SELECT status FROM grammar_state WHERE grammar_point='は'"
    ).fetchone()
    assert row["status"] == "known"


def test_mark_grammar_fuzzy_match(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = mark_grammar(conn, "the ても thing", "learning")
    assert out["resolved"] == "ても"
    row = conn.execute(
        "SELECT status FROM grammar_state WHERE grammar_point='ても'"
    ).fetchone()
    assert row["status"] == "learning"


def test_mark_grammar_ambiguous_returns_candidates(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    # No exact match for "たり" — only substring matches.
    # (Note: '〜たり' as a single entry WOULD be a tilde-equivalent exact match, so
    #  for true ambiguity we use two entries where 'たり' is only a substring.)
    conn.execute("INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES ('〜たりする', 'N4')")
    conn.execute("INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES ('〜たり〜たり', 'N4')")
    out = mark_grammar(conn, "たり", "learning")
    assert out["resolved"] is None
    assert set(out["candidates"]) == {"〜たりする", "〜たり〜たり"}
    n = conn.execute("SELECT COUNT(*) FROM grammar_state").fetchone()[0]
    assert n == 0


def test_mark_grammar_no_match_raises(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(LookupError):
        mark_grammar(conn, "completely-unknown-term", "known")


def test_mark_grammar_rejects_bad_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(ValueError, match="status"):
        mark_grammar(conn, "は", "fluent")


def test_mark_grammar_with_note(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "ながら", "learning", note="keep practicing")
    row = conn.execute(
        "SELECT note FROM grammar_state WHERE grammar_point='ながら'"
    ).fetchone()
    assert row["note"] == "keep practicing"


def test_mark_grammar_upsert(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "は", "learning")
    mark_grammar(conn, "は", "known", note="now solid")
    row = conn.execute(
        "SELECT status, note FROM grammar_state WHERE grammar_point='は'"
    ).fetchone()
    assert row["status"] == "known"
    assert row["note"] == "now solid"


def test_list_known_grammar_returns_all_with_implicit_unknown(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "は", "known")
    out = list_known_grammar(conn)
    by_gp = {x["grammar_point"]: x for x in out}
    assert by_gp["は"]["status"] == "known"
    assert by_gp["も"]["status"] == "unknown"
    assert by_gp["も"]["note"] is None
    assert by_gp["も"]["jlpt_level"] == "N5"


def test_list_known_grammar_filters_by_status_including_implicit(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "は", "known")
    out = list_known_grammar(conn, status_filter=["unknown"])
    points = {x["grammar_point"] for x in out}
    assert "は" not in points
    assert "も" in points


def test_list_known_grammar_filters_by_level(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = list_known_grammar(conn, level_filter=["N4"])
    assert {x["grammar_point"] for x in out} == {"ない", "ながら", "ても"}


def test_walk_grammar_streams_one_at_a_time(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    first = walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    assert first["done"] is False
    assert first["item"]["jlpt_level"] == "N5"
    assert "remaining" in first
    second = walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    assert second["done"] is False
    assert second["item"]["grammar_point"] != first["item"]["grammar_point"]


def test_walk_grammar_returns_marked_item_after_status_change(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    first = walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    mark_grammar(conn, first["item"]["grammar_point"], "known")
    second = walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    assert second["item"]["grammar_point"] != first["item"]["grammar_point"]


def test_walk_grammar_done(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "について", "known")
    out = walk_grammar(conn, level_filter=["N3"], status_filter=["unknown"])
    assert out["done"] is True
    assert out["item"] is None
    assert out["remaining"] == 0


def test_walk_grammar_filter_change_resets(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    n4_first = walk_grammar(conn, level_filter=["N4"], status_filter=["unknown"])
    assert n4_first["item"]["jlpt_level"] == "N4"
