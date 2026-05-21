"""First-run calibration helper.

The LLM calls this when starting a session against a cold DB and uses the
returned payload to ask the user "what's your level — should I bulk-mark
N5 + N4 + N3 as known?". The user agrees, the LLM calls bulk_mark_grammar.
"""
import sqlite3
from typing import Any

_COLD_FRACTION = 0.05


def quick_calibration(conn: sqlite3.Connection) -> dict[str, Any]:
    """Inspect the current marking state; return a calibration suggestion if cold."""
    total = conn.execute("SELECT COUNT(*) FROM grammar_seed").fetchone()[0]
    marked = conn.execute("SELECT COUNT(*) FROM grammar_state").fetchone()[0]
    by_level = {
        r["jlpt_level"]: r["c"]
        for r in conn.execute(
            "SELECT jlpt_level, COUNT(*) AS c FROM grammar_seed "
            "GROUP BY jlpt_level"
        ).fetchall()
    }
    marked_by_level = {
        r["jlpt_level"]: r["c"]
        for r in conn.execute(
            "SELECT s.jlpt_level, COUNT(*) AS c "
            "FROM grammar_state st JOIN grammar_seed s USING (grammar_point) "
            "GROUP BY s.jlpt_level"
        ).fetchall()
    }
    fraction = (marked / total) if total > 0 else 1.0
    needs = fraction < _COLD_FRACTION

    suggested_actions: list[dict[str, Any]] = []
    if needs:
        suggested_actions = [
            {
                "label": "I'm comfortable through N5",
                "description": "Bulk-mark all N5 as known.",
                "calls": [
                    {"tool": "bulk_mark_grammar",
                     "args": {"filter": {"level": "N5"}, "status": "known"}},
                ],
            },
            {
                "label": "I'm N4-ish",
                "description": "Bulk-mark N5 and N4 as known; leave N3+ unknown.",
                "calls": [
                    {"tool": "bulk_mark_grammar",
                     "args": {"filter": {"level": ["N5", "N4"]}, "status": "known"}},
                ],
            },
            {
                "label": "I'm N3-ish",
                "description": "Bulk-mark N5, N4 as known and N3 as learning.",
                "calls": [
                    {"tool": "bulk_mark_grammar",
                     "args": {"filter": {"level": ["N5", "N4"]}, "status": "known"}},
                    {"tool": "bulk_mark_grammar",
                     "args": {"filter": {"level": "N3"}, "status": "learning"}},
                ],
            },
            {
                "label": "I'm N2-ish",
                "description": "Bulk-mark N5–N3 as known and N2 as learning.",
                "calls": [
                    {"tool": "bulk_mark_grammar",
                     "args": {"filter": {"level": ["N5", "N4", "N3"]}, "status": "known"}},
                    {"tool": "bulk_mark_grammar",
                     "args": {"filter": {"level": "N2"}, "status": "learning"}},
                ],
            },
            {
                "label": "Walk me through everything",
                "description": "Skip bulk marking; use walk_grammar one item at a time.",
                "calls": [],
            },
        ]

    return {
        "needs_calibration": needs,
        "current_state": {
            "total_grammar_points": total,
            "marked_count": marked,
            "unmarked_count": total - marked,
            "by_level": by_level,
            "marked_by_level": marked_by_level,
        },
        "suggested_actions": suggested_actions,
        "message": (
            "You haven't marked much grammar yet. Want to bulk-set your level "
            "so prompts are immediately useful? You can refine from there."
            if needs else
            "You've marked enough grammar that calibration isn't urgent. "
            "Continue using mark_grammar or walk_grammar as normal."
        ),
    }
