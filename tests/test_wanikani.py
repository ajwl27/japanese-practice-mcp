import json
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.wanikani import (
    WaniKaniClient,
    last_synced_at,
    sync_assignments,
    sync_subjects,
)


FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_sync_subjects_pages_through_all(httpx_mock, tmp_db_path: Path) -> None:
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/subjects",
        json=load("wk_subjects_page1.json"),
    )
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/subjects?page_after_id=1",
        json=load("wk_subjects_page2.json"),
    )
    conn = connect(tmp_db_path)
    init_schema(conn)
    client = WaniKaniClient(token="tk")
    n = sync_subjects(conn, client)
    assert n == 2
    rows = conn.execute("SELECT id, characters FROM wk_subjects ORDER BY id").fetchall()
    assert [(r["id"], r["characters"]) for r in rows] == [(1, "猫"), (2, "犬")]


def test_sync_assignments(httpx_mock, tmp_db_path: Path) -> None:
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/assignments?unlocked=true",
        json=load("wk_assignments_page1.json"),
    )
    conn = connect(tmp_db_path)
    init_schema(conn)
    client = WaniKaniClient(token="tk")
    n = sync_assignments(conn, client)
    assert n == 2
    rows = conn.execute(
        "SELECT id, subject_id, srs_stage FROM wk_assignments ORDER BY id"
    ).fetchall()
    assert [(r["id"], r["subject_id"], r["srs_stage"]) for r in rows] == [
        (100, 1, 5),
        (101, 2, 2),
    ]


def test_auth_header_present(httpx_mock, tmp_db_path: Path) -> None:
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/subjects",
        json=load("wk_subjects_page2.json"),
    )
    conn = connect(tmp_db_path)
    init_schema(conn)
    client = WaniKaniClient(token="secret-token")
    sync_subjects(conn, client)
    req = httpx_mock.get_requests()[0]
    assert req.headers["Authorization"] == "Bearer secret-token"


def test_sync_records_synced_at(httpx_mock, tmp_db_path: Path) -> None:
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/subjects",
        json=load("wk_subjects_page2.json"),
    )
    conn = connect(tmp_db_path)
    init_schema(conn)
    client = WaniKaniClient(token="tk")
    sync_subjects(conn, client)
    assert last_synced_at(conn, "subjects") is not None
