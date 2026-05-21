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
    grammar_points: list[str] | None = None,
    vocabulary: list[str | int] | None = None,
    per_item_verdicts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record a production attempt and link it to the grammar/vocabulary it exercised.

    grammar_points: canonical grammar points the prompt was intended to test.
    vocabulary: WK Japanese forms (str) or subject IDs (int).
    per_item_verdicts: optional override of the attempt-level verdict for
      individual items, keyed by grammar point or word form.
    """
    p = _require(prompt, "prompt")
    a = _require(my_answer, "my_answer")
    c = _require(correct_answer, "correct_answer")
    v = _require(verdict, "verdict")
    cur = conn.execute(
        "INSERT INTO production_attempts (prompt, my_answer, correct_answer, verdict) "
        "VALUES (?, ?, ?, ?)",
        (p, a, c, v),
    )
    attempt_id = cur.lastrowid
    per_item = per_item_verdicts or {}

    for gp in grammar_points or []:
        gp_v = per_item.get(gp, v)
        conn.execute(
            "INSERT INTO grammar_practice_events (grammar_point, attempt_id, verdict) "
            "VALUES (?, ?, ?)",
            (gp, attempt_id, gp_v),
        )

    for vocab_item in vocabulary or []:
        if isinstance(vocab_item, int):
            subject_id: int | None = vocab_item
            word_form: str | None = None
            key = str(vocab_item)
        else:
            subject_id = None
            word_form = vocab_item
            key = vocab_item
        vocab_v = per_item.get(key, v)
        conn.execute(
            "INSERT INTO vocabulary_practice_events "
            "(subject_id, word_form, attempt_id, verdict) VALUES (?, ?, ?, ?)",
            (subject_id, word_form, attempt_id, vocab_v),
        )

    return {
        "id": attempt_id,
        "prompt": p,
        "verdict": v,
        "grammar_events": len(grammar_points or []),
        "vocabulary_events": len(vocabulary or []),
    }


def log_mined_word(
    conn: sqlite3.Connection,
    word: str,
    context: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    w = _require(word, "word")
    cur = conn.execute(
        "INSERT INTO mined_words (word, context, note) VALUES (?, ?, ?)",
        (w, context, note),
    )
    return {"id": cur.lastrowid, "word": w, "context": context, "note": note}


def log_expression(
    conn: sqlite3.Connection,
    form: str,
    context: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Log a multi-word expression: idiom, compound, proverb, set phrase, onomatopoeia.

    Only the canonical form is stored — Claude reinterprets meaning/reading on read.
    """
    f = _require(form, "form")
    cur = conn.execute(
        "INSERT INTO expressions (form, context, note) VALUES (?, ?, ?)",
        (f, context, note),
    )
    return {"id": cur.lastrowid, "form": f, "context": context, "note": note}
