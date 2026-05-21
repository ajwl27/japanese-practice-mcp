import json
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.seed import (
    DEFAULT_SEED_PATH,
    seed_grammar_from_bunpro,
)


SAMPLE = [
    {"term": "は",   "deck_type": "Grammar", "deck_name": "N5"},
    {"term": "も",   "deck_type": "Grammar", "deck_name": "N5"},
    {"term": "丸",   "deck_type": "Vocab",   "deck_name": "N5"},
    {"term": "ない", "deck_type": "Grammar", "deck_name": "N4"},
]


def test_seed_inserts_only_grammar(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    inserted = seed_grammar_from_bunpro(conn, seed_file)
    assert inserted == 3
    rows = conn.execute(
        "SELECT grammar_point, jlpt_level, status FROM grammar ORDER BY grammar_point"
    ).fetchall()
    pairs = [(r["grammar_point"], r["jlpt_level"], r["status"]) for r in rows]
    assert ("は", "N5", "unknown") in pairs
    assert ("ない", "N4", "unknown") in pairs
    assert all(p[0] != "丸" for p in pairs)


def test_seed_is_idempotent(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    seed_grammar_from_bunpro(conn, seed_file)
    inserted_second = seed_grammar_from_bunpro(conn, seed_file)
    assert inserted_second == 0
    n = conn.execute("SELECT COUNT(*) FROM grammar").fetchone()[0]
    assert n == 3


def test_seed_preserves_user_status(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    seed_grammar_from_bunpro(conn, seed_file)
    conn.execute("UPDATE grammar SET status='known' WHERE grammar_point='は'")
    seed_grammar_from_bunpro(conn, seed_file)
    row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point='は'"
    ).fetchone()
    assert row["status"] == "known"


def test_default_seed_file_exists() -> None:
    assert DEFAULT_SEED_PATH.exists()
    assert DEFAULT_SEED_PATH.stat().st_size > 1000
