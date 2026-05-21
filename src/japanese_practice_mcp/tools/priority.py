"""Unified 'what should I drill' view across personal-state tables."""
import json
import sqlite3
from typing import Any

PRIORITY_OVERRIDES = ("priority", "struggling")


def list_priority_items(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return everything currently marked for active practice across all surfaces.

    - WK vocab with override_status in (priority, struggling)
    - Grammar with status='learning'
    - All logged expressions
    - All mined words
    """
    placeholders = ",".join("?" for _ in PRIORITY_OVERRIDES)
    vocab_rows = conn.execute(
        f"""
        SELECT s.id, s.characters, s.meanings, s.readings, s.level,
               a.srs_stage, o.override_status, o.note, o.updated_at
        FROM wk_overrides o
        JOIN wk_subjects s ON s.id = o.subject_id
        LEFT JOIN wk_assignments a ON a.subject_id = s.id
        WHERE o.override_status IN ({placeholders})
        ORDER BY o.updated_at DESC
        """,
        PRIORITY_OVERRIDES,
    ).fetchall()
    vocabulary = [
        {
            "subject_id": r["id"],
            "characters": r["characters"],
            "meanings": json.loads(r["meanings"]),
            "readings": json.loads(r["readings"]),
            "level": r["level"],
            "srs_stage": r["srs_stage"],
            "override_status": r["override_status"],
            "note": r["note"],
            "updated_at": r["updated_at"],
        }
        for r in vocab_rows
    ]

    grammar_rows = conn.execute(
        """
        SELECT s.grammar_point, s.jlpt_level, st.status, st.note, st.marked_at
        FROM grammar_state st
        JOIN grammar_seed s USING (grammar_point)
        WHERE st.status = 'learning'
        ORDER BY st.marked_at DESC
        """
    ).fetchall()
    grammar = [dict(r) for r in grammar_rows]

    expressions = [
        dict(r) for r in conn.execute(
            "SELECT id, form, context, note, logged_at FROM expressions "
            "ORDER BY logged_at DESC"
        ).fetchall()
    ]

    mined_words = [
        dict(r) for r in conn.execute(
            "SELECT id, word, context, note, logged_at FROM mined_words "
            "ORDER BY logged_at DESC"
        ).fetchall()
    ]

    total = len(vocabulary) + len(grammar) + len(expressions) + len(mined_words)
    return {
        "vocabulary": vocabulary,
        "grammar": grammar,
        "expressions": expressions,
        "mined_words": mined_words,
        "total": total,
    }
