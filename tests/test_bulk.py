from pathlib import Path

import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.bulk import bulk_mark_grammar
from japanese_practice_mcp.tools.grammar import mark_grammar


def _seed(conn) -> None:
    for gp, level in [
        ("は", "N5"), ("も", "N5"), ("が", "N5"),
        ("ない", "N4"), ("ながら", "N4"), ("ても", "N4"),
        ("について", "N3"), ("にとって", "N3"),
    ]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )


def test_bulk_mark_by_single_level(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = bulk_mark_grammar(conn, {"level": "N5"}, "known")
    assert out["affected"] == 3
    rows = conn.execute(
        "SELECT grammar_point FROM grammar_state WHERE status='known'"
    ).fetchall()
    assert {r["grammar_point"] for r in rows} == {"は", "も", "が"}


def test_bulk_mark_by_level_list(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = bulk_mark_grammar(conn, {"level": ["N5", "N4"]}, "known")
    assert out["affected"] == 6


def test_bulk_mark_by_explicit_points(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = bulk_mark_grammar(conn, {"points": ["は", "も"]}, "learning")
    assert out["affected"] == 2
    statuses = {r["grammar_point"]: r["status"]
                for r in conn.execute("SELECT grammar_point, status FROM grammar_state")}
    assert statuses == {"は": "learning", "も": "learning"}


def test_bulk_mark_level_with_except(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = bulk_mark_grammar(conn, {"level": "N5", "except": ["も"]}, "known")
    assert out["affected"] == 2
    rows = conn.execute(
        "SELECT grammar_point FROM grammar_state"
    ).fetchall()
    assert {r["grammar_point"] for r in rows} == {"は", "が"}


def test_bulk_mark_filter_by_current_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "は", "learning")
    out = bulk_mark_grammar(
        conn,
        {"current_status": "unknown", "level": "N5"},
        "known",
    )
    assert out["affected"] == 2
    row = conn.execute(
        "SELECT status FROM grammar_state WHERE grammar_point='は'"
    ).fetchone()
    assert row["status"] == "learning"


def test_bulk_mark_returns_sample(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = bulk_mark_grammar(conn, {"level": "N5"}, "known")
    assert isinstance(out["sample"], list)
    assert set(out["sample"]) <= {"は", "も", "が"}


def test_bulk_mark_rejects_bad_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(ValueError):
        bulk_mark_grammar(conn, {"level": "N5"}, "fluent")


def test_bulk_mark_no_matches(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = bulk_mark_grammar(conn, {"level": "N0"}, "known")
    assert out["affected"] == 0
    assert out["sample"] == []
