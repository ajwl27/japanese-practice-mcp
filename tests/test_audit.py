import json
from pathlib import Path

from japanese_practice_mcp.audit import audit
from japanese_practice_mcp.db import connect, init_schema


def test_audit_records_success(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)

    @audit(lambda: conn, "my_tool")
    def my_tool(x: int) -> dict:
        return {"doubled": x * 2}

    out = my_tool(3)
    assert out == {"doubled": 6}
    rows = conn.execute(
        "SELECT tool_name, arguments_json, result_summary, error FROM tool_audit"
    ).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r["tool_name"] == "my_tool"
    assert json.loads(r["arguments_json"]) == {"x": 3}
    assert r["error"] is None
    assert "doubled" in r["result_summary"]


def test_audit_records_exception(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)

    @audit(lambda: conn, "boom_tool")
    def boom(x: int) -> int:
        raise ValueError("nope")

    try:
        boom(7)
    except ValueError:
        pass
    rows = conn.execute(
        "SELECT tool_name, error FROM tool_audit"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "boom_tool"
    assert "nope" in rows[0]["error"]
