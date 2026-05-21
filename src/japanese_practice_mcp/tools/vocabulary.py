import json
import sqlite3
from typing import Any

from japanese_practice_mcp.resolve import resolve_vocabulary

# Override statuses that mean "don't surface this as known"
HIDE_FROM_KNOWN = ("fading", "struggling", "buried")


def list_known_vocabulary(
    conn: sqlite3.Connection,
    min_srs_stage: int = 5,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Return WK vocab at or above the given SRS stage, excluding overrides
    marked fading/struggling/buried AND items with practice_signal='weak'.
    """
    from japanese_practice_mcp.practice import (
        compute_practice_signal,
        fetch_vocabulary_events,
    )

    placeholders = ",".join("?" for _ in HIDE_FROM_KNOWN)
    cur = conn.execute(
        f"""
        SELECT s.id, s.characters, s.meanings, s.readings, s.level, a.srs_stage,
               o.override_status
        FROM wk_subjects s
        JOIN wk_assignments a ON a.subject_id = s.id
        LEFT JOIN wk_overrides o ON o.subject_id = s.id
        WHERE s.object = 'vocabulary'
          AND a.srs_stage >= ?
          AND (o.override_status IS NULL OR o.override_status NOT IN ({placeholders}))
        ORDER BY a.srs_stage DESC, s.level ASC, s.id ASC
        LIMIT ?
        """,
        (min_srs_stage, *HIDE_FROM_KNOWN, limit),
    )
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        events = fetch_vocabulary_events(
            conn, subject_id=r["id"], word_form=r["characters"]
        )
        sig = compute_practice_signal(events)
        if sig["signal"] == "weak":
            continue
        out.append(
            {
                "subject_id": r["id"],
                "characters": r["characters"],
                "meanings": json.loads(r["meanings"]),
                "readings": json.loads(r["readings"]),
                "level": r["level"],
                "srs_stage": r["srs_stage"],
                "override_status": r["override_status"],
                "practice_signal": sig["signal"],
            }
        )
    return out


def is_word_known(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    """Resolve `query` via fuzzy match; return all candidates with their SRS
    stage and override status.

    `known` is True iff at least one candidate has an SRS stage and isn't hidden
    by an override (fading/struggling/buried).
    """
    candidates = resolve_vocabulary(conn, query)
    if not candidates:
        return {"known": False, "query": query, "matches": []}

    matches: list[dict[str, Any]] = []
    any_known = False
    for c in candidates:
        sid = c["subject_id"]
        a = conn.execute(
            "SELECT srs_stage FROM wk_assignments WHERE subject_id = ?", (sid,)
        ).fetchone()
        o = conn.execute(
            "SELECT override_status FROM wk_overrides WHERE subject_id = ?", (sid,)
        ).fetchone()
        srs_stage = a["srs_stage"] if a else None
        override = o["override_status"] if o else None
        is_known = (srs_stage is not None) and (override not in HIDE_FROM_KNOWN)
        if is_known:
            any_known = True
        matches.append({**c, "srs_stage": srs_stage, "override_status": override})

    return {"known": any_known, "query": query, "matches": matches}
