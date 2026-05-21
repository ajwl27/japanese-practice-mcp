"""Practice-history signal + effective-status derivation.

A "practice signal" is a label derived from rolling-window stats over
production attempts. It is *not* stored — it's computed each time it's needed.

An "effective status" merges the practice signal with the user's self-reported
manual status. Practice wins when it has spoken (solid/weak); otherwise we
fall back to manual.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

_CORRECT_TOKENS = {"correct", "right", "pass", "ok", "good", "yes"}
_INCORRECT_TOKENS = {"incorrect", "wrong", "fail", "bad", "no"}
_PARTIAL_TOKENS = {"partial", "close", "mostly", "kind of", "almost"}


def classify_verdict(verdict: str) -> str:
    """Map a free-form verdict string to 'correct' | 'incorrect' | 'partial'.

    Anything we don't recognize falls into 'partial' — it counts as neither a
    success nor a failure for signal purposes.
    """
    v = (verdict or "").strip().lower()
    if v in _CORRECT_TOKENS:
        return "correct"
    if v in _INCORRECT_TOKENS:
        return "incorrect"
    return "partial"


def _parse_iso(s: str) -> datetime:
    """Parse an ISO8601 string returned by SQLite; assume UTC if naive."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_practice_signal(
    events: list[dict],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Roll a list of practice events into a signal.

    events: list of dicts with at minimum 'verdict' and 'attempted_at' (ISO).
    now: defaults to datetime.now(UTC) — accepts an override for tests.

    Returns: {signal, successes_30d, failures_30d, last_practiced, recent_total}
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    last_30d = now - timedelta(days=30)
    last_90d = now - timedelta(days=90)

    in_30d: list[dict] = []
    in_90d: list[dict] = []
    last_practiced: datetime | None = None
    for e in events:
        ts = _parse_iso(e["attempted_at"])
        if last_practiced is None or ts > last_practiced:
            last_practiced = ts
        if ts >= last_30d:
            in_30d.append(e)
        if ts >= last_90d:
            in_90d.append(e)

    successes_30 = sum(1 for e in in_30d if classify_verdict(e["verdict"]) == "correct")
    failures_30 = sum(1 for e in in_30d if classify_verdict(e["verdict"]) == "incorrect")

    sorted_recent = sorted(
        events, key=lambda e: _parse_iso(e["attempted_at"]), reverse=True
    )[:10]
    rated = [
        classify_verdict(e["verdict"])
        for e in sorted_recent
        if classify_verdict(e["verdict"]) in ("correct", "incorrect")
    ]
    n_rated = len(rated)
    n_correct = rated.count("correct")
    success_rate = (n_correct / n_rated) if n_rated > 0 else None

    if successes_30 >= 3 and failures_30 == 0:
        signal = "solid"
    elif n_rated >= 5 and success_rate is not None and success_rate >= 0.8:
        signal = "solid"
    elif failures_30 >= 2:
        signal = "weak"
    elif n_rated >= 3 and success_rate is not None and success_rate < 0.5:
        signal = "weak"
    elif not in_90d:
        signal = "untested"
    else:
        signal = "shaky"

    return {
        "signal": signal,
        "successes_30d": successes_30,
        "failures_30d": failures_30,
        "last_practiced": last_practiced.isoformat() if last_practiced else None,
        "recent_total": n_rated,
    }


def grammar_effective_status(manual_status: str | None, practice_signal: str) -> str:
    if practice_signal == "solid":
        return "solid"
    if practice_signal == "weak":
        return "weak"
    return manual_status or "unknown"


def vocabulary_effective_status(
    srs_stage: int | None,
    override_status: str | None,
    practice_signal: str,
) -> str:
    if practice_signal == "solid":
        return "solid"
    if practice_signal == "weak":
        return "weak"
    if override_status:
        return override_status
    if srs_stage is None:
        return "unknown"
    if srs_stage >= 5:
        return "known"
    return "learning"


def fetch_grammar_events(conn, grammar_point: str) -> list[dict]:
    rows = conn.execute(
        "SELECT verdict, attempted_at FROM grammar_practice_events "
        "WHERE grammar_point = ? ORDER BY attempted_at DESC",
        (grammar_point,),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_vocabulary_events(conn, subject_id: int | None, word_form: str | None) -> list[dict]:
    if subject_id is not None and word_form is not None:
        rows = conn.execute(
            "SELECT verdict, attempted_at FROM vocabulary_practice_events "
            "WHERE subject_id = ? OR word_form = ? ORDER BY attempted_at DESC",
            (subject_id, word_form),
        ).fetchall()
    elif subject_id is not None:
        rows = conn.execute(
            "SELECT verdict, attempted_at FROM vocabulary_practice_events "
            "WHERE subject_id = ? ORDER BY attempted_at DESC",
            (subject_id,),
        ).fetchall()
    elif word_form is not None:
        rows = conn.execute(
            "SELECT verdict, attempted_at FROM vocabulary_practice_events "
            "WHERE word_form = ? ORDER BY attempted_at DESC",
            (word_form,),
        ).fetchall()
    else:
        return []
    return [dict(r) for r in rows]
