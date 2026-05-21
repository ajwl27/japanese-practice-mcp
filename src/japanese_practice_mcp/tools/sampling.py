import random
import sqlite3
from typing import Any

from japanese_practice_mcp.tools.grammar import list_known_grammar
from japanese_practice_mcp.tools.vocabulary import list_known_vocabulary


def sample_for_prompts(
    conn: sqlite3.Connection,
    count: int = 10,
    vocab_filter: dict | None = None,
    grammar_filter: dict | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Return a random sample of vocab + grammar matching the filters."""
    rng = rng or random.Random()
    vocab_filter = vocab_filter or {}
    grammar_filter = grammar_filter or {}

    vocab_pool = list_known_vocabulary(
        conn,
        min_srs_stage=vocab_filter.get("min_srs_stage", 5),
        limit=10_000,
        source_filter=vocab_filter.get("source_filter"),
    )
    grammar_pool = list_known_grammar(
        conn,
        status_filter=grammar_filter.get("status_filter"),
        level_filter=grammar_filter.get("level_filter"),
    )

    rng.shuffle(vocab_pool)
    rng.shuffle(grammar_pool)
    return {
        "vocabulary": vocab_pool[:count],
        "grammar": grammar_pool[:count],
        "vocab_pool_size": len(vocab_pool),
        "grammar_pool_size": len(grammar_pool),
    }
