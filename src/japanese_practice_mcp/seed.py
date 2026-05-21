import json
import sqlite3
from pathlib import Path

# Layout: src/japanese_practice_mcp/seed.py -> ../../seed/bunpro_deck_index.json
DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parent.parent.parent / "seed" / "bunpro_deck_index.json"
)


def seed_grammar_from_bunpro(conn: sqlite3.Connection, path: Path) -> int:
    """Insert grammar rows that aren't already present. Returns # inserted."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    grammar_rows = [r for r in raw if r.get("deck_type") == "Grammar"]
    inserted = 0
    for r in grammar_rows:
        gp = r["term"]
        level = r["deck_name"]
        cur = conn.execute(
            "INSERT OR IGNORE INTO grammar (grammar_point, jlpt_level) VALUES (?, ?)",
            (gp, level),
        )
        if cur.rowcount > 0:
            inserted += 1
    return inserted
