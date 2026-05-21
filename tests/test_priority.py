import json
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.grammar import mark_grammar
from japanese_practice_mcp.tools.logs import log_expression, log_mined_word
from japanese_practice_mcp.tools.overrides import override_vocabulary
from japanese_practice_mcp.tools.priority import list_priority_items


def _seed_vocab(conn) -> None:
    for i, (ch, en, reading, srs) in enumerate(
        [("猫", "cat", "ねこ", 5),
         ("犬", "dog", "いぬ", 7)],
        start=1,
    ):
        conn.execute(
            "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
            "VALUES (?, 'vocabulary', ?, ?, 1, ?, ?, '{}', '2024-01-01')",
            (i, ch, ch, json.dumps([en]), json.dumps([reading])),
        )
        conn.execute(
            "INSERT INTO wk_assignments (id, subject_id, srs_stage, data_json, cached_at) "
            "VALUES (?, ?, ?, '{}', '2024-01-01')",
            (100 + i, i, srs),
        )


def _seed_grammar(conn) -> None:
    for gp, level in [("は", "N5"), ("ながら", "N4"), ("ても", "N4")]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )


def test_priority_includes_wk_priority_overrides(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    override_vocabulary(conn, "猫", "priority", note="working on it")
    out = list_priority_items(conn)
    assert any(
        v["characters"] == "猫" and v["override_status"] == "priority"
        for v in out["vocabulary"]
    )


def test_priority_includes_wk_struggling(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    override_vocabulary(conn, "犬", "struggling")
    out = list_priority_items(conn)
    chars = {v["characters"] for v in out["vocabulary"]}
    assert "犬" in chars


def test_priority_excludes_wk_fading(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    override_vocabulary(conn, "犬", "fading")
    out = list_priority_items(conn)
    chars = {v["characters"] for v in out["vocabulary"]}
    assert "犬" not in chars


def test_priority_includes_learning_grammar(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    mark_grammar(conn, "ながら", "learning")
    out = list_priority_items(conn)
    pts = {g["grammar_point"] for g in out["grammar"]}
    assert "ながら" in pts


def test_priority_excludes_known_grammar(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    mark_grammar(conn, "ても", "known")
    out = list_priority_items(conn)
    pts = {g["grammar_point"] for g in out["grammar"]}
    assert "ても" not in pts


def test_priority_includes_expressions(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_expression(conn, "足を引っ張る", context="from Mariko")
    out = list_priority_items(conn)
    forms = {e["form"] for e in out["expressions"]}
    assert "足を引っ張る" in forms


def test_priority_includes_mined_words(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_mined_word(conn, "紛争", context="headline")
    out = list_priority_items(conn)
    words = {w["word"] for w in out["mined_words"]}
    assert "紛争" in words


def test_priority_includes_practice_weak_grammar(tmp_db_path: Path) -> None:
    from japanese_practice_mcp.tools.logs import log_production_attempt
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    for _ in range(3):
        log_production_attempt(
            conn, prompt="x", my_answer="y", correct_answer="z",
            verdict="incorrect", grammar_points=["は"],
        )
    out = list_priority_items(conn)
    pts = [g for g in out["grammar"] if g["grammar_point"] == "は"]
    assert len(pts) == 1
    assert pts[0]["reason"] == "practice_weak"


def test_priority_includes_practice_weak_vocab(tmp_db_path: Path) -> None:
    from japanese_practice_mcp.tools.logs import log_production_attempt
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    for _ in range(3):
        log_production_attempt(
            conn, prompt="x", my_answer="y", correct_answer="z",
            verdict="incorrect", vocabulary=[1],
        )
    out = list_priority_items(conn)
    vs = [v for v in out["vocabulary"] if v["characters"] == "猫"]
    assert len(vs) == 1
    assert vs[0]["reason"] == "practice_weak"


def test_priority_practice_weak_not_duplicated_with_override(tmp_db_path: Path) -> None:
    from japanese_practice_mcp.tools.logs import log_production_attempt
    from japanese_practice_mcp.tools.overrides import override_vocabulary
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    override_vocabulary(conn, "猫", "struggling")
    for _ in range(3):
        log_production_attempt(
            conn, prompt="x", my_answer="y", correct_answer="z",
            verdict="incorrect", vocabulary=[1],
        )
    out = list_priority_items(conn)
    vs = [v for v in out["vocabulary"] if v["characters"] == "猫"]
    assert len(vs) == 1
    assert vs[0]["reason"] == "override"


def test_priority_count_totals(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn); _seed_grammar(conn)
    override_vocabulary(conn, "猫", "priority")
    mark_grammar(conn, "は", "learning")
    log_expression(conn, "一石二鳥")
    log_mined_word(conn, "紛争")
    out = list_priority_items(conn)
    assert out["total"] == 4
