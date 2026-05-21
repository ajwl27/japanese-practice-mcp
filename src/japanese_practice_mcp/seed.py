import json
import sqlite3
from pathlib import Path

DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parent.parent.parent / "seed" / "bunpro_deck_index.json"
)


def seed_grammar_from_bunpro(conn: sqlite3.Connection, path: Path) -> int:
    """Insert grammar_seed rows not already present. Returns # inserted."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    grammar_rows = [r for r in raw if r.get("deck_type") == "Grammar"]
    inserted = 0
    for r in grammar_rows:
        cur = conn.execute(
            "INSERT OR IGNORE INTO grammar_seed (grammar_point, jlpt_level) VALUES (?, ?)",
            (r["term"], r["deck_name"]),
        )
        if cur.rowcount > 0:
            inserted += 1
    return inserted
