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
    """Refresh WK caches if needed; return any staleness notes."""
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

    @mcp.tool()
    @audit(_conn, "list_known_vocabulary")
    def list_known_vocabulary(
        min_srs_stage: int = 5,
        limit: int = 500,
        source_filter: str | None = None,
    ) -> dict[str, Any]:
        """List WaniKani vocabulary the user knows at or above the given SRS stage.

        SRS stages: 1-4 = Apprentice, 5-6 = Guru, 7 = Master, 8 = Enlightened, 9 = Burned.
        Default min_srs_stage=5 ("Guru+", what WaniKani considers 'known').
        """
        notes = _ensure_wk_fresh()
        items = vocab_tools.list_known_vocabulary(_conn(), min_srs_stage, limit, source_filter)
        return {"items": items, "count": len(items), "staleness_notes": notes}

    @mcp.tool()
    @audit(_conn, "is_word_known")
    def is_word_known(japanese_or_english: str) -> dict[str, Any]:
        """Look up a word (Japanese characters or English meaning) in the WaniKani set.

        Returns whether it is in the user's known set and its SRS stage.
        """
        notes = _ensure_wk_fresh()
        out = vocab_tools.is_word_known(_conn(), japanese_or_english)
        out["staleness_notes"] = notes
        return out

    @mcp.tool()
    @audit(_conn, "list_known_grammar")
    def list_known_grammar(
        status_filter: list[str] | None = None,
        level_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """List grammar points matching the filters.

        status_filter values: unknown, learning, known, mastered.
        level_filter values: N5, N4, N3, N2, N1.
        """
        items = grammar_tools.list_known_grammar(_conn(), status_filter, level_filter)
        return {"items": items, "count": len(items)}

    @mcp.tool()
    @audit(_conn, "mark_grammar")
    def mark_grammar(
        grammar_point: str,
        status: Literal["unknown", "learning", "known", "mastered"],
        note: str | None = None,
    ) -> dict[str, Any]:
        """Set the status (and optional note) for a single grammar point."""
        return grammar_tools.mark_grammar(_conn(), grammar_point, status, note)

    @mcp.tool()
    @audit(_conn, "walk_grammar")
    def walk_grammar(
        level_filter: list[str] | None = None,
        status_filter: list[str] | None = None,
        previous_response: Literal["k", "l", "u", "m", "s"] | None = None,
    ) -> dict[str, Any]:
        """Stream one grammar point at a time for fast bulk-marking.

        previous_response: k=known, l=learning, u=unknown, m=mastered, s=skip.
        Keep calling with the same filters until 'done' is true.
        """
        return grammar_tools.walk_grammar(_conn(), level_filter, status_filter, previous_response)

    @mcp.tool()
    @audit(_conn, "sample_for_prompts")
    def sample_for_prompts(
        count: int = 10,
        vocab_filter: dict | None = None,
        grammar_filter: dict | None = None,
    ) -> dict[str, Any]:
        """Return a random sample of vocab + grammar to use when building prompts.

        vocab_filter:  {min_srs_stage: int, source_filter: str|None}
        grammar_filter: {status_filter: [str], level_filter: [str]}
        """
        notes = _ensure_wk_fresh()
        out = sampling_tools.sample_for_prompts(_conn(), count, vocab_filter, grammar_filter)
        out["staleness_notes"] = notes
        return out

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
        """Append a production attempt (prompt, the user's answer, the correct answer, verdict)."""
        return log_tools.log_production_attempt(
            _conn(), prompt, my_answer, correct_answer, verdict
        )

    @mcp.tool()
    @audit(_conn, "log_unknown_word")
    def log_unknown_word(word: str, context: str | None = None) -> dict[str, Any]:
        """Append a word the user encountered but didn't know."""
        return log_tools.log_unknown_word(_conn(), word, context)

    return mcp


def run() -> None:
    global _CONFIG, _CONN, _WK
    _CONFIG, _CONN, _WK = _init_runtime()
    app = build_app()
    app.run()


if __name__ == "__main__":
    run()
