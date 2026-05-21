import random
import sqlite3
from typing import Any

from japanese_practice_mcp.tools.grammar import list_known_grammar
from japanese_practice_mcp.tools.vocabulary import list_known_vocabulary

# Items with effective_status == "solid" get extra weight in the sampler.
_SOLID_WEIGHT = 3
_MASTERED_WEIGHT = 2
_KNOWN_WEIGHT = 1


def _weight_for(item: dict, status_key: str) -> int:
    s = item.get(status_key)
    if s == "solid":
        return _SOLID_WEIGHT
    if s == "mastered":
        return _MASTERED_WEIGHT
    return _KNOWN_WEIGHT


def _weighted_sample(
    pool: list[dict], count: int, rng: random.Random, status_key: str
) -> list[dict]:
    if not pool or count <= 0:
        return []
    indices = list(range(len(pool)))
    weights = [_weight_for(p, status_key) for p in pool]
    chosen: list[int] = []
    for _ in range(min(count, len(pool))):
        idx = rng.choices(indices, weights=weights, k=1)[0]
        pos = indices.index(idx)
        indices.pop(pos)
        weights.pop(pos)
        chosen.append(idx)
    return [pool[i] for i in chosen]


def sample_for_prompts(
    conn: sqlite3.Connection,
    count: int = 10,
    vocab_filter: dict | None = None,
    grammar_filter: dict | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Return a random sample of vocab + grammar matching the filters.

    Vocab is automatically pre-filtered to exclude fading/struggling/buried AND
    practice-weak items. Grammar uses effective_status (known/solid/mastered)
    by default. "Solid" items get extra sampling weight.
    """
    rng = rng or random.Random()
    vocab_filter = vocab_filter or {}
    grammar_filter = grammar_filter or {}

    vocab_pool = list_known_vocabulary(
        conn,
        min_srs_stage=vocab_filter.get("min_srs_stage", 5),
        limit=10_000,
    )
    grammar_pool = list_known_grammar(
        conn,
        status_filter=grammar_filter.get("status_filter"),
        level_filter=grammar_filter.get("level_filter"),
    )

    vocab_chosen = _weighted_sample(vocab_pool, count, rng, "practice_signal")
    grammar_chosen = _weighted_sample(grammar_pool, count, rng, "effective_status")

    return {
        "vocabulary": vocab_chosen,
        "grammar": grammar_chosen,
        "vocab_pool_size": len(vocab_pool),
        "grammar_pool_size": len(grammar_pool),
    }
