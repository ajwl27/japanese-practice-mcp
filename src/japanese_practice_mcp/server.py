"""MCP server entry point. Wires FastMCP to our tool functions."""
import sqlite3
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from japanese_practice_mcp.audit import audit
from japanese_practice_mcp.config import Config, load_config
from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.seed import DEFAULT_SEED_PATH, seed_grammar_from_bunpro
from japanese_practice_mcp.tools import grammar as grammar_tools
from japanese_practice_mcp.tools import logs as log_tools
from japanese_practice_mcp.tools import overrides as override_tools
from japanese_practice_mcp.tools import priority as priority_tools
from japanese_practice_mcp.tools import sampling as sampling_tools
from japanese_practice_mcp.tools import vocabulary as vocab_tools
from japanese_practice_mcp.wanikani import (
    StalenessError,
    WaniKaniClient,
    ensure_assignments_fresh,
    ensure_subjects_fresh,
)


_CONN: sqlite3.Connection | None = None
_CONFIG: Config | None = None
_WK: WaniKaniClient | None = None


def _conn() -> sqlite3.Connection:
    if _CONN is None:
        raise RuntimeError("server not initialized")
    return _CONN


def _init_runtime() -> tuple[Config, sqlite3.Connection, WaniKaniClient]:
    cfg = load_config()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(cfg.data_dir / "japanese-practice.db")
    init_schema(conn)
    seed_grammar_from_bunpro(conn, DEFAULT_SEED_PATH)
    wk = WaniKaniClient(token=cfg.wanikani_token)
    return cfg, conn, wk


def _ensure_wk_fresh() -> list[str]:
    assert _CONFIG is not None and _CONN is not None and _WK is not None
    notes: list[str] = []
    try:
        _ok, note = ensure_subjects_fresh(
            _CONN, _WK, max_age_days=_CONFIG.subjects_max_age_days
        )
        if note:
            notes.append(note)
    except StalenessError as e:
        notes.append(str(e))
    try:
        _ok, note = ensure_assignments_fresh(
            _CONN, _WK, ttl_seconds=_CONFIG.assignments_ttl_seconds
        )
        if note:
            notes.append(note)
    except StalenessError as e:
        notes.append(str(e))
    return notes


