from datetime import datetime, timedelta, timezone

from japanese_practice_mcp.practice import (
    classify_verdict,
    compute_practice_signal,
    grammar_effective_status,
    vocabulary_effective_status,
)


NOW = datetime(2026, 5, 21, tzinfo=timezone.utc)


def _iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _events(*specs: tuple[str, int]) -> list[dict]:
    return [{"verdict": v, "attempted_at": _iso(d)} for v, d in specs]


def test_classify_verdict_correct() -> None:
    assert classify_verdict("correct") == "correct"
    assert classify_verdict("Correct") == "correct"
    assert classify_verdict("right") == "correct"
    assert classify_verdict("pass") == "correct"
    assert classify_verdict("ok") == "correct"


def test_classify_verdict_incorrect() -> None:
    assert classify_verdict("incorrect") == "incorrect"
    assert classify_verdict("wrong") == "incorrect"
    assert classify_verdict("fail") == "incorrect"


def test_classify_verdict_partial() -> None:
    assert classify_verdict("partial") == "partial"
    assert classify_verdict("close") == "partial"
    assert classify_verdict("mostly") == "partial"


def test_classify_verdict_unknown_defaults_to_partial() -> None:
    assert classify_verdict("hmm") == "partial"


def test_signal_solid_by_count_rule() -> None:
    events = _events(("correct", 1), ("correct", 5), ("correct", 10))
    out = compute_practice_signal(events, NOW)
    assert out["signal"] == "solid"
    assert out["successes_30d"] == 3
    assert out["failures_30d"] == 0


def test_signal_solid_by_rate_rule() -> None:
    events = _events(
        ("correct", 1), ("correct", 2), ("correct", 3),
        ("correct", 4), ("incorrect", 5),
    )
    out = compute_practice_signal(events, NOW)
    assert out["signal"] == "solid"


def test_signal_weak_by_failure_count() -> None:
    events = _events(("incorrect", 5), ("incorrect", 10))
    out = compute_practice_signal(events, NOW)
    assert out["signal"] == "weak"


def test_signal_weak_by_rate() -> None:
    events = _events(("correct", 1), ("incorrect", 2), ("incorrect", 3))
    out = compute_practice_signal(events, NOW)
    assert out["signal"] == "weak"


def test_signal_shaky_default() -> None:
    events = _events(("correct", 5))
    out = compute_practice_signal(events, NOW)
    assert out["signal"] == "shaky"


def test_signal_untested_no_recent() -> None:
    events = _events(("correct", 120))
    out = compute_practice_signal(events, NOW)
    assert out["signal"] == "untested"


def test_signal_untested_empty() -> None:
    out = compute_practice_signal([], NOW)
    assert out["signal"] == "untested"
    assert out["last_practiced"] is None


def test_signal_records_last_practiced() -> None:
    events = _events(("correct", 3), ("incorrect", 1))
    out = compute_practice_signal(events, NOW)
    assert out["last_practiced"] == _iso(1)


def test_grammar_effective_status_practice_overrides_manual() -> None:
    assert grammar_effective_status("known", "weak") == "weak"
    assert grammar_effective_status("unknown", "solid") == "solid"


def test_grammar_effective_status_falls_back_to_manual() -> None:
    assert grammar_effective_status("learning", "shaky") == "learning"
    assert grammar_effective_status(None, "untested") == "unknown"


def test_vocab_effective_status_practice_overrides() -> None:
    assert vocabulary_effective_status(5, None, "weak") == "weak"
    assert vocabulary_effective_status(2, None, "solid") == "solid"


def test_vocab_effective_status_falls_back() -> None:
    assert vocabulary_effective_status(5, None, "shaky") == "known"
    assert vocabulary_effective_status(2, None, "shaky") == "learning"
    assert vocabulary_effective_status(None, None, "untested") == "unknown"
    assert vocabulary_effective_status(7, "fading", "shaky") == "fading"
    assert vocabulary_effective_status(7, "priority", "shaky") == "priority"
