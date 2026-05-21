import json
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.overrides import override_vocabulary
from japanese_practice_mcp.tools.vocabulary import (
    is_word_known,
    list_known_vocabulary,
)


def _seed(conn) -> None:
    for i, (ch, en, reading, srs) in enumerate(
        [("猫", "cat", "ねこ", 5),
         ("犬", "dog", "いぬ", 7),
         ("家", "house", "いえ", 2),
         ("水", "water", "みず", 9)],
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


def test_list_known_filters_by_srs(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    items = list_known_vocabulary(conn, min_srs_stage=5)
    chars = {x["characters"] for x in items}
    assert chars == {"猫", "犬", "水"}


def test_list_known_excludes_fading(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    override_vocabulary(conn, "猫", "fading")
    items = list_known_vocabulary(conn, min_srs_stage=5)
    chars = {x["characters"] for x in items}
    assert "猫" not in chars
    assert "犬" in chars


def test_list_known_excludes_struggling_and_buried(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    override_vocabulary(conn, "犬", "struggling")
    override_vocabulary(conn, "水", "buried")
    items = list_known_vocabulary(conn, min_srs_stage=5)
    chars = {x["characters"] for x in items}
    assert "犬" not in chars
    assert "水" not in chars
    assert "猫" in chars


def test_list_known_keeps_priority_overrides(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    override_vocabulary(conn, "猫", "priority")
    items = list_known_vocabulary(conn, min_srs_stage=5)
    chars = {x["characters"] for x in items}
    assert "猫" in chars


def test_list_known_limit(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    items = list_known_vocabulary(conn, min_srs_stage=0, limit=1)
    assert len(items) == 1


def test_is_word_known_by_japanese(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "猫")
    assert out["known"] is True
    assert out["matches"][0]["srs_stage"] == 5
    assert out["matches"][0]["override_status"] is None


def test_is_word_known_returns_override(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    override_vocabulary(conn, "猫", "fading")
    out = is_word_known(conn, "猫")
    assert out["matches"][0]["override_status"] == "fading"


def test_is_word_known_by_english(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "dog")
    assert out["known"] is True
    assert out["matches"][0]["characters"] == "犬"


def test_is_word_known_unknown(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "elephant")
    assert out["known"] is False
    assert out["matches"] == []


def test_is_word_known_exact_match_wins(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    conn.execute(
        "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
        "VALUES (5, 'vocabulary', '黒猫', '黒猫', 1, ?, ?, '{}', '2024-01-01')",
        (json.dumps(["black cat"]), json.dumps(["くろねこ"])),
    )
    out = is_word_known(conn, "cat")
    # 'cat' is an EXACT meaning of 猫; should not also surface 黒猫 (which has substring 'cat' in 'black cat')
    assert {m["characters"] for m in out["matches"]} == {"猫"}
