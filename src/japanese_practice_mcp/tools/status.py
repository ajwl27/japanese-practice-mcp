"""Read-only status tools: report manual + practice + effective status for an item."""
import sqlite3
from typing import Any

from japanese_practice_mcp.practice import (
    compute_practice_signal,
    fetch_grammar_events,
    fetch_vocabulary_events,
    grammar_effective_status,
    vocabulary_effective_status,
)
from japanese_practice_mcp.resolve import resolve_grammar, resolve_vocabulary


def grammar_status(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    """Return manual + practice + effective status for the resolved grammar point.

    Returns {"resolved": None, "candidates": [...]} on ambiguous resolution.
    Raises LookupError if no match.
    """
    candidates = resolve_grammar(conn, query)
    if not candidates:
        raise LookupError(f"no grammar point found for query {query!r}")
    if len(candidates) > 1:
        return {"resolved": None, "candidates": candidates, "query": query}

    canonical = candidates[0]
    row = conn.execute(
        "SELECT s.grammar_point, s.jlpt_level, st.status, st.note "
        "FROM grammar_seed s LEFT JOIN grammar_state st USING (grammar_point) "
        "WHERE s.grammar_point = ?",
        (canonical,),
    ).fetchone()
    manual_status = row["status"]
    events = fetch_grammar_events(conn, canonical)
    sig = compute_practice_signal(events)
    eff = grammar_effective_status(manual_status, sig["signal"])
    return {
        "resolved": canonical,
        "grammar_point": canonical,
        "jlpt_level": row["jlpt_level"],
        "manual_status": manual_status,
        "note": row["note"],
        "practice_signal": sig["signal"],
        "effective_status": eff,
        "successes_30d": sig["successes_30d"],
        "failures_30d": sig["failures_30d"],
        "last_practiced": sig["last_practiced"],
        "recent_total": sig["recent_total"],
    }


def vocabulary_status(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    """Return SRS + override + practice + effective status for the resolved WK item.

    Returns {"resolved": None, "candidates": [...]} on ambiguous resolution.
    Raises LookupError if no match.
    """
    candidates = resolve_vocabulary(conn, query)
    if not candidates:
        raise LookupError(f"no vocabulary found for query {query!r}")
    if len(candidates) > 1:
        return {"resolved": None, "candidates": candidates, "query": query}

    target = candidates[0]
    sid = target["subject_id"]
    a = conn.execute(
        "SELECT srs_stage FROM wk_assignments WHERE subject_id = ?", (sid,)
    ).fetchone()
    o = conn.execute(
        "SELECT override_status, note FROM wk_overrides WHERE subject_id = ?", (sid,)
    ).fetchone()
    srs_stage = a["srs_stage"] if a else None
    override = o["override_status"] if o else None
    override_note = o["note"] if o else None

    events = fetch_vocabulary_events(conn, subject_id=sid, word_form=target["characters"])
    sig = compute_practice_signal(events)
    eff = vocabulary_effective_status(srs_stage, override, sig["signal"])
    return {
        "resolved": target["characters"],
        "subject_id": sid,
        "characters": target["characters"],
        "meanings": target["meanings"],
        "readings": target["readings"],
        "level": target["level"],
        "srs_stage": srs_stage,
        "override_status": override,
        "override_note": override_note,
        "practice_signal": sig["signal"],
        "effective_status": eff,
        "successes_30d": sig["successes_30d"],
        "failures_30d": sig["failures_30d"],
        "last_practiced": sig["last_practiced"],
        "recent_total": sig["recent_total"],
    }
