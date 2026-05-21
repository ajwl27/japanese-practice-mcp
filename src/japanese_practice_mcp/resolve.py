"""Fuzzy resolution of user-typed identifiers to canonical forms.

Used by any tool that accepts natural-language identifiers. Returns ALL
candidates on ambiguity — callers are expected to disambiguate with the user
rather than silently picking one.

Bug fix in v0.3: exact match (after NFKC + tilde + whitespace normalization)
always wins, even when the query is also a substring of other entries.
"""
import json
import re
import sqlite3
import unicodedata
from typing import Any

_GRAMMAR_DESCRIPTORS = [
    "conditional", "the", "particle", "form", "construction",
    "grammar", "thing", "pattern", "verb", "expression",
]
_DESCRIPTOR_RE = re.compile(
    r"\b(" + "|".join(_GRAMMAR_DESCRIPTORS) + r")\b",
    flags=re.IGNORECASE,
)

_STRIP_RE = re.compile(r"[\s+\-]")
_TILDE_CHARS = "〜～~"


def _match_key(s: str) -> str:
    """Canonical key for tolerant equality comparison."""
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.lstrip(_TILDE_CHARS)
    s = _STRIP_RE.sub("", s)
    return s


def _normalize_grammar_query(query: str) -> str:
    q = _DESCRIPTOR_RE.sub("", query)
    q = q.strip().strip("\"'.,;:!?")
    q = re.sub(r"\s+", " ", q).strip()
    return q


def resolve_grammar(conn: sqlite3.Connection, query: str) -> list[str]:
    """Return canonical grammar_points matching the query.

    Algorithm:
      1. Strip English descriptors from the query.
      2. Compute a normalization key (NFKC + lowercase + strip tilde prefix +
         strip whitespace/+/−).
      3. Scan all seed points; collect those whose key equals the query key
         (exact) OR whose key contains the query key (substring).
      4. If any exact matches exist, return ONLY them. Otherwise return all
         substring matches.
    """
    q = _normalize_grammar_query(query)
    if not q:
        return []
    q_key = _match_key(q)
    if not q_key:
        return []

    rows = conn.execute("SELECT grammar_point FROM grammar_seed").fetchall()

    exact: list[str] = []
    substring: list[str] = []
    for r in rows:
        gp = r["grammar_point"]
        gp_key = _match_key(gp)
        if gp_key == q_key:
            exact.append(gp)
        elif q_key in gp_key:
            substring.append(gp)

    if exact:
        return exact
    substring.sort(key=lambda s: (len(s), s))
    return substring


def resolve_vocabulary(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    """Return WK vocabulary subjects matching the query.

    Tiered: exact characters / exact reading / exact meaning win in that order
    (NFKC-normalized for Japanese). Falls back to substring in the same order.
    """
    q = query.strip()
    if not q:
        return []
    q_norm = unicodedata.normalize("NFKC", q)
    q_key = _match_key(q)
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
        chars_key = _match_key(chars)
        readings_keys = [_match_key(rd) for rd in readings]
        meanings_lower = [m.lower() for m in meanings]

        if q_key and chars_key == q_key:
            exact_chars.append(item)
        elif q_key and q_key in readings_keys:
            exact_reading.append(item)
        elif q_lower in meanings_lower:
            exact_meaning.append(item)
        elif q_norm and q_norm in chars:
            sub_chars.append(item)
        elif any(q in rd for rd in readings):
            sub_reading.append(item)
        elif any(q_lower in m for m in meanings_lower):
            sub_meaning.append(item)

    for tier in (exact_chars, exact_reading, exact_meaning, sub_chars, sub_reading, sub_meaning):
        if tier:
            return tier
    return []
