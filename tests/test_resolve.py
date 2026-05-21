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
    """When the query exact-matches one entry, return only it — substring matches are excluded."""
    conn = connect(tmp_db_path); init_schema(conn)
    for gp in ["〜て", "〜てもいい", "〜てから"]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, 'N4')", (gp,)
        )
    out = resolve_grammar(conn, "て")
    assert out == ["〜て"]


def test_resolve_grammar_substring_when_no_exact(tmp_db_path: Path) -> None:
    """When no exact match, fall back to substring — surface all candidates."""
    conn = connect(tmp_db_path); init_schema(conn)
    for gp in ["〜ばよかった", "〜ばと思う"]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, 'N3')", (gp,)
        )
    out = resolve_grammar(conn, "ばよ")
    assert out == ["〜ばよかった"]


def test_resolve_grammar_multiple_tilde_equivalents_are_all_exact(tmp_db_path: Path) -> None:
    """If seed has BOTH 'ば' and '〜ば', querying 'ば' returns both — tilde is ignored
    in the match key, so they are equivalent exact matches and Claude must disambiguate.
    """
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    out = resolve_grammar(conn, "ば")
    assert set(out) == {"ば", "～ば"}


def test_resolve_grammar_strips_english_descriptors(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    out = resolve_grammar(conn, "the ても thing")
    assert out == ["ても"]


def test_resolve_grammar_conditional_prefix(tmp_db_path: Path) -> None:
    """'Conditional ば' → 'ば' (after stripping descriptor). Both 'ば' and '～ば'
    are tilde-equivalent exact matches in this seed.
    """
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    out = resolve_grammar(conn, "Conditional ば")
    assert set(out) == {"ば", "～ば"}


def test_resolve_grammar_none(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed_grammar(conn)
    assert resolve_grammar(conn, "Mandarin") == []


def test_resolve_grammar_exact_wins_against_substring_matches(tmp_db_path: Path) -> None:
    """When the query exact-matches one seed entry AND substring-matches others,
    return only the exact match. This is the v0.3 bug fix.
    """
    conn = connect(tmp_db_path); init_schema(conn)
    for gp in ["〜て", "〜てもいい", "〜て + B", "Verb + て + Verb"]:
        conn.execute(
            "INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, 'N4')", (gp,)
        )
    out = resolve_grammar(conn, "Verb + て")
    assert out == ["〜て"]


def test_resolve_grammar_tilde_prefix_tolerant(tmp_db_path: Path) -> None:
    """Querying without the leading 〜 should still match an entry that has it."""
    conn = connect(tmp_db_path); init_schema(conn)
    conn.execute("INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES ('〜ても', 'N4')")
    out = resolve_grammar(conn, "ても")
    assert out == ["〜ても"]


def test_resolve_grammar_whitespace_tolerant(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    conn.execute("INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES ('〜ても', 'N4')")
    out = resolve_grammar(conn, "  ても  ")
    assert out == ["〜ても"]


def test_resolve_grammar_nfkc_half_width_tilde(tmp_db_path: Path) -> None:
    """Half-width tilde (～, U+FF5E) and wave-dash (〜, U+301C) should be equivalent."""
    conn = connect(tmp_db_path); init_schema(conn)
    conn.execute("INSERT INTO grammar_seed (grammar_point, jlpt_level) VALUES ('〜ても', 'N4')")
    out = resolve_grammar(conn, "～ても")
    assert out == ["〜ても"]
