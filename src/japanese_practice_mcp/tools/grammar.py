import hashlib
import json
import sqlite3
from typing import Any, Literal

VALID_STATUSES = ("unknown", "learning", "known", "mastered")
RESPONSE_TO_STATUS = {"k": "known", "l": "learning", "u": "unknown", "m": "mastered"}


def list_known_grammar(
    conn: sqlite3.Connection,
    status_filter: list[str] | None = None,
    level_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if status_filter:
        where.append(f"status IN ({','.join('?' for _ in status_filter)})")
        params.extend(status_filter)
    if level_filter:
        where.append(f"jlpt_level IN ({','.join('?' for _ in level_filter)})")
        params.extend(level_filter)
    sql = "SELECT grammar_point, reading, jlpt_level, status, note FROM grammar"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY jlpt_level DESC, grammar_point ASC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def mark_grammar(
    conn: sqlite3.Connection,
    grammar_point: str,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; must be one of {VALID_STATUSES}"
        )
    if note is None:
        cur = conn.execute(
            "UPDATE grammar SET status = ?, updated_at = datetime('now') "
            "WHERE grammar_point = ?",
            (status, grammar_point),
        )
    else:
        cur = conn.execute(
            "UPDATE grammar SET status = ?, note = ?, updated_at = datetime('now') "
            "WHERE grammar_point = ?",
            (status, note, grammar_point),
        )
    if cur.rowcount == 0:
        raise LookupError(f"grammar point not found: {grammar_point!r}")
    row = conn.execute(
        "SELECT grammar_point, reading, jlpt_level, status, note FROM grammar "
        "WHERE grammar_point = ?",
        (grammar_point,),
    ).fetchone()
    return dict(row)


def _filter_hash(level_filter: list[str] | None, status_filter: list[str] | None) -> str:
    payload = json.dumps(
        {"level": sorted(level_filter or []), "status": sorted(status_filter or [])},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def walk_grammar(
    conn: sqlite3.Connection,
    level_filter: list[str] | None = None,
    status_filter: list[str] | None = None,
    previous_response: Literal["k", "l", "u", "m", "s"] | None = None,
) -> dict[str, Any]:
    """Stream one grammar point at a time for bulk-marking.

    Stateful via the `walk_state` table. If `previous_response` is supplied and
    the state row's current_grammar_id is set, the previous point's status is
    updated (unless response is 's' = skip).
    """
    fh = _filter_hash(level_filter, status_filter)
    state = conn.execute("SELECT * FROM walk_state WHERE id = 1").fetchone()

    if previous_response and state and state["filter_hash"] == fh and state["current_grammar_id"]:
        if previous_response != "s":
            new_status = RESPONSE_TO_STATUS.get(previous_response)
            if new_status is None:
                raise ValueError(
                    f"invalid previous_response {previous_response!r}; expected one of k/l/u/m/s"
                )
            conn.execute(
                "UPDATE grammar SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (new_status, state["current_grammar_id"]),
            )

    where: list[str] = []
    params: list[Any] = []
    if level_filter:
        where.append(f"jlpt_level IN ({','.join('?' for _ in level_filter)})")
        params.extend(level_filter)
    if status_filter:
        where.append(f"status IN ({','.join('?' for _ in status_filter)})")
        params.extend(status_filter)
    sql = "SELECT id, grammar_point, reading, jlpt_level, status, note FROM grammar"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY jlpt_level DESC, id ASC LIMIT 1"
    nxt = conn.execute(sql, params).fetchone()

    if nxt is None:
        conn.execute(
            "INSERT INTO walk_state (id, filter_hash, current_grammar_id, updated_at) "
            "VALUES (1, ?, NULL, datetime('now')) "
            "ON CONFLICT(id) DO UPDATE SET filter_hash=excluded.filter_hash, "
            "current_grammar_id=NULL, updated_at=datetime('now')",
            (fh,),
        )
        return {"done": True, "item": None, "remaining_estimate": 0}

    conn.execute(
        "INSERT INTO walk_state (id, filter_hash, current_grammar_id, updated_at) "
        "VALUES (1, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET filter_hash=excluded.filter_hash, "
        "current_grammar_id=excluded.current_grammar_id, updated_at=datetime('now')",
        (fh, nxt["id"]),
    )
    count_sql = "SELECT COUNT(*) FROM grammar"
    if where:
        count_sql += " WHERE " + " AND ".join(where)
    remaining = conn.execute(count_sql, params).fetchone()[0]
    return {
        "done": False,
        "item": {
            "grammar_point": nxt["grammar_point"],
            "reading": nxt["reading"],
            "jlpt_level": nxt["jlpt_level"],
            "status": nxt["status"],
            "note": nxt["note"],
        },
        "remaining_estimate": remaining,
        "hint": "Respond with previous_response='k' (known), 'l' (learning), 'u' (unknown), 'm' (mastered), or 's' (skip).",
    }
