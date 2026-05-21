import sqlite3
from typing import Any


def _require(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value.strip()


def log_stuck_phrase(
    conn: sqlite3.Connection,
    phrase: str,
    context: str | None = None,
) -> dict[str, Any]:
    p = _require(phrase, "phrase")
    cur = conn.execute(
        "INSERT INTO stuck_phrases (phrase, context) VALUES (?, ?)",
        (p, context),
    )
    return {"id": cur.lastrowid, "phrase": p, "context": context}


def log_production_attempt(
    conn: sqlite3.Connection,
    prompt: str,
    my_answer: str,
    correct_answer: str,
    verdict: str,
) -> dict[str, Any]:
    p = _require(prompt, "prompt")
    a = _require(my_answer, "my_answer")
    c = _require(correct_answer, "correct_answer")
    v = _require(verdict, "verdict")
    cur = conn.execute(
        "INSERT INTO production_attempts (prompt, my_answer, correct_answer, verdict) "
        "VALUES (?, ?, ?, ?)",
        (p, a, c, v),
    )
    return {"id": cur.lastrowid, "prompt": p, "verdict": v}


def log_unknown_word(
    conn: sqlite3.Connection,
    word: str,
    context: str | None = None,
) -> dict[str, Any]:
    w = _require(word, "word")
    cur = conn.execute(
        "INSERT INTO unknown_words (word, context) VALUES (?, ?)",
        (w, context),
    )
    return {"id": cur.lastrowid, "word": w, "context": context}
