"""Bulk operations across personal-state tables."""
import sqlite3
from typing import Any

from japanese_practice_mcp.tools.grammar import VALID_STATUSES

_SAMPLE_SIZE = 10


def _as_list(v: str | list[str] | None) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return list(v)


def bulk_mark_grammar(
    conn: sqlite3.Connection,
    filter: dict[str, Any],
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Set status on every grammar point matching the filter.

    Filter shapes (combine freely):
      {"level": "N5"} or {"level": ["N5", "N4"]}
      {"points": ["〜ても", "〜ながら"]}
      {"except": ["〜たり"]}
      {"current_status": "unknown"}    # only touch points currently in this status
    """
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; must be one of {VALID_STATUSES}"
        )

    levels = _as_list(filter.get("level"))
    points = _as_list(filter.get("points"))
    except_points = _as_list(filter.get("except"))
    current_status = filter.get("current_status")

    where: list[str] = []
    params: list[Any] = []
    if levels:
        where.append(f"s.jlpt_level IN ({','.join('?' for _ in levels)})")
        params.extend(levels)
    if points:
        where.append(f"s.grammar_point IN ({','.join('?' for _ in points)})")
        params.extend(points)
    if except_points:
        where.append(
            f"s.grammar_point NOT IN ({','.join('?' for _ in except_points)})"
        )
        params.extend(except_points)
    if current_status is not None:
        where.append("COALESCE(st.status, 'unknown') = ?")
        params.append(current_status)

    sql = (
        "SELECT s.grammar_point FROM grammar_seed s "
        "LEFT JOIN grammar_state st USING (grammar_point)"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.jlpt_level DESC, s.grammar_point ASC"

    matching = [r["grammar_point"] for r in conn.execute(sql, params).fetchall()]

    for gp in matching:
        if note is None:
            conn.execute(
                "INSERT INTO grammar_state (grammar_point, status, marked_at) "
                "VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(grammar_point) DO UPDATE SET "
                "  status=excluded.status, marked_at=datetime('now')",
                (gp, status),
            )
        else:
            conn.execute(
                "INSERT INTO grammar_state (grammar_point, status, note, marked_at) "
                "VALUES (?, ?, ?, datetime('now')) "
                "ON CONFLICT(grammar_point) DO UPDATE SET "
                "  status=excluded.status, note=excluded.note, "
                "  marked_at=datetime('now')",
                (gp, status, note),
            )

    return {
        "affected": len(matching),
        "sample": matching[:_SAMPLE_SIZE],
        "status": status,
    }
