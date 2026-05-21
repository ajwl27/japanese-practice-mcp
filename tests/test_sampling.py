import json
import random
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.grammar import mark_grammar
from japanese_practice_mcp.tools.sampling import sample_for_prompts


def _seed(conn) -> None:
    for i, (ch, en, srs) in enumerate(
        [("猫", "cat", 5), ("犬", "dog", 7), ("家", "house", 2), ("水", "water", 9)],
        start=1,
    ):
        conn.execute(
            "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
            "VALUES (?, 'vocabulary', ?, ?, 1, ?, ?, '{}', '2024-01-01')",
            (i, ch, ch, json.dumps([en]), json.dumps(["x"])),
        )
        conn.execute(
            "INSERT INTO wk_assignments (id, subject_id, srs_stage, data_json, cached_at) "
            "VALUES (?, ?, ?, '{}', '2024-01-01')",
            (100 + i, i, srs),
        )
    for gp, level in [("は", "N5"), ("も", "N5"), ("ない", "N4")]:
        conn.execute(
            "INSERT INTO grammar (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )
    mark_grammar(conn, "は", "known")
    mark_grammar(conn, "ない", "known")


def test_sample_returns_filtered_items(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = sample_for_prompts(
        conn,
        count=2,
        vocab_filter={"min_srs_stage": 5},
        grammar_filter={"status_filter": ["known"]},
        rng=random.Random(0),
    )
    assert "vocabulary" in out and "grammar" in out
    assert len(out["vocabulary"]) <= 2
    assert len(out["grammar"]) <= 2
    for v in out["vocabulary"]:
        assert v["srs_stage"] >= 5
    for g in out["grammar"]:
        assert g["status"] == "known"


def test_sample_count_caps_results(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = sample_for_prompts(
        conn, count=1,
        vocab_filter={"min_srs_stage": 0},
        grammar_filter={},
        rng=random.Random(0),
    )
    assert len(out["vocabulary"]) == 1
    assert len(out["grammar"]) == 1


def test_sample_deterministic_with_seed(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    a = sample_for_prompts(
        conn, count=3,
        vocab_filter={"min_srs_stage": 0}, grammar_filter={},
        rng=random.Random(42),
    )
    b = sample_for_prompts(
        conn, count=3,
        vocab_filter={"min_srs_stage": 0}, grammar_filter={},
        rng=random.Random(42),
    )
    assert [v["characters"] for v in a["vocabulary"]] == [v["characters"] for v in b["vocabulary"]]
