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


def test_seed_inserts_grammar_seed_rows(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    inserted = seed_grammar_from_bunpro(conn, seed_file)
    assert inserted == 3
    rows = {r["grammar_point"]: r["jlpt_level"] for r in
            conn.execute("SELECT grammar_point, jlpt_level FROM grammar_seed").fetchall()}
    assert rows == {"は": "N5", "も": "N5", "ない": "N4"}


def test_seed_is_idempotent(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    seed_grammar_from_bunpro(conn, seed_file)
    inserted_second = seed_grammar_from_bunpro(conn, seed_file)
    assert inserted_second == 0
    n = conn.execute("SELECT COUNT(*) FROM grammar_seed").fetchone()[0]
    assert n == 3


def test_seed_does_not_touch_state(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    seed_grammar_from_bunpro(conn, seed_file)
    conn.execute(
        "INSERT INTO grammar_state (grammar_point, status, note) VALUES ('は', 'known', 'topic')"
    )
    seed_grammar_from_bunpro(conn, seed_file)
    row = conn.execute("SELECT status, note FROM grammar_state WHERE grammar_point='は'").fetchone()
    assert row["status"] == "known"
    assert row["note"] == "topic"


def test_default_seed_file_exists() -> None:
    assert DEFAULT_SEED_PATH.exists()
    assert DEFAULT_SEED_PATH.stat().st_size > 1000
