import json
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.resolve import resolve_grammar, resolve_vocabulary


def _seed_vocab(conn) -> None:
    for i, (ch, meaning, reading) in enumerate(
        [("猫", "cat", "ねこ"),
         ("食べる", "to eat", "たべる"),
         ("食べ物", "food", "たべもの"),
         ("約束", "promise", "やくそく")],
        start=1,
    ):
        conn.execute(
            "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
            "VALUES (?, 'vocabulary', ?, ?, 1, ?, ?, '{}', '2024-01-01')",
            (i, ch, ch, json.dumps([meaning]), json.dumps([reading])),
        )


def _seed_grammar(conn) -> None:
    for gp, level in [
        ("ば", "N4"),
        ("～ば", "N4"),
        ("ても", "N4"),
        ("について", "N3"),
        ("ながら", "N4"),
    ]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )


def test_resolve_vocab_by_characters_exact(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    out = resolve_vocabulary(conn, "猫")
    assert len(out) == 1
    assert out[0]["characters"] == "猫"


def test_resolve_vocab_by_reading(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    out = resolve_vocabulary(conn, "ねこ")
    assert len(out) == 1
    assert out[0]["characters"] == "猫"


def test_resolve_vocab_by_english(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    out = resolve_vocabulary(conn, "cat")
    assert len(out) == 1
    assert out[0]["characters"] == "猫"


def test_resolve_vocab_ambiguous(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    out = resolve_vocabulary(conn, "食べ")
    chars = {x["characters"] for x in out}
    assert chars == {"食べる", "食べ物"}


def test_resolve_vocab_none(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_vocab(conn)
    assert resolve_vocabulary(conn, "elephant") == []


def test_resolve_grammar_exact(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    out = resolve_grammar(conn, "ながら")
    assert out == ["ながら"]


def test_resolve_grammar_exact_wins_over_substring(tmp_db_path: Path) -> None:
    """When an exact match exists, return only it — don't also surface substring matches."""
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    out = resolve_grammar(conn, "ば")
    assert out == ["ば"]


def test_resolve_grammar_substring_when_no_exact(tmp_db_path: Path) -> None:
    """When no exact match, fall back to substring — surface all candidates."""
    conn = connect(tmp_db_path); init_schema(conn)
    for gp, level in [("～ば", "N4"), ("～ばよかった", "N4")]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )
    out = resolve_grammar(conn, "ば")
    assert set(out) == {"～ば", "～ばよかった"}


def test_resolve_grammar_strips_english_descriptors(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    out = resolve_grammar(conn, "the ても thing")
    assert out == ["ても"]


def test_resolve_grammar_conditional_prefix(tmp_db_path: Path) -> None:
    """'Conditional ば' → 'ば' (after stripping descriptor) → exact match."""
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    out = resolve_grammar(conn, "Conditional ば")
    assert out == ["ば"]


def test_resolve_grammar_none(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    assert resolve_grammar(conn, "Mandarin") == []