def build_app() -> FastMCP:
    mcp = FastMCP("japanese-practice-mcp")

    # --------- Vocabulary ---------

    @mcp.tool()
    @audit(_conn, "list_known_vocabulary")
    def list_known_vocabulary(
        min_srs_stage: int = 5,
        limit: int = 500,
    ) -> dict[str, Any]:
        """List WaniKani vocabulary the user knows solidly.

        Returns WK items at or above the given SRS stage, automatically excluding
        any items the user has overridden as fading, struggling, or buried.

        SRS stages: 1-4 = Apprentice, 5-6 = Guru, 7 = Master, 8 = Enlightened, 9 = Burned.
        Default min_srs_stage=5 ("Guru+", what WaniKani considers 'known').
        """
        notes = _ensure_wk_fresh()
        items = vocab_tools.list_known_vocabulary(_conn(), min_srs_stage, limit)
        return {"items": items, "count": len(items), "staleness_notes": notes}

    @mcp.tool()
    @audit(_conn, "is_word_known")
    def is_word_known(query: str) -> dict[str, Any]:
        """Look up a word (Japanese, kana, or English meaning) in the WaniKani set.

        Fuzzy matching across characters, readings, and meanings. Returns all
        candidates (Claude disambiguates on ambiguity) with their SRS stage AND
        any user override (fading, struggling, priority, buried).
        """
        notes = _ensure_wk_fresh()
        out = vocab_tools.is_word_known(_conn(), query)
        out["staleness_notes"] = notes
        return out

    @mcp.tool()
    @audit(_conn, "override_vocabulary")
    def override_vocabulary(
        query: str,
        override_status: Literal["fading", "struggling", "priority", "buried"],
        note: str | None = None,
    ) -> dict[str, Any]:
        """Override the user's relationship to a WK vocabulary item.

        - fading: slipping out of knowledge; excluded from "known"
        - struggling: chronically wrong; excluded from "known" + on priority list
        - priority: drill this; on priority list
        - buried: hide from "known" suggestions

        Accepts fuzzy queries. On ambiguity returns the candidate list without
        writing — caller is expected to disambiguate with the user.
        """
        notes = _ensure_wk_fresh()
        out = override_tools.override_vocabulary(_conn(), query, override_status, note)
        out["staleness_notes"] = notes
        return out

    # --------- Grammar ---------

    @mcp.tool()
    @audit(_conn, "list_known_grammar")
    def list_known_grammar(
        status_filter: list[str] | None = None,
        level_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """List grammar points matching the filters.

        Items the user hasn't marked yet are returned with status='unknown'.
        status_filter values: unknown, learning, known, mastered.
        level_filter values: N5, N4, N3, N2, N1.
        """
        items = grammar_tools.list_known_grammar(_conn(), status_filter, level_filter)
        return {"items": items, "count": len(items)}

    @mcp.tool()
    @audit(_conn, "mark_grammar")
    def mark_grammar(
        query: str,
        status: Literal["learning", "known", "mastered"],
        note: str | None = None,
    ) -> dict[str, Any]:
        """Mark a grammar point's status. Accepts fuzzy queries.

        Note: there's no 'unknown' status — that's the implicit state of any
        grammar point with no row in grammar_state.

        On ambiguous resolution, returns {"resolved": None, "candidates": [...]}
        without writing — disambiguate with the user and retry.
        """
        return grammar_tools.mark_grammar(_conn(), query, status, note)

    @mcp.tool()
    @audit(_conn, "walk_grammar")
    def walk_grammar(
        level_filter: list[str] | None = None,
        status_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Stream one grammar point at a time for bulk-marking sessions.

        Returns the current grammar point plus the remaining count for pacing.
        Claude is expected to generate a fresh example + 1-line explanation
        on the fly (the seed only stores canonical form + JLPT level), then ask
        the user k/l/u/m, then call mark_grammar accordingly, then call
        walk_grammar again for the next point. Filter changes reset the cursor.
        """
        return grammar_tools.walk_grammar(_conn(), level_filter, status_filter)

    # --------- Sampling + priority ---------

    @mcp.tool()
    @audit(_conn, "sample_for_prompts")
    def sample_for_prompts(
        count: int = 10,
        vocab_filter: dict | None = None,
        grammar_filter: dict | None = None,
    ) -> dict[str, Any]:
        """Return a random sample of vocab + grammar to use when building prompts.

        Vocab is pre-filtered to exclude fading/struggling/buried — "give me
        prompts using stuff I solidly know" works naturally.

        vocab_filter:  {min_srs_stage: int}
        grammar_filter: {status_filter: [str], level_filter: [str]}
        """
        notes = _ensure_wk_fresh()
        out = sampling_tools.sample_for_prompts(_conn(), count, vocab_filter, grammar_filter)
        out["staleness_notes"] = notes
        return out

    @mcp.tool()
    @audit(_conn, "list_priority_items")
    def list_priority_items() -> dict[str, Any]:
        """Return everything currently marked for active practice.

        Unified view across:
        - WK vocab with override_status in (priority, struggling)
        - Grammar with status='learning'
        - All logged expressions
        - All mined words

        This is the "what should I drill" surface. Derived, not stored.
        """
        return priority_tools.list_priority_items(_conn())

    # --------- Logs ---------

    @mcp.tool()
    @audit(_conn, "log_stuck_phrase")
    def log_stuck_phrase(phrase: str, context: str | None = None) -> dict[str, Any]:
        """Append a phrase the user got stuck trying to say."""
        return log_tools.log_stuck_phrase(_conn(), phrase, context)

    @mcp.tool()
    @audit(_conn, "log_production_attempt")
    def log_production_attempt(
        prompt: str, my_answer: str, correct_answer: str, verdict: str
    ) -> dict[str, Any]:
        """Append a production attempt (prompt, user's answer, correct answer, verdict)."""
        return log_tools.log_production_attempt(
            _conn(), prompt, my_answer, correct_answer, verdict
        )

    @mcp.tool()
    @audit(_conn, "log_mined_word")
    def log_mined_word(
        word: str, context: str | None = None, note: str | None = None
    ) -> dict[str, Any]:
        """Append a word the user encountered but didn't know. Only the form is
        stored — Claude reinterprets meaning/reading on next read.
        """
        return log_tools.log_mined_word(_conn(), word, context, note)

    @mcp.tool()
    @audit(_conn, "log_expression")
    def log_expression(
        form: str, context: str | None = None, note: str | None = None
    ) -> dict[str, Any]:
        """Log a multi-word expression: idiom, four-character compound, proverb,
        set phrase, onomatopoeia. Only the canonical form is stored — Claude
        reinterprets type/meaning on next read.
        """
        return log_tools.log_expression(_conn(), form, context, note)

    return mcp


def run() -> None:
    global _CONFIG, _CONN, _WK
    _CONFIG, _CONN, _WK = _init_runtime()
    app = build_app()
    app.run()


if __name__ == "__main__":
    run()
