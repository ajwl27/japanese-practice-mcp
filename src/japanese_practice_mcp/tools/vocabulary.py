import json
import sqlite3
from typing import Any


def list_known_vocabulary(
    conn: sqlite3.Connection,
    min_srs_stage: int = 5,
    limit: int = 500,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return WK vocabulary items at or above the given SRS stage."""
    if source_filter not in (None, "wanikani"):
        return []
    cur = conn.execute(
        """
        SELECT s.id, s.characters, s.meanings, s.readings, s.level, a.srs_stage
        FROM wk_subjects s
        JOIN wk_assignments a ON a.subject_id = s.id
        WHERE s.object = 'vocabulary' AND a.srs_stage >= ?
        ORDER BY a.srs_stage DESC, s.level ASC, s.id ASC
        LIMIT ?
        """,
        (min_srs_stage, limit),
    )
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        out.append(
            {
                "subject_id": r["id"],
                "characters": r["characters"],
                "meanings": json.loads(r["meanings"]),
                "readings": json.loads(r["readings"]),
                "level": r["level"],
                "srs_stage": r["srs_stage"],
                "source": "wanikani",
            }
        )
    return out


def is_word_known(conn: sqlite3.Connection, japanese_or_english: str) -> dict[str, Any]:
    """Look up by characters (exact) or any meaning (case-insensitive). Vocab only."""
    q = japanese_or_english.strip()
    row = conn.execute(
        """
        SELECT s.id, s.characters, s.meanings, s.readings, s.level, a.srs_stage
        FROM wk_subjects s
        LEFT JOIN wk_assignments a ON a.subject_id = s.id
        WHERE s.object = 'vocabulary' AND s.characters = ?
        ORDER BY (a.srs_stage IS NULL), a.srs_stage DESC
        LIMIT 1
        """,
        (q,),
    ).fetchone()
    if row is None:
        q_lower = q.lower()
        candidates = conn.execute(
            """
            SELECT s.id, s.characters, s.meanings, s.readings, s.level, a.srs_stage
            FROM wk_subjects s
            LEFT JOIN wk_assignments a ON a.subject_id = s.id
            WHERE s.object = 'vocabulary'
            """
        ).fetchall()
        for c in candidates:
            meanings = [m.lower() for m in json.loads(c["meanings"])]
            if q_lower in meanings:
                row = c
                break

    if row is None:
        return {"known": False, "query": japanese_or_english, "srs_stage": None}
    srs = row["srs_stage"]
    return {
        "known": srs is not None,
        "query": japanese_or_english,
        "subject_id": row["id"],
        "characters": row["characters"],
        "meanings": json.loads(row["meanings"]),
        "readings": json.loads(row["readings"]),
        "level": row["level"],
        "srs_stage": srs,
    }
