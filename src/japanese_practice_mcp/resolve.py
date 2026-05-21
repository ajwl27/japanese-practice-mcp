"""Fuzzy resolution of user-typed identifiers to canonical forms.

Used by any tool that accepts natural-language identifiers. Returns ALL
candidates on ambiguity — callers are expected to disambiguate with the user
rather than silently picking one.
"""
import json
import re
import sqlite3
from typing import Any

_GRAMMAR_DESCRIPTORS = [
    "conditional", "the", "particle", "form", "construction",
    "grammar", "thing", "pattern", "verb", "expression",
]
_DESCRIPTOR_RE = re.compile(
    r"\b(" + "|".join(_GRAMMAR_DESCRIPTORS) + r")\b",
    flags=re.IGNORECASE,
)


def _normalize_grammar_query(query: str) -> str:
    q = _DESCRIPTOR_RE.sub("", query)
    q = q.strip().strip("\"'.,;:!?")
    q = re.sub(r"\s+", " ", q).strip()
    return q


def resolve_grammar(conn: sqlite3.Connection, query: str) -> list[str]:
    """Return all grammar_seed rows whose grammar_point matches the query.

    Exact match (case-insensitive) wins outright. Otherwise substring match.
    """
    q = _normalize_grammar_query(query)
    if not q:
        return []
    exact = conn.execute(
        "SELECT grammar_point FROM grammar_seed "
        "WHERE LOWER(grammar_point) = LOWER(?)",
        (q,),
    ).fetchall()
    if exact:
        return [r["grammar_point"] for r in exact]
    like = conn.execute(
        "SELECT grammar_point FROM grammar_seed "
        "WHERE LOWER(grammar_point) LIKE LOWER('%' || ? || '%') "
        "ORDER BY LENGTH(grammar_point) ASC, grammar_point ASC",
        (q,),
    ).fetchall()
    return [r["grammar_point"] for r in like]


def resolve_vocabulary(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    """Return WK vocabulary subjects matching the query.

    Match priority: exact characters → exact reading → exact meaning →
    substring characters → substring reading → substring meaning.
    """
    q = query.strip()
    if not q:
        return []
    q_lower = q.lower()

    rows = conn.execute(
        "SELECT id, characters, meanings, readings, level FROM wk_subjects "
        "WHERE object = 'vocabulary'"
    ).fetchall()

    exact_chars: list[dict] = []
    exact_reading: list[dict] = []
    exact_meaning: list[dict] = []
    sub_chars: list[dict] = []
    sub_reading: list[dict] = []
    sub_meaning: list[dict] = []

    for r in rows:
        meanings = json.loads(r["meanings"])
        readings = json.loads(r["readings"])
        item = {
            "subject_id": r["id"],
            "characters": r["characters"],
            "meanings": meanings,
            "readings": readings,
            "level": r["level"],
        }
        chars = r["characters"] or ""
        meanings_lower = [m.lower() for m in meanings]
        if chars == q:
            exact_chars.append(item)
        elif q in readings:
            exact_reading.append(item)
        elif q_lower in meanings_lower:
            exact_meaning.append(item)
        elif q in chars:
            sub_chars.append(item)
        elif any(q in rd for rd in readings):
            sub_reading.append(item)
        elif any(q_lower in m for m in meanings_lower):
            sub_meaning.append(item)

    for tier in (exact_chars, exact_reading, exact_meaning, sub_chars, sub_reading, sub_meaning):
        if tier:
            return tier
    return []
