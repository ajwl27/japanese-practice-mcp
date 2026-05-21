import json
from pathlib import Path

import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.overrides import override_vocabulary


def _seed(conn) -> None:
    for i, (ch, meaning, reading) in enumerate(
        [("猫", "cat", "ねこ"),
         ("食べる", "to eat", "たべる"),
         ("食べ物", "food", "たべもの")],
        start=1,
    ):
        conn.execute(
            "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
            "VALUES (?, 'vocabulary', ?, ?, 1, ?, ?, '{}', '2024-01-01')",
            (i, ch, ch, json.dumps([meaning]), json.dumps([reading])),
        )


def test_override_exact_japanese(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = override_vocabulary(conn, "猫", "fading")
    assert out["resolved"]["characters"] == "猫"
    assert out["status"] == "fading"
    row = conn.execute(
        "SELECT override_status FROM wk_overrides WHERE subject_id = 1"
    ).fetchone()
    assert row["override_status"] == "fading"


def test_override_by_meaning(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = override_vocabulary(conn, "cat", "priority")
    assert out["resolved"]["characters"] == "猫"


def test_override_ambiguous_returns_candidates(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = override_vocabulary(conn, "食べ", "struggling")
    assert out["resolved"] is None
    chars = {c["characters"] for c in out["candidates"]}
    assert chars == {"食べる", "食べ物"}
    n = conn.execute("SELECT COUNT(*) FROM wk_overrides").fetchone()[0]
    assert n == 0


def test_override_upsert(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    override_vocabulary(conn, "猫", "fading")
    override_vocabulary(conn, "猫", "priority", note="working on it")
    row = conn.execute(
        "SELECT override_status, note FROM wk_overrides WHERE subject_id = 1"
    ).fetchone()
    assert row["override_status"] == "priority"
    assert row["note"] == "working on it"


def test_override_bad_status_rejected(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(ValueError, match="override_status"):
        override_vocabulary(conn, "猫", "bogus")


def test_override_no_match_raises(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(LookupError):
        override_vocabulary(conn, "xyzzy", "fading")
