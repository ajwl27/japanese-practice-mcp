"""Grammar tools.

Personal state lives in `grammar_state` — only marked items have a row there.
Everything not in `grammar_state` is implicitly status='unknown'. This means:

- `mark_grammar` is an UPSERT into grammar_state.
- `list_known_grammar` LEFT JOINs grammar_seed → grammar_state and synthesizes
  the implicit unknown status.
- `walk_grammar` does the same JOIN, applies filters, advances past the
  previously-returned point.
"""
import hashlib
import json
import sqlite3
from typing import Any

from japanese_practice_mcp.resolve import resolve_grammar

VALID_STATUSES = ("learning", "known", "mastered")  # 'unknown' is implicit


def list_known_grammar(
    conn: sqlite3.Connection,
    status_filter: list[str] | None = None,
    level_filter: list[str] | None = None,
    raw: bool = False,
) -> list[dict[str, Any]]:
    """Return grammar points matching the filters.

    By default returns items whose *effective* status (manual ∪ practice) is in
    ("known", "solid", "mastered"). Practice signal of "solid"/"weak" overrides
    the user's self-reported manual status.

    status_filter: filter on effective_status by default; with raw=True applies
      to raw manual_status (treating absent rows as 'unknown').
    level_filter: JLPT levels.
    raw: when True, returns the v0.2 shape with the manual status under "status".
    """
    from japanese_practice_mcp.practice import (
        compute_practice_signal,
        fetch_grammar_events,
        grammar_effective_status,
    )

    where: list[str] = []
    params: list[Any] = []
    if level_filter:
        where.append(f"s.jlpt_level IN ({','.join('?' for _ in level_filter)})")
        params.extend(level_filter)
    sql = (
        "SELECT s.grammar_point, s.jlpt_level, "
        "       COALESCE(st.status, 'unknown') AS manual_status, st.note "
        "FROM grammar_seed s LEFT JOIN grammar_state st USING (grammar_point)"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.jlpt_level DESC, s.grammar_point ASC"
    rows = conn.execute(sql, params).fetchall()

    if raw:
        items = [
            {
                "grammar_point": r["grammar_point"],
                "jlpt_level": r["jlpt_level"],
                "status": r["manual_status"],
                "note": r["note"],
            }
            for r in rows
        ]
        if status_filter:
            items = [i for i in items if i["status"] in status_filter]
        return items

    effective_filter = status_filter or ["known", "solid", "mastered"]
    out: list[dict[str, Any]] = []
    for r in rows:
        gp = r["grammar_point"]
        manual = r["manual_status"] if r["manual_status"] != "unknown" else None
        events = fetch_grammar_events(conn, gp)
        sig = compute_practice_signal(events)
        eff = grammar_effective_status(manual, sig["signal"])
        if eff in effective_filter:
            out.append(
                {
                    "grammar_point": gp,
                    "jlpt_level": r["jlpt_level"],
                    "manual_status": r["manual_status"],
                    "practice_signal": sig["signal"],
                    "effective_status": eff,
                    "note": r["note"],
                }
            )
    return out


def mark_grammar(
    conn: sqlite3.Connection,
    query: str,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Set status (and optional note) for the grammar point resolved from `query`.

    On ambiguous resolution, returns {"resolved": None, "candidates": [...]} without
    writing — caller is expected to disambiguate and retry with the canonical form.
    """
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; must be one of {VALID_STATUSES} "
            "(use the absence of a mark to represent 'unknown')"
        )
    candidates = resolve_grammar(conn, query)
    if not candidates:
        raise LookupError(f"no grammar point found for query {query!r}")
    if len(candidates) > 1:
        return {"resolved": None, "candidates": candidates, "query": query}

    canonical = candidates[0]
    if note is None:
        conn.execute(
            "INSERT INTO grammar_state (grammar_point, status, marked_at) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(grammar_point) DO UPDATE SET "
            "  status=excluded.status, marked_at=datetime('now')",
            (canonical, status),
        )
    else:
        conn.execute(
            "INSERT INTO grammar_state (grammar_point, status, note, marked_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(grammar_point) DO UPDATE SET "
            "  status=excluded.status, note=excluded.note, marked_at=datetime('now')",
            (canonical, status, note),
        )
    row = conn.execute(
        "SELECT s.grammar_point, s.jlpt_level, st.status, st.note "
        "FROM grammar_seed s LEFT JOIN grammar_state st USING (grammar_point) "
        "WHERE s.grammar_point = ?",
        (canonical,),
    ).fetchone()
    return {"resolved": canonical, **dict(row)}


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
) -> dict[str, Any]:
    """Return the next grammar point matching the filters, plus remaining count.

    Stateful: tracks the previously-returned grammar_point so consecutive calls
    advance through the list. Filter change resets the cursor.

    Claude is expected to call `mark_grammar` between walks to record k/l/u/m.
    """
    fh = _filter_hash(level_filter, status_filter)
    state = conn.execute("SELECT * FROM walk_state WHERE id = 1").fetchone()

    advance_past: str | None = None
    if state and state["filter_hash"] == fh and state["last_grammar_point"]:
        advance_past = state["last_grammar_point"]

    where: list[str] = []
    params: list[Any] = []
    if level_filter:
        where.append(f"s.jlpt_level IN ({','.join('?' for _ in level_filter)})")
        params.extend(level_filter)
    if status_filter:
        where.append(
            f"COALESCE(st.status, 'unknown') IN ({','.join('?' for _ in status_filter)})"
        )
        params.extend(status_filter)
    if advance_past is not None:
        where.append("s.grammar_point > ?")
        params.append(advance_past)

    sql = (
        "SELECT s.grammar_point, s.jlpt_level, "
        "       COALESCE(st.status, 'unknown') AS status, st.note "
        "FROM grammar_seed s LEFT JOIN grammar_state st USING (grammar_point)"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.jlpt_level DESC, s.grammar_point ASC LIMIT 1"
    nxt = conn.execute(sql, params).fetchone()

    count_where: list[str] = []
    count_params: list[Any] = []
    if level_filter:
        count_where.append(f"s.jlpt_level IN ({','.join('?' for _ in level_filter)})")
        count_params.extend(level_filter)
    if status_filter:
        count_where.append(
            f"COALESCE(st.status, 'unknown') IN ({','.join('?' for _ in status_filter)})"
        )
        count_params.extend(status_filter)
    count_sql = (
        "SELECT COUNT(*) FROM grammar_seed s "
        "LEFT JOIN grammar_state st USING (grammar_point)"
    )
    if count_where:
        count_sql += " WHERE " + " AND ".join(count_where)
    remaining = conn.execute(count_sql, count_params).fetchone()[0]

    if nxt is None:
        conn.execute(
            "INSERT INTO walk_state (id, filter_hash, last_grammar_point, updated_at) "
            "VALUES (1, ?, NULL, datetime('now')) "
            "ON CONFLICT(id) DO UPDATE SET filter_hash=excluded.filter_hash, "
            "  last_grammar_point=NULL, updated_at=datetime('now')",
            (fh,),
        )
        return {"done": True, "item": None, "remaining": 0}

    conn.execute(
        "INSERT INTO walk_state (id, filter_hash, last_grammar_point, updated_at) "
        "VALUES (1, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET filter_hash=excluded.filter_hash, "
        "  last_grammar_point=excluded.last_grammar_point, updated_at=datetime('now')",
        (fh, nxt["grammar_point"]),
    )
    return {
        "done": False,
        "item": dict(nxt),
        "remaining": remaining,
        "hint": (
            "Generate a fresh example + 1-line explanation for the user, then "
            "call mark_grammar(<grammar_point>, 'known'|'learning'|'mastered') "
            "or skip the mark entirely. Then call walk_grammar again for the next."
        ),
    }
