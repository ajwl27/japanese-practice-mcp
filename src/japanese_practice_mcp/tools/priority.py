"""Unified 'what should I drill' view across personal-state tables."""
import json
import sqlite3
from typing import Any

from japanese_practice_mcp.practice import (
    compute_practice_signal,
    fetch_grammar_events,
    fetch_vocabulary_events,
)

PRIORITY_OVERRIDES = ("priority", "struggling")


def _weak_grammar_points(conn: sqlite3.Connection) -> list[str]:
    """Distinct grammar points whose practice_signal is currently 'weak'."""
    points = [r["grammar_point"] for r in conn.execute(
        "SELECT DISTINCT grammar_point FROM grammar_practice_events"
    ).fetchall()]
    weak: list[str] = []
    for gp in points:
        events = fetch_grammar_events(conn, gp)
        if compute_practice_signal(events)["signal"] == "weak":
            weak.append(gp)
    return weak


def _weak_vocab_subject_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT subject_id FROM vocabulary_practice_events "
        "WHERE subject_id IS NOT NULL"
    ).fetchall()
    weak: list[int] = []
    for r in rows:
        sid = r["subject_id"]
        events = fetch_vocabulary_events(conn, subject_id=sid, word_form=None)
        if compute_practice_signal(events)["signal"] == "weak":
            weak.append(sid)
    return weak


def list_priority_items(conn: sqlite3.Connection) -> dict[str, Any]:
    """Everything currently marked for active practice.

    Sources:
      - WK vocab with override_status in (priority, struggling)
      - WK vocab with practice_signal='weak' (regardless of manual status)
      - Grammar with status='learning'
      - Grammar with practice_signal='weak' (regardless of manual status)
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
            "reason": "override",
        }
        for r in vocab_rows
    ]
    seen_sids = {v["subject_id"] for v in vocabulary}
    for sid in _weak_vocab_subject_ids(conn):
        if sid in seen_sids:
            continue
        srow = conn.execute(
            "SELECT s.id, s.characters, s.meanings, s.readings, s.level, "
            "       a.srs_stage, o.override_status, o.note "
            "FROM wk_subjects s "
            "LEFT JOIN wk_assignments a ON a.subject_id = s.id "
            "LEFT JOIN wk_overrides o ON o.subject_id = s.id "
            "WHERE s.id = ?",
            (sid,),
        ).fetchone()
        if srow is None:
            continue
        vocabulary.append({
            "subject_id": srow["id"],
            "characters": srow["characters"],
            "meanings": json.loads(srow["meanings"]),
            "readings": json.loads(srow["readings"]),
            "level": srow["level"],
            "srs_stage": srow["srs_stage"],
            "override_status": srow["override_status"],
            "note": srow["note"],
            "updated_at": None,
            "reason": "practice_weak",
        })

    grammar_rows = conn.execute(
        """
        SELECT s.grammar_point, s.jlpt_level, st.status, st.note, st.marked_at
        FROM grammar_state st
        JOIN grammar_seed s USING (grammar_point)
        WHERE st.status = 'learning'
        ORDER BY st.marked_at DESC
        """
    ).fetchall()
    grammar = [{**dict(r), "reason": "learning"} for r in grammar_rows]
    seen_gps = {g["grammar_point"] for g in grammar}
    for gp in _weak_grammar_points(conn):
        if gp in seen_gps:
            continue
        srow = conn.execute(
            "SELECT s.grammar_point, s.jlpt_level, st.status, st.note, st.marked_at "
            "FROM grammar_seed s LEFT JOIN grammar_state st USING (grammar_point) "
            "WHERE s.grammar_point = ?",
            (gp,),
        ).fetchone()
        if srow is None:
            continue
        grammar.append({
            "grammar_point": srow["grammar_point"],
            "jlpt_level": srow["jlpt_level"],
            "status": srow["status"] or "unknown",
            "note": srow["note"],
            "marked_at": srow["marked_at"],
            "reason": "practice_weak",
        })

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
