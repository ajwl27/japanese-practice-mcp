import sqlite3
from typing import Any

from japanese_practice_mcp.resolve import resolve_vocabulary

VALID_OVERRIDES = ("fading", "struggling", "priority", "buried")


def override_vocabulary(
    conn: sqlite3.Connection,
    query: str,
    override_status: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Override Claude's view of a WK vocabulary item.

    Statuses:
      fading      — slipping out of knowledge; excluded from list_known_vocabulary
      struggling  — chronically wrong; excluded from list_known_vocabulary
      priority    — drill this; included in list_priority_items
      buried      — hide from "known" suggestions
    """
    if override_status not in VALID_OVERRIDES:
        raise ValueError(
            f"invalid override_status {override_status!r}; "
            f"must be one of {VALID_OVERRIDES}"
        )
    candidates = resolve_vocabulary(conn, query)
    if not candidates:
        raise LookupError(f"no vocabulary found for query {query!r}")
    if len(candidates) > 1:
        return {"resolved": None, "candidates": candidates, "query": query}

    target = candidates[0]
    if note is None:
        conn.execute(
            "INSERT INTO wk_overrides (subject_id, override_status, updated_at) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(subject_id) DO UPDATE SET "
            "  override_status=excluded.override_status, updated_at=datetime('now')",
            (target["subject_id"], override_status),
        )
    else:
        conn.execute(
            "INSERT INTO wk_overrides (subject_id, override_status, note, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(subject_id) DO UPDATE SET "
            "  override_status=excluded.override_status, note=excluded.note, "
            "  updated_at=datetime('now')",
            (target["subject_id"], override_status, note),
        )
    return {"resolved": target, "status": override_status, "note": note}
