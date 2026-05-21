import json
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.vocabulary import (
    is_word_known,
    list_known_vocabulary,
)


def _seed(conn) -> None:
    conn.execute(
        "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
        "VALUES (1, 'vocabulary', '猫', 'neko', 2, ?, ?, '{}', '2024-01-01')",
        (json.dumps(["cat"]), json.dumps(["ねこ"])),
    )
    conn.execute(
        "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
        "VALUES (2, 'vocabulary', '犬', 'inu', 2, ?, ?, '{}', '2024-01-01')",
        (json.dumps(["dog"]), json.dumps(["いぬ"])),
    )
    conn.execute(
        "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
        "VALUES (3, 'kanji', '猫', 'neko-kanji', 2, ?, ?, '{}', '2024-01-01')",
        (json.dumps(["cat"]), json.dumps(["ねこ"])),
    )
    conn.execute(
        "INSERT INTO wk_assignments (id, subject_id, srs_stage, data_json, cached_at) "
        "VALUES (100, 1, 5, '{}', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO wk_assignments (id, subject_id, srs_stage, data_json, cached_at) "
        "VALUES (101, 2, 2, '{}', '2024-01-01')"
    )


def test_list_known_vocab_filters_by_srs(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    items = list_known_vocabulary(conn, min_srs_stage=5)
    assert len(items) == 1
    assert items[0]["characters"] == "猫"
    assert items[0]["srs_stage"] == 5


def test_list_known_vocab_excludes_lower_srs(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    items = list_known_vocabulary(conn, min_srs_stage=2)
    assert {i["characters"] for i in items} == {"猫", "犬"}


def test_list_known_vocab_limit(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    items = list_known_vocabulary(conn, min_srs_stage=0, limit=1)
    assert len(items) == 1


def test_is_word_known_by_japanese(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "猫")
    assert out["known"] is True
    assert out["srs_stage"] == 5


def test_is_word_known_by_english(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "dog")
    assert out["known"] is True
    assert out["srs_stage"] == 2


def test_is_word_unknown(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "elephant")
    assert out["known"] is False
    assert out["srs_stage"] is None
