from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.bulk import bulk_mark_grammar
from japanese_practice_mcp.tools.calibration import quick_calibration


def _seed(conn) -> None:
    pts = [(f"p{i}", "N5") for i in range(50)] + [(f"q{i}", "N4") for i in range(40)]
    for gp, level in pts:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )


def test_calibration_signals_needed_when_cold(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = quick_calibration(conn)
    assert out["needs_calibration"] is True
    assert out["current_state"]["total_grammar_points"] == 90
    assert out["current_state"]["marked_count"] == 0
    assert len(out["suggested_actions"]) >= 2
    assert "message" in out


def test_calibration_signals_not_needed_when_warm(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    bulk_mark_grammar(conn, {"level": ["N5", "N4"]}, "known")
    out = quick_calibration(conn)
    assert out["needs_calibration"] is False


def test_calibration_counts_by_level(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = quick_calibration(conn)
    by_level = out["current_state"]["by_level"]
    assert by_level["N5"] == 50
    assert by_level["N4"] == 40


def test_calibration_suggestions_use_bulk_mark(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = quick_calibration(conn)
    for action in out["suggested_actions"]:
        for call in action["calls"]:
            assert call["tool"] == "bulk_mark_grammar"
