# japanese-practice-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local stdio MCP server that exposes a user's WaniKani progress + a local SQLite grammar/log database to Claude clients, so Claude can produce Japanese production prompts using only items the user knows.

**Architecture:** Single Python package, single process, single SQLite database. FastMCP (`mcp.server.fastmcp.FastMCP`) exposes tools over stdio. A `wanikani` module wraps the WK v2 REST API with httpx and caches subjects + assignments into SQLite. Each MCP tool is a thin layer that calls a pure function in `tools/` modules, then `audit.py` records the call. SQLite is the only persistence; no extra processes, no daemons. Designed for an HTTPS transport drop-in later: all tool functions are transport-agnostic — only `server.py` knows about FastMCP.

**Tech Stack:**
- Language: Python 3.11+ (uses stdlib `tomllib`)
- MCP SDK: `mcp` (official Python SDK), via `FastMCP`
- HTTP: `httpx` (sync mode — FastMCP tools can be sync; simpler than asyncio)
- DB: stdlib `sqlite3`, WAL mode
- Cross-platform paths: `platformdirs`
- Tests: `pytest` + `pytest-httpx` (mocks `httpx`)
- Package manager: `uv`
- License: MIT

---

## Decisions (recorded here, copied to README)

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | User is fluent; stdlib `tomllib`; clean MCP SDK |
| MCP SDK | `mcp` Python SDK, FastMCP | Official Anthropic SDK; decorator-based; stdio default |
| Package manager | `uv` | Fast, single binary, reproducible lockfile |
| SQLite library | stdlib `sqlite3` | Schema is tiny; no ORM needed |
| Test framework | `pytest` + `pytest-httpx` | Standard; clean HTTP mocking |
| Project layout | `src/japanese_practice_mcp/` | Avoids import-from-cwd footgun |
| Data directory | `platformdirs.user_data_dir("japanese-practice-mcp")` | Cross-platform; XDG on Linux |
| Config location | `platformdirs.user_config_dir("japanese-practice-mcp")/config.toml` | Same |
| Concurrency | Sync end-to-end | One user, one process, blocking I/O is fine |
| License | MIT | Permissive, common |
| Audit log | Same SQLite DB | One file to back up |

---

## File Structure

```
japanese-practice-mcp/
├── pyproject.toml                        # uv project, deps, console script entry point
├── README.md                             # Install, register, decisions, scope
├── LICENSE                               # MIT
├── .gitignore                            # __pycache__, .venv, *.db, _tmp_*
├── docs/superpowers/plans/2026-05-21-japanese-practice-mcp.md  # this file
├── seed/
│   └── bunpro_deck_index.json            # Committed snapshot of flio/wkanki dump
├── src/japanese_practice_mcp/
│   ├── __init__.py
│   ├── __main__.py                       # `python -m japanese_practice_mcp`
│   ├── server.py                         # FastMCP instance + tool registration
│   ├── config.py                         # Config loading (TOML + env overrides)
│   ├── paths.py                          # platformdirs wrappers
│   ├── db.py                             # Schema, connection mgmt, migrations
│   ├── seed.py                           # Initial grammar seeding from bunpro JSON
│   ├── wanikani.py                       # WK API client + caching
│   ├── audit.py                          # Tool-call audit logging
│   └── tools/
│       ├── __init__.py
│       ├── vocabulary.py                 # list_known_vocabulary, is_word_known
│       ├── grammar.py                    # list_known_grammar, mark_grammar, walk_grammar
│       ├── sampling.py                   # sample_for_prompts
│       └── logs.py                       # log_stuck_phrase, log_production_attempt, log_unknown_word
└── tests/
    ├── conftest.py                       # Shared fixtures (tmp DB, mock WK)
    ├── test_db.py
    ├── test_seed.py
    ├── test_wanikani.py
    ├── test_config.py
    ├── test_audit.py
    ├── test_vocabulary.py
    ├── test_grammar.py
    ├── test_sampling.py
    ├── test_logs.py
    └── fixtures/
        ├── wk_subjects_page1.json
        ├── wk_subjects_page2.json
        └── wk_assignments_page1.json
```

---

## Database Schema

```sql
-- WaniKani subjects cache (full payload, rarely changes)
CREATE TABLE wk_subjects (
    id           INTEGER PRIMARY KEY,
    object       TEXT NOT NULL,             -- 'vocabulary' | 'kanji' | 'radical'
    characters   TEXT,                      -- the Japanese characters
    slug         TEXT,
    level        INTEGER,                   -- WK level 1-60
    meanings     TEXT NOT NULL,             -- JSON array of strings
    readings     TEXT NOT NULL,             -- JSON array of strings (vocab/kanji only)
    data_json    TEXT NOT NULL,             -- full WK payload (for forward-compat)
    updated_at   TEXT NOT NULL              -- WK's data_updated_at, ISO8601
);
CREATE INDEX idx_wk_subjects_object ON wk_subjects(object);
CREATE INDEX idx_wk_subjects_characters ON wk_subjects(characters);

-- WaniKani assignments cache (per-subject SRS state)
CREATE TABLE wk_assignments (
    id           INTEGER PRIMARY KEY,
    subject_id   INTEGER NOT NULL,
    srs_stage    INTEGER NOT NULL,          -- 0..9 (Apprentice 1 .. Burned)
    data_json    TEXT NOT NULL,
    cached_at    TEXT NOT NULL              -- ISO8601, our local fetch time
);
CREATE INDEX idx_wk_assignments_subject ON wk_assignments(subject_id);
CREATE INDEX idx_wk_assignments_srs ON wk_assignments(srs_stage);

-- Cache freshness markers (one row per cache key)
CREATE TABLE wk_cache_meta (
    key          TEXT PRIMARY KEY,          -- e.g. 'subjects_synced_at', 'assignments_synced_at'
    value        TEXT NOT NULL,             -- ISO8601 or arbitrary string
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Grammar list (seeded from bunpro, mutated by user)
CREATE TABLE grammar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grammar_point TEXT NOT NULL UNIQUE,
    reading       TEXT,                       -- nullable; bunpro dump has none
    jlpt_level    TEXT NOT NULL,              -- 'N1' .. 'N5'
    status        TEXT NOT NULL DEFAULT 'unknown'
                  CHECK(status IN ('unknown','learning','known','mastered')),
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_grammar_status ON grammar(status);
CREATE INDEX idx_grammar_level ON grammar(jlpt_level);

-- Stuck phrases log
CREATE TABLE stuck_phrases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase      TEXT NOT NULL,
    context     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Production attempts log
CREATE TABLE production_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt          TEXT NOT NULL,
    my_answer       TEXT NOT NULL,
    correct_answer  TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Unknown words log
CREATE TABLE unknown_words (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word        TEXT NOT NULL,
    context     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tool-call audit log
CREATE TABLE tool_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name       TEXT NOT NULL,
    arguments_json  TEXT,
    result_summary  TEXT,
    error           TEXT,
    duration_ms     INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_tool ON tool_audit(tool_name);

-- Single-row walk state
CREATE TABLE walk_state (
    id                  INTEGER PRIMARY KEY CHECK(id = 1),
    filter_hash         TEXT,
    current_grammar_id  INTEGER,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Task 0: Project skeleton + dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `src/japanese_practice_mcp/__init__.py` (empty)
- Create: `src/japanese_practice_mcp/__main__.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Working dir: `C:\Users\orca\japanese-practice-mcp` (already exists, empty)

- [ ] **Step 0.1: Write `pyproject.toml`**

```toml
[project]
name = "japanese-practice-mcp"
version = "0.1.0"
description = "Local MCP server exposing my Japanese learning data to Claude clients for production practice."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "orca" }]
dependencies = [
    "mcp>=1.2.0",
    "httpx>=0.27",
    "platformdirs>=4.2",
]

[project.scripts]
japanese-practice-mcp = "japanese_practice_mcp.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/japanese_practice_mcp"]

[tool.hatch.build]
include = ["src/japanese_practice_mcp/**", "seed/**"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-httpx>=0.30",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 0.2: Write `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
*.db
*.db-journal
*.db-wal
*.db-shm
.env
_tmp_*
dist/
build/
*.egg-info/
.coverage
```

- [ ] **Step 0.3: Write `LICENSE`** (standard MIT, attributed to "orca", year 2026)

- [ ] **Step 0.4: Write `src/japanese_practice_mcp/__main__.py`** (will be filled in later, for now a placeholder)

```python
def main() -> None:
    from japanese_practice_mcp.server import run
    run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 0.5: Write `tests/conftest.py`** (will be expanded later)

```python
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("JPMCP_DATA_DIR", str(d))
    return d
```

- [ ] **Step 0.6: Initialize the venv and install**

Run:
```bash
cd C:/Users/orca/japanese-practice-mcp
uv sync
```
Expected: `.venv` created, deps installed, no errors.

- [ ] **Step 0.7: Smoke-run pytest**

Run: `uv run pytest -q`
Expected: "no tests ran" (exit 5 is fine), no import errors.

- [ ] **Step 0.8: Commit**

Run:
```bash
git init -b main
git add pyproject.toml .gitignore LICENSE src tests docs
git commit -m "chore: project skeleton with uv, pyproject, MIT license"
```

---

## Task 1: Bunpro seed snapshot

**Files:**
- Create: `seed/bunpro_deck_index.json`

- [ ] **Step 1.1: Download the dump and commit it**

Run:
```bash
curl -fsSL "https://gitlab.com/flio/wkanki/-/raw/main/bunpro/deck_index.json" -o seed/bunpro_deck_index.json
```
Expected: file exists, ~500KB-ish, valid JSON.

- [ ] **Step 1.2: Quick sanity check**

Run:
```bash
uv run python -c "import json; d=json.load(open('seed/bunpro_deck_index.json',encoding='utf-8')); g=[x for x in d if x['deck_type']=='Grammar']; print(len(g), 'grammar rows')"
```
Expected: `910 grammar rows` (or close to it if upstream updates).

- [ ] **Step 1.3: Commit**

```bash
git add seed/bunpro_deck_index.json
git commit -m "data: snapshot bunpro deck_index.json (grammar seed)"
```

---

## Task 2: Paths + config module

**Files:**
- Create: `src/japanese_practice_mcp/paths.py`
- Create: `src/japanese_practice_mcp/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 2.1: Write the failing config test**

Create `tests/test_config.py`:

```python
import os
from pathlib import Path

import pytest

from japanese_practice_mcp.config import Config, load_config


def write_toml(p: Path, content: str) -> None:
    p.write_text(content, encoding="utf-8")


def test_loads_from_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.toml"
    write_toml(cfg_file, 'wanikani_token = "wk-from-file"\ndata_dir = "/tmp/x"\n')
    monkeypatch.delenv("JPMCP_WANIKANI_TOKEN", raising=False)
    monkeypatch.delenv("JPMCP_DATA_DIR", raising=False)
    cfg = load_config(config_path=cfg_file)
    assert cfg.wanikani_token == "wk-from-file"
    assert cfg.data_dir == Path("/tmp/x")


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.toml"
    write_toml(cfg_file, 'wanikani_token = "wk-from-file"\n')
    monkeypatch.setenv("JPMCP_WANIKANI_TOKEN", "wk-from-env")
    cfg = load_config(config_path=cfg_file)
    assert cfg.wanikani_token == "wk-from-env"


def test_missing_token_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.toml"
    write_toml(cfg_file, "")
    monkeypatch.delenv("JPMCP_WANIKANI_TOKEN", raising=False)
    with pytest.raises(ValueError, match="wanikani_token"):
        load_config(config_path=cfg_file)


def test_no_config_file_with_env_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JPMCP_WANIKANI_TOKEN", "wk-from-env")
    monkeypatch.setenv("JPMCP_DATA_DIR", str(tmp_path / "d"))
    cfg = load_config(config_path=tmp_path / "nonexistent.toml")
    assert cfg.wanikani_token == "wk-from-env"
    assert cfg.data_dir == tmp_path / "d"
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: ImportError / ModuleNotFoundError on `japanese_practice_mcp.config`.

- [ ] **Step 2.3: Write `src/japanese_practice_mcp/paths.py`**

```python
from pathlib import Path

import platformdirs

APP_NAME = "japanese-practice-mcp"


def default_data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME))


def default_config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME))


def default_config_path() -> Path:
    return default_config_dir() / "config.toml"
```

- [ ] **Step 2.4: Write `src/japanese_practice_mcp/config.py`**

```python
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from japanese_practice_mcp.paths import default_config_path, default_data_dir


@dataclass(frozen=True)
class Config:
    wanikani_token: str
    data_dir: Path
    subjects_max_age_days: int = 7
    assignments_ttl_seconds: int = 3600


def load_config(config_path: Path | None = None) -> Config:
    """Load config from TOML; env vars (JPMCP_*) override.

    Env vars:
      JPMCP_WANIKANI_TOKEN  -> wanikani_token
      JPMCP_DATA_DIR        -> data_dir
      JPMCP_CONFIG          -> path to config.toml (if config_path is None)
    """
    if config_path is None:
        env_path = os.environ.get("JPMCP_CONFIG")
        config_path = Path(env_path) if env_path else default_config_path()

    raw: dict = {}
    if config_path.exists():
        with config_path.open("rb") as f:
            raw = tomllib.load(f)

    token = os.environ.get("JPMCP_WANIKANI_TOKEN") or raw.get("wanikani_token")
    if not token:
        raise ValueError(
            f"wanikani_token not found. Set JPMCP_WANIKANI_TOKEN or add "
            f"`wanikani_token = \"...\"` to {config_path}."
        )

    data_dir_str = os.environ.get("JPMCP_DATA_DIR") or raw.get("data_dir")
    data_dir = Path(data_dir_str) if data_dir_str else default_data_dir()

    return Config(
        wanikani_token=str(token),
        data_dir=data_dir,
        subjects_max_age_days=int(raw.get("subjects_max_age_days", 7)),
        assignments_ttl_seconds=int(raw.get("assignments_ttl_seconds", 3600)),
    )
```

- [ ] **Step 2.5: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 2.6: Commit**

```bash
git add src/japanese_practice_mcp/paths.py src/japanese_practice_mcp/config.py tests/test_config.py
git commit -m "feat(config): TOML config + JPMCP_* env var overrides"
```

---

## Task 3: Database module (connection + schema)

**Files:**
- Create: `src/japanese_practice_mcp/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 3.1: Write the failing test**

Create `tests/test_db.py`:

```python
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema


def test_init_schema_creates_tables(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    expected = {
        "wk_subjects", "wk_assignments", "wk_cache_meta",
        "grammar", "stuck_phrases", "production_attempts",
        "unknown_words", "tool_audit", "walk_state",
    }
    assert expected.issubset(names)


def test_init_schema_is_idempotent(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)
    init_schema(conn)  # must not raise


def test_grammar_status_check_rejects_bad_value(tmp_db_path: Path) -> None:
    import sqlite3
    conn = connect(tmp_db_path)
    init_schema(conn)
    try:
        conn.execute(
            "INSERT INTO grammar (grammar_point, jlpt_level, status) "
            "VALUES ('x', 'N5', 'bogus')"
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected IntegrityError")


def test_walk_state_single_row(tmp_db_path: Path) -> None:
    import sqlite3
    conn = connect(tmp_db_path)
    init_schema(conn)
    conn.execute("INSERT INTO walk_state (id) VALUES (1)")
    try:
        conn.execute("INSERT INTO walk_state (id) VALUES (2)")
        conn.commit()
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected walk_state id=2 to violate CHECK")
```

- [ ] **Step 3.2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: ModuleNotFoundError on `japanese_practice_mcp.db`.

- [ ] **Step 3.3: Write `src/japanese_practice_mcp/db.py`**

```python
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS wk_subjects (
    id           INTEGER PRIMARY KEY,
    object       TEXT NOT NULL,
    characters   TEXT,
    slug         TEXT,
    level        INTEGER,
    meanings     TEXT NOT NULL,
    readings     TEXT NOT NULL,
    data_json    TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wk_subjects_object ON wk_subjects(object);
CREATE INDEX IF NOT EXISTS idx_wk_subjects_characters ON wk_subjects(characters);

CREATE TABLE IF NOT EXISTS wk_assignments (
    id           INTEGER PRIMARY KEY,
    subject_id   INTEGER NOT NULL,
    srs_stage    INTEGER NOT NULL,
    data_json    TEXT NOT NULL,
    cached_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wk_assignments_subject ON wk_assignments(subject_id);
CREATE INDEX IF NOT EXISTS idx_wk_assignments_srs ON wk_assignments(srs_stage);

CREATE TABLE IF NOT EXISTS wk_cache_meta (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grammar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grammar_point TEXT NOT NULL UNIQUE,
    reading       TEXT,
    jlpt_level    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'unknown'
                  CHECK(status IN ('unknown','learning','known','mastered')),
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_grammar_status ON grammar(status);
CREATE INDEX IF NOT EXISTS idx_grammar_level ON grammar(jlpt_level);

CREATE TABLE IF NOT EXISTS stuck_phrases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase      TEXT NOT NULL,
    context     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS production_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt          TEXT NOT NULL,
    my_answer       TEXT NOT NULL,
    correct_answer  TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS unknown_words (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word        TEXT NOT NULL,
    context     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name       TEXT NOT NULL,
    arguments_json  TEXT,
    result_summary  TEXT,
    error           TEXT,
    duration_ms     INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_tool ON tool_audit(tool_name);

CREATE TABLE IF NOT EXISTS walk_state (
    id                  INTEGER PRIMARY KEY CHECK(id = 1),
    filter_hash         TEXT,
    current_grammar_id  INTEGER,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: 4 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/japanese_practice_mcp/db.py tests/test_db.py
git commit -m "feat(db): SQLite schema + connection helper"
```

---

## Task 4: Grammar seeding

**Files:**
- Create: `src/japanese_practice_mcp/seed.py`
- Create: `tests/test_seed.py`

- [ ] **Step 4.1: Write the failing test**

Create `tests/test_seed.py`:

```python
import json
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.seed import (
    DEFAULT_SEED_PATH,
    seed_grammar_from_bunpro,
)


SAMPLE = [
    {"term": "は",  "deck_type": "Grammar", "deck_name": "N5"},
    {"term": "も",  "deck_type": "Grammar", "deck_name": "N5"},
    {"term": "丸",  "deck_type": "Vocab",   "deck_name": "N5"},
    {"term": "ない", "deck_type": "Grammar", "deck_name": "N4"},
]


def test_seed_inserts_only_grammar(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    inserted = seed_grammar_from_bunpro(conn, seed_file)
    assert inserted == 3
    rows = conn.execute(
        "SELECT grammar_point, jlpt_level, status FROM grammar ORDER BY grammar_point"
    ).fetchall()
    pairs = [(r["grammar_point"], r["jlpt_level"], r["status"]) for r in rows]
    assert ("は", "N5", "unknown") in pairs
    assert ("ない", "N4", "unknown") in pairs
    # vocab not inserted
    assert all(p[0] != "丸" for p in pairs)


def test_seed_is_idempotent(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    seed_grammar_from_bunpro(conn, seed_file)
    inserted_second = seed_grammar_from_bunpro(conn, seed_file)
    assert inserted_second == 0
    n = conn.execute("SELECT COUNT(*) FROM grammar").fetchone()[0]
    assert n == 3


def test_seed_preserves_user_status(tmp_path: Path, tmp_db_path: Path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(SAMPLE), encoding="utf-8")
    conn = connect(tmp_db_path)
    init_schema(conn)
    seed_grammar_from_bunpro(conn, seed_file)
    conn.execute("UPDATE grammar SET status='known' WHERE grammar_point='は'")
    seed_grammar_from_bunpro(conn, seed_file)  # re-seed
    row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point='は'"
    ).fetchone()
    assert row["status"] == "known"


def test_default_seed_file_exists() -> None:
    assert DEFAULT_SEED_PATH.exists()
    assert DEFAULT_SEED_PATH.stat().st_size > 1000
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `uv run pytest tests/test_seed.py -v`
Expected: ModuleNotFoundError on `japanese_practice_mcp.seed`.

- [ ] **Step 4.3: Write `src/japanese_practice_mcp/seed.py`**

```python
import json
import sqlite3
from pathlib import Path

# Resolve path to the committed seed file at runtime.
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
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_seed.py -v`
Expected: 4 passed.

- [ ] **Step 4.5: Commit**

```bash
git add src/japanese_practice_mcp/seed.py tests/test_seed.py
git commit -m "feat(seed): import bunpro grammar dump, idempotent"
```

---

## Task 5: WaniKani client + caching

**Files:**
- Create: `src/japanese_practice_mcp/wanikani.py`
- Create: `tests/test_wanikani.py`
- Create: `tests/fixtures/wk_subjects_page1.json`
- Create: `tests/fixtures/wk_subjects_page2.json`
- Create: `tests/fixtures/wk_assignments_page1.json`

- [ ] **Step 5.1: Create test fixtures**

`tests/fixtures/wk_subjects_page1.json`:
```json
{
  "object": "collection",
  "total_count": 2,
  "pages": { "next_url": "https://api.wanikani.com/v2/subjects?page_after_id=1", "previous_url": null, "per_page": 1 },
  "data": [
    {
      "id": 1,
      "object": "vocabulary",
      "data_updated_at": "2024-01-01T00:00:00Z",
      "data": {
        "characters": "猫",
        "slug": "neko",
        "level": 2,
        "meanings": [{"meaning": "cat", "primary": true, "accepted_answer": true}],
        "readings": [{"reading": "ねこ", "primary": true, "accepted_answer": true}]
      }
    }
  ]
}
```

`tests/fixtures/wk_subjects_page2.json`:
```json
{
  "object": "collection",
  "total_count": 2,
  "pages": { "next_url": null, "previous_url": null, "per_page": 1 },
  "data": [
    {
      "id": 2,
      "object": "vocabulary",
      "data_updated_at": "2024-01-01T00:00:00Z",
      "data": {
        "characters": "犬",
        "slug": "inu",
        "level": 2,
        "meanings": [{"meaning": "dog", "primary": true, "accepted_answer": true}],
        "readings": [{"reading": "いぬ", "primary": true, "accepted_answer": true}]
      }
    }
  ]
}
```

`tests/fixtures/wk_assignments_page1.json`:
```json
{
  "object": "collection",
  "total_count": 2,
  "pages": { "next_url": null, "previous_url": null, "per_page": 500 },
  "data": [
    { "id": 100, "object": "assignment", "data": { "subject_id": 1, "subject_type": "vocabulary", "srs_stage": 5 } },
    { "id": 101, "object": "assignment", "data": { "subject_id": 2, "subject_type": "vocabulary", "srs_stage": 2 } }
  ]
}
```

- [ ] **Step 5.2: Write the failing test**

Create `tests/test_wanikani.py`:

```python
import json
from pathlib import Path

import httpx
import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.wanikani import (
    WaniKaniClient,
    StalenessError,
    sync_subjects,
    sync_assignments,
    last_synced_at,
)


FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_sync_subjects_pages_through_all(httpx_mock, tmp_db_path: Path) -> None:
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/subjects",
        json=load("wk_subjects_page1.json"),
    )
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/subjects?page_after_id=1",
        json=load("wk_subjects_page2.json"),
    )
    conn = connect(tmp_db_path)
    init_schema(conn)
    client = WaniKaniClient(token="tk")
    n = sync_subjects(conn, client)
    assert n == 2
    rows = conn.execute("SELECT id, characters FROM wk_subjects ORDER BY id").fetchall()
    assert [(r["id"], r["characters"]) for r in rows] == [(1, "猫"), (2, "犬")]


def test_sync_assignments(httpx_mock, tmp_db_path: Path) -> None:
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/assignments?unlocked=true",
        json=load("wk_assignments_page1.json"),
    )
    conn = connect(tmp_db_path)
    init_schema(conn)
    client = WaniKaniClient(token="tk")
    n = sync_assignments(conn, client)
    assert n == 2
    rows = conn.execute(
        "SELECT id, subject_id, srs_stage FROM wk_assignments ORDER BY id"
    ).fetchall()
    assert [(r["id"], r["subject_id"], r["srs_stage"]) for r in rows] == [
        (100, 1, 5),
        (101, 2, 2),
    ]


def test_auth_header_present(httpx_mock, tmp_db_path: Path) -> None:
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/subjects",
        json=load("wk_subjects_page2.json"),
    )
    conn = connect(tmp_db_path)
    init_schema(conn)
    client = WaniKaniClient(token="secret-token")
    sync_subjects(conn, client)
    req = httpx_mock.get_requests()[0]
    assert req.headers["Authorization"] == "Bearer secret-token"


def test_sync_records_synced_at(httpx_mock, tmp_db_path: Path) -> None:
    httpx_mock.add_response(
        url="https://api.wanikani.com/v2/subjects",
        json=load("wk_subjects_page2.json"),
    )
    conn = connect(tmp_db_path)
    init_schema(conn)
    client = WaniKaniClient(token="tk")
    sync_subjects(conn, client)
    assert last_synced_at(conn, "subjects") is not None
```

- [ ] **Step 5.3: Run test to verify it fails**

Run: `uv run pytest tests/test_wanikani.py -v`
Expected: ModuleNotFoundError on `japanese_practice_mcp.wanikani`.

- [ ] **Step 5.4: Write `src/japanese_practice_mcp/wanikani.py`**

```python
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

import httpx

BASE_URL = "https://api.wanikani.com/v2"


class StalenessError(RuntimeError):
    """Raised when fresh data cannot be obtained and stale is unacceptable."""


@dataclass
class WaniKaniClient:
    token: str
    timeout: float = 30.0

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Wanikani-Revision": "20170710",
        }

    def get_pages(self, url: str) -> Iterator[dict]:
        with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
            next_url: str | None = url
            while next_url:
                resp = client.get(next_url)
                resp.raise_for_status()
                payload = resp.json()
                yield payload
                next_url = (payload.get("pages") or {}).get("next_url")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _mark_synced(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        "INSERT INTO wk_cache_meta (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
        (f"{key}_synced_at", _now_iso()),
    )


def last_synced_at(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM wk_cache_meta WHERE key = ?", (f"{key}_synced_at",)
    ).fetchone()
    return row["value"] if row else None


def sync_subjects(conn: sqlite3.Connection, client: WaniKaniClient) -> int:
    """Fetch all subjects, upsert into wk_subjects. Returns # rows upserted."""
    n = 0
    for page in client.get_pages(f"{BASE_URL}/subjects"):
        for item in page.get("data", []):
            sid = item["id"]
            obj = item["object"]
            data = item.get("data", {})
            characters = data.get("characters")
            slug = data.get("slug")
            level = data.get("level")
            meanings = [m["meaning"] for m in data.get("meanings", [])]
            readings = [r["reading"] for r in data.get("readings", [])]
            conn.execute(
                """
                INSERT INTO wk_subjects
                    (id, object, characters, slug, level, meanings, readings, data_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    object=excluded.object,
                    characters=excluded.characters,
                    slug=excluded.slug,
                    level=excluded.level,
                    meanings=excluded.meanings,
                    readings=excluded.readings,
                    data_json=excluded.data_json,
                    updated_at=excluded.updated_at
                """,
                (
                    sid, obj, characters, slug, level,
                    json.dumps(meanings, ensure_ascii=False),
                    json.dumps(readings, ensure_ascii=False),
                    json.dumps(item, ensure_ascii=False),
                    item.get("data_updated_at", _now_iso()),
                ),
            )
            n += 1
    _mark_synced(conn, "subjects")
    return n


def sync_assignments(conn: sqlite3.Connection, client: WaniKaniClient) -> int:
    """Fetch all unlocked assignments, replace wk_assignments. Returns # rows."""
    conn.execute("DELETE FROM wk_assignments")
    n = 0
    for page in client.get_pages(f"{BASE_URL}/assignments?unlocked=true"):
        for item in page.get("data", []):
            aid = item["id"]
            data = item.get("data", {})
            conn.execute(
                """
                INSERT INTO wk_assignments
                    (id, subject_id, srs_stage, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    aid, data["subject_id"], data["srs_stage"],
                    json.dumps(item, ensure_ascii=False), _now_iso(),
                ),
            )
            n += 1
    _mark_synced(conn, "assignments")
    return n


def assignments_age_seconds(conn: sqlite3.Connection) -> float | None:
    ts = last_synced_at(conn, "assignments")
    if not ts:
        return None
    delta = datetime.now(tz=timezone.utc) - datetime.fromisoformat(ts)
    return delta.total_seconds()


def subjects_age_days(conn: sqlite3.Connection) -> float | None:
    ts = last_synced_at(conn, "subjects")
    if not ts:
        return None
    delta = datetime.now(tz=timezone.utc) - datetime.fromisoformat(ts)
    return delta.total_seconds() / 86400.0


def ensure_subjects_fresh(
    conn: sqlite3.Connection, client: WaniKaniClient, max_age_days: float
) -> tuple[bool, str | None]:
    """Refresh subjects if stale or absent. Returns (is_fresh, staleness_note_or_none)."""
    age = subjects_age_days(conn)
    if age is None or age > max_age_days:
        try:
            sync_subjects(conn, client)
            return True, None
        except (httpx.HTTPError, httpx.HTTPStatusError) as e:
            if age is None:
                raise StalenessError(
                    f"WaniKani subjects have never been synced and the API is unreachable: {e}"
                ) from e
            return False, f"WaniKani API unreachable; serving subjects cache from {age:.1f}d ago"
    return True, None


def ensure_assignments_fresh(
    conn: sqlite3.Connection, client: WaniKaniClient, ttl_seconds: float
) -> tuple[bool, str | None]:
    age = assignments_age_seconds(conn)
    if age is None or age > ttl_seconds:
        try:
            sync_assignments(conn, client)
            return True, None
        except (httpx.HTTPError, httpx.HTTPStatusError) as e:
            if age is None:
                raise StalenessError(
                    f"WaniKani assignments have never been synced and the API is unreachable: {e}"
                ) from e
            return False, f"WaniKani API unreachable; serving assignments cache from {age/60:.1f}m ago"
    return True, None
```

- [ ] **Step 5.5: Run tests to verify they pass**

Run: `uv run pytest tests/test_wanikani.py -v`
Expected: 4 passed.

- [ ] **Step 5.6: Commit**

```bash
git add src/japanese_practice_mcp/wanikani.py tests/test_wanikani.py tests/fixtures
git commit -m "feat(wanikani): subjects+assignments sync with cache freshness helpers"
```

---

## Task 6: Audit logging

**Files:**
- Create: `src/japanese_practice_mcp/audit.py`
- Create: `tests/test_audit.py`

- [ ] **Step 6.1: Write the failing test**

`tests/test_audit.py`:

```python
import json
from pathlib import Path

from japanese_practice_mcp.audit import audit
from japanese_practice_mcp.db import connect, init_schema


def test_audit_records_success(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)

    @audit(lambda: conn, "my_tool")
    def my_tool(x: int) -> dict:
        return {"doubled": x * 2}

    out = my_tool(3)
    assert out == {"doubled": 6}
    rows = conn.execute(
        "SELECT tool_name, arguments_json, result_summary, error FROM tool_audit"
    ).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r["tool_name"] == "my_tool"
    assert json.loads(r["arguments_json"]) == {"x": 3}
    assert r["error"] is None
    assert "doubled" in r["result_summary"]


def test_audit_records_exception(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path)
    init_schema(conn)

    @audit(lambda: conn, "boom_tool")
    def boom(x: int) -> int:
        raise ValueError("nope")

    try:
        boom(7)
    except ValueError:
        pass
    rows = conn.execute(
        "SELECT tool_name, error FROM tool_audit"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "boom_tool"
    assert "nope" in rows[0]["error"]
```

- [ ] **Step 6.2: Run test to verify it fails**

Run: `uv run pytest tests/test_audit.py -v`
Expected: ModuleNotFoundError on `japanese_practice_mcp.audit`.

- [ ] **Step 6.3: Write `src/japanese_practice_mcp/audit.py`**

```python
import functools
import inspect
import json
import sqlite3
import time
import traceback
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

MAX_RESULT_SUMMARY = 500


def _summarize(value: Any) -> str:
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        s = repr(value)
    return s[:MAX_RESULT_SUMMARY]


def audit(conn_getter: Callable[[], sqlite3.Connection], tool_name: str) -> Callable[[F], F]:
    """Decorator that records each call to `tool_audit`. `conn_getter` is invoked per call."""

    def decorator(func: F) -> F:
        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = sig.bind_partial(*args, **kwargs)
            args_json = json.dumps(dict(bound.arguments), ensure_ascii=False, default=str)
            start = time.monotonic()
            error: str | None = None
            result: Any = None
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
                raise
            finally:
                duration_ms = int((time.monotonic() - start) * 1000)
                try:
                    conn = conn_getter()
                    conn.execute(
                        "INSERT INTO tool_audit "
                        "(tool_name, arguments_json, result_summary, error, duration_ms) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (tool_name, args_json, _summarize(result) if error is None else None,
                         error, duration_ms),
                    )
                except Exception:
                    pass  # never let audit failures break the tool

        return wrapper  # type: ignore[return-value]

    return decorator
```

- [ ] **Step 6.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_audit.py -v`
Expected: 2 passed.

- [ ] **Step 6.5: Commit**

```bash
git add src/japanese_practice_mcp/audit.py tests/test_audit.py
git commit -m "feat(audit): decorator that records every tool call"
```

---

## Task 7: Vocabulary tools (`list_known_vocabulary`, `is_word_known`)

**Files:**
- Create: `src/japanese_practice_mcp/tools/__init__.py` (empty)
- Create: `src/japanese_practice_mcp/tools/vocabulary.py`
- Create: `tests/test_vocabulary.py`

- [ ] **Step 7.1: Write the failing test**

`tests/test_vocabulary.py`:

```python
import json
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.vocabulary import (
    list_known_vocabulary,
    is_word_known,
)


def _seed(conn) -> None:
    # Two vocab items: 猫 (cat) at SRS 5, 犬 (dog) at SRS 2
    conn.execute(
        "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
        "VALUES (1, 'vocabulary', '猫', 'neko', 2, ?, ?, '{}', '2024-01-01')",
        (json.dumps(["cat"]), json.dumps(["ねこ"])),
    )
    conn.execute(
        "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
        "VALUES (2, 'vocabulary', '犬', 'inu', 2, ?, ?, '{}', '2024-01-01')",
        (json.dumps(["dog"]), json.dumps(["いぬ"])),
    )
    conn.execute(
        "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
        "VALUES (3, 'kanji', '猫', 'neko-kanji', 2, ?, ?, '{}', '2024-01-01')",
        (json.dumps(["cat"]), json.dumps(["ねこ"])),
    )
    conn.execute(
        "INSERT INTO wk_assignments (id, subject_id, srs_stage, data_json, cached_at) "
        "VALUES (100, 1, 5, '{}', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO wk_assignments (id, subject_id, srs_stage, data_json, cached_at) "
        "VALUES (101, 2, 2, '{}', '2024-01-01')"
    )
    conn.commit()


def test_list_known_vocab_filters_by_srs(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    items = list_known_vocabulary(conn, min_srs_stage=5)
    assert len(items) == 1
    assert items[0]["characters"] == "猫"
    assert items[0]["srs_stage"] == 5


def test_list_known_vocab_excludes_lower_srs(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    items = list_known_vocabulary(conn, min_srs_stage=2)
    assert {i["characters"] for i in items} == {"猫", "犬"}


def test_list_known_vocab_limit(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    items = list_known_vocabulary(conn, min_srs_stage=0, limit=1)
    assert len(items) == 1


def test_is_word_known_by_japanese(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "猫")
    assert out["known"] is True
    assert out["srs_stage"] == 5


def test_is_word_known_by_english(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "dog")
    assert out["known"] is True
    assert out["srs_stage"] == 2


def test_is_word_unknown(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = is_word_known(conn, "elephant")
    assert out["known"] is False
    assert out["srs_stage"] is None
```

- [ ] **Step 7.2: Run test to verify it fails**

Run: `uv run pytest tests/test_vocabulary.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 7.3: Write `src/japanese_practice_mcp/tools/__init__.py`** (empty file)

- [ ] **Step 7.4: Write `src/japanese_practice_mcp/tools/vocabulary.py`**

```python
import json
import sqlite3
from typing import Any


def list_known_vocabulary(
    conn: sqlite3.Connection,
    min_srs_stage: int = 5,
    limit: int = 500,
    source_filter: str | None = None,  # placeholder for future sources
) -> list[dict[str, Any]]:
    """Return WK vocabulary items at or above the given SRS stage."""
    if source_filter not in (None, "wanikani"):
        return []
    cur = conn.execute(
        """
        SELECT s.id, s.characters, s.meanings, s.readings, s.level, a.srs_stage
        FROM wk_subjects s
        JOIN wk_assignments a ON a.subject_id = s.id
        WHERE s.object = 'vocabulary' AND a.srs_stage >= ?
        ORDER BY a.srs_stage DESC, s.level ASC, s.id ASC
        LIMIT ?
        """,
        (min_srs_stage, limit),
    )
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        out.append(
            {
                "subject_id": r["id"],
                "characters": r["characters"],
                "meanings": json.loads(r["meanings"]),
                "readings": json.loads(r["readings"]),
                "level": r["level"],
                "srs_stage": r["srs_stage"],
                "source": "wanikani",
            }
        )
    return out


def is_word_known(conn: sqlite3.Connection, japanese_or_english: str) -> dict[str, Any]:
    """Look up by characters (exact) or any meaning (case-insensitive). Vocab only."""
    q = japanese_or_english.strip()
    # Try Japanese exact match first
    row = conn.execute(
        """
        SELECT s.id, s.characters, s.meanings, s.readings, s.level, a.srs_stage
        FROM wk_subjects s
        LEFT JOIN wk_assignments a ON a.subject_id = s.id
        WHERE s.object = 'vocabulary' AND s.characters = ?
        ORDER BY a.srs_stage DESC NULLS LAST
        LIMIT 1
        """,
        (q,),
    ).fetchone()
    # Fall back to meaning match
    if row is None:
        q_lower = q.lower()
        candidates = conn.execute(
            """
            SELECT s.id, s.characters, s.meanings, s.readings, s.level, a.srs_stage
            FROM wk_subjects s
            LEFT JOIN wk_assignments a ON a.subject_id = s.id
            WHERE s.object = 'vocabulary'
            """
        ).fetchall()
        for c in candidates:
            meanings = [m.lower() for m in json.loads(c["meanings"])]
            if q_lower in meanings:
                row = c
                break

    if row is None:
        return {"known": False, "query": japanese_or_english, "srs_stage": None}
    srs = row["srs_stage"]
    return {
        "known": srs is not None,
        "query": japanese_or_english,
        "subject_id": row["id"],
        "characters": row["characters"],
        "meanings": json.loads(row["meanings"]),
        "readings": json.loads(row["readings"]),
        "level": row["level"],
        "srs_stage": srs,
    }
```

- [ ] **Step 7.5: Run tests to verify they pass**

Run: `uv run pytest tests/test_vocabulary.py -v`
Expected: 6 passed.

- [ ] **Step 7.6: Commit**

```bash
git add src/japanese_practice_mcp/tools/__init__.py src/japanese_practice_mcp/tools/vocabulary.py tests/test_vocabulary.py
git commit -m "feat(tools): list_known_vocabulary + is_word_known"
```

---

## Task 8: Grammar tools (`list_known_grammar`, `mark_grammar`, `walk_grammar`)

**Files:**
- Create: `src/japanese_practice_mcp/tools/grammar.py`
- Create: `tests/test_grammar.py`

- [ ] **Step 8.1: Write the failing test**

`tests/test_grammar.py`:

```python
from pathlib import Path

import pytest

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.grammar import (
    list_known_grammar,
    mark_grammar,
    walk_grammar,
)


def _seed(conn) -> None:
    pts = [
        ("は", "N5"), ("も", "N5"), ("が", "N5"),
        ("ない", "N4"), ("ながら", "N4"),
        ("について", "N3"),
    ]
    for gp, level in pts:
        conn.execute(
            "INSERT INTO grammar (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )
    conn.commit()


def test_mark_grammar_updates_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = mark_grammar(conn, "は", "known")
    assert out["grammar_point"] == "は"
    assert out["status"] == "known"
    row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point='は'"
    ).fetchone()
    assert row["status"] == "known"


def test_mark_grammar_rejects_bad_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(ValueError, match="status"):
        mark_grammar(conn, "は", "fluent")


def test_mark_grammar_unknown_point_raises(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    with pytest.raises(LookupError):
        mark_grammar(conn, "もうない", "known")


def test_mark_grammar_with_note(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "ながら", "learning", note="keep practicing")
    row = conn.execute(
        "SELECT note FROM grammar WHERE grammar_point='ながら'"
    ).fetchone()
    assert row["note"] == "keep practicing"


def test_list_known_grammar_filters_by_status(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    mark_grammar(conn, "は", "known")
    mark_grammar(conn, "も", "known")
    out = list_known_grammar(conn, status_filter=["known"])
    assert {x["grammar_point"] for x in out} == {"は", "も"}


def test_list_known_grammar_filters_by_level(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_screen = init_schema(conn); _seed(conn)  # noqa
    out = list_known_grammar(conn, level_filter=["N4"])
    assert {x["grammar_point"] for x in out} == {"ない", "ながら"}


def test_walk_grammar_streams_one_at_a_time(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    first = walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    assert first["done"] is False
    assert first["item"]["jlpt_level"] == "N5"
    second = walk_grammar(
        conn, level_filter=["N5"], status_filter=["unknown"], previous_response="k"
    )
    assert second["item"]["grammar_point"] != first["item"]["grammar_point"]
    # The previous one should now be 'known'
    prev_row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point=?",
        (first["item"]["grammar_point"],),
    ).fetchone()
    assert prev_row["status"] == "known"


def test_walk_grammar_done_when_no_more(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    while True:
        out = walk_grammar(
            conn, level_filter=["N3"], status_filter=["unknown"], previous_response="k"
        )
        if out["done"]:
            break
    # All N3 items should now be known
    row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point='について'"
    ).fetchone()
    assert row["status"] == "known"


def test_walk_grammar_skip_response(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    first = walk_grammar(conn, level_filter=["N5"], status_filter=["unknown"])
    walk_grammar(
        conn, level_filter=["N5"], status_filter=["unknown"], previous_response="s"
    )
    # 's' = skip; status unchanged
    row = conn.execute(
        "SELECT status FROM grammar WHERE grammar_point=?",
        (first["item"]["grammar_point"],),
    ).fetchone()
    assert row["status"] == "unknown"
```

> **Note on the test file:** there's an intentional typo (`init_screen = init_schema(conn)`) — the engineer should write the test exactly as shown above to verify it fails first, then **fix the typo to `init_schema(conn); _seed(conn)`** before the green run. (Pre-emptive fix in the green step below.)

- [ ] **Step 8.2: Run test to verify it fails**

Run: `uv run pytest tests/test_grammar.py -v`
Expected: ModuleNotFoundError. (Fix the typo above to `init_schema(conn); _seed(conn)` while writing the file too — it's a transcription artifact, not a test of the implementation.)

- [ ] **Step 8.3: Write `src/japanese_practice_mcp/tools/grammar.py`**

```python
import hashlib
import json
import sqlite3
from typing import Any, Literal

VALID_STATUSES = ("unknown", "learning", "known", "mastered")
RESPONSE_TO_STATUS = {"k": "known", "l": "learning", "u": "unknown", "m": "mastered"}


def list_known_grammar(
    conn: sqlite3.Connection,
    status_filter: list[str] | None = None,
    level_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if status_filter:
        where.append(f"status IN ({','.join('?' for _ in status_filter)})")
        params.extend(status_filter)
    if level_filter:
        where.append(f"jlpt_level IN ({','.join('?' for _ in level_filter)})")
        params.extend(level_filter)
    sql = "SELECT grammar_point, reading, jlpt_level, status, note FROM grammar"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY jlpt_level DESC, grammar_point ASC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def mark_grammar(
    conn: sqlite3.Connection,
    grammar_point: str,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; must be one of {VALID_STATUSES}"
        )
    if note is None:
        cur = conn.execute(
            "UPDATE grammar SET status = ?, updated_at = datetime('now') "
            "WHERE grammar_point = ?",
            (status, grammar_point),
        )
    else:
        cur = conn.execute(
            "UPDATE grammar SET status = ?, note = ?, updated_at = datetime('now') "
            "WHERE grammar_point = ?",
            (status, note, grammar_point),
        )
    if cur.rowcount == 0:
        raise LookupError(f"grammar point not found: {grammar_point!r}")
    row = conn.execute(
        "SELECT grammar_point, reading, jlpt_level, status, note FROM grammar "
        "WHERE grammar_point = ?",
        (grammar_point,),
    ).fetchone()
    return dict(row)


def _filter_hash(level_filter: list[str] | None, status_filter: list[str] | None) -> str:
    payload = json.dumps(
        {"level": sorted(level_filter or []), "status": sorted(status_filter or [])},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def walk_grammar(
    conn: sqlite3.Connection,
    level_filter: list[str] | None = None,
    status_filter: list[str] | None = None,
    previous_response: Literal["k", "l", "u", "m", "s"] | None = None,
) -> dict[str, Any]:
    """Stream one grammar point at a time for bulk-marking.

    Stateful via the `walk_state` table. If `previous_response` is supplied and
    the state row's current_grammar_id is set, the previous point's status is
    updated (unless response is 's' = skip).
    """
    fh = _filter_hash(level_filter, status_filter)
    state = conn.execute("SELECT * FROM walk_state WHERE id = 1").fetchone()

    # Apply previous response (if continuing the same filter set)
    if previous_response and state and state["filter_hash"] == fh and state["current_grammar_id"]:
        if previous_response != "s":
            new_status = RESPONSE_TO_STATUS.get(previous_response)
            if new_status is None:
                raise ValueError(
                    f"invalid previous_response {previous_response!r}; expected one of k/l/u/m/s"
                )
            conn.execute(
                "UPDATE grammar SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (new_status, state["current_grammar_id"]),
            )

    # Build query for next item
    where: list[str] = []
    params: list[Any] = []
    if level_filter:
        where.append(f"jlpt_level IN ({','.join('?' for _ in level_filter)})")
        params.extend(level_filter)
    if status_filter:
        where.append(f"status IN ({','.join('?' for _ in status_filter)})")
        params.extend(status_filter)
    sql = "SELECT id, grammar_point, reading, jlpt_level, status, note FROM grammar"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY jlpt_level DESC, id ASC LIMIT 1"
    nxt = conn.execute(sql, params).fetchone()

    if nxt is None:
        # Clear state, signal done
        conn.execute(
            "INSERT INTO walk_state (id, filter_hash, current_grammar_id, updated_at) "
            "VALUES (1, ?, NULL, datetime('now')) "
            "ON CONFLICT(id) DO UPDATE SET filter_hash=excluded.filter_hash, "
            "current_grammar_id=NULL, updated_at=datetime('now')",
            (fh,),
        )
        return {"done": True, "item": None, "remaining_estimate": 0}

    # Save new state
    conn.execute(
        "INSERT INTO walk_state (id, filter_hash, current_grammar_id, updated_at) "
        "VALUES (1, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET filter_hash=excluded.filter_hash, "
        "current_grammar_id=excluded.current_grammar_id, updated_at=datetime('now')",
        (fh, nxt["id"]),
    )
    # Estimate remaining (cheap COUNT)
    count_sql = "SELECT COUNT(*) FROM grammar"
    if where:
        count_sql += " WHERE " + " AND ".join(where)
    remaining = conn.execute(count_sql, params).fetchone()[0]
    return {
        "done": False,
        "item": {
            "grammar_point": nxt["grammar_point"],
            "reading": nxt["reading"],
            "jlpt_level": nxt["jlpt_level"],
            "status": nxt["status"],
            "note": nxt["note"],
        },
        "remaining_estimate": remaining,
        "hint": "Respond with previous_response='k' (known), 'l' (learning), 'u' (unknown), 'm' (mastered), or 's' (skip).",
    }
```

- [ ] **Step 8.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_grammar.py -v`
Expected: 9 passed (after fixing the typo noted in 8.1).

- [ ] **Step 8.5: Commit**

```bash
git add src/japanese_practice_mcp/tools/grammar.py tests/test_grammar.py
git commit -m "feat(tools): list_known_grammar, mark_grammar, walk_grammar"
```

---

## Task 9: Sampling tool (`sample_for_prompts`)

**Files:**
- Create: `src/japanese_practice_mcp/tools/sampling.py`
- Create: `tests/test_sampling.py`

- [ ] **Step 9.1: Write the failing test**

`tests/test_sampling.py`:

```python
import json
import random
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.grammar import mark_grammar
from japanese_practice_mcp.tools.sampling import sample_for_prompts


def _seed(conn) -> None:
    # Vocab
    for i, (ch, en, srs) in enumerate(
        [("猫", "cat", 5), ("犬", "dog", 7), ("家", "house", 2), ("水", "water", 9)],
        start=1,
    ):
        conn.execute(
            "INSERT INTO wk_subjects (id, object, characters, slug, level, meanings, readings, data_json, updated_at) "
            "VALUES (?, 'vocabulary', ?, ?, 1, ?, ?, '{}', '2024-01-01')",
            (i, ch, ch, json.dumps([en]), json.dumps(["x"])),
        )
        conn.execute(
            "INSERT INTO wk_assignments (id, subject_id, srs_stage, data_json, cached_at) "
            "VALUES (?, ?, ?, '{}', '2024-01-01')",
            (100 + i, i, srs),
        )
    # Grammar
    for gp, level in [("は", "N5"), ("も", "N5"), ("ない", "N4")]:
        conn.execute(
            "INSERT INTO grammar (grammar_point, jlpt_level) VALUES (?, ?)", (gp, level)
        )
    conn.commit()
    mark_grammar(conn, "は", "known")
    mark_grammar(conn, "ない", "known")


def test_sample_returns_filtered_items(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = sample_for_prompts(
        conn,
        count=2,
        vocab_filter={"min_srs_stage": 5},
        grammar_filter={"status_filter": ["known"]},
        rng=random.Random(0),
    )
    assert "vocabulary" in out and "grammar" in out
    assert len(out["vocabulary"]) <= 2
    assert len(out["grammar"]) <= 2
    for v in out["vocabulary"]:
        assert v["srs_stage"] >= 5
    for g in out["grammar"]:
        assert g["status"] == "known"


def test_sample_count_caps_results(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    out = sample_for_prompts(
        conn, count=1,
        vocab_filter={"min_srs_stage": 0},
        grammar_filter={},
        rng=random.Random(0),
    )
    assert len(out["vocabulary"]) == 1
    assert len(out["grammar"]) == 1


def test_sample_deterministic_with_seed(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn); _seed(conn)
    a = sample_for_prompts(
        conn, count=3,
        vocab_filter={"min_srs_stage": 0}, grammar_filter={},
        rng=random.Random(42),
    )
    b = sample_for_prompts(
        conn, count=3,
        vocab_filter={"min_srs_stage": 0}, grammar_filter={},
        rng=random.Random(42),
    )
    assert [v["characters"] for v in a["vocabulary"]] == [v["characters"] for v in b["vocabulary"]]
```

- [ ] **Step 9.2: Run test to verify it fails**

Run: `uv run pytest tests/test_sampling.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 9.3: Write `src/japanese_practice_mcp/tools/sampling.py`**

```python
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
```

- [ ] **Step 9.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sampling.py -v`
Expected: 3 passed.

- [ ] **Step 9.5: Commit**

```bash
git add src/japanese_practice_mcp/tools/sampling.py tests/test_sampling.py
git commit -m "feat(tools): sample_for_prompts (vocab + grammar)"
```

---

## Task 10: Log tools (`log_stuck_phrase`, `log_production_attempt`, `log_unknown_word`)

**Files:**
- Create: `src/japanese_practice_mcp/tools/logs.py`
- Create: `tests/test_logs.py`

- [ ] **Step 10.1: Write the failing test**

`tests/test_logs.py`:

```python
from pathlib import Path

from japanese_practice_mcp.db import connect, init_schema
from japanese_practice_mcp.tools.logs import (
    log_stuck_phrase,
    log_production_attempt,
    log_unknown_word,
)


def test_log_stuck_phrase(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    out = log_stuck_phrase(conn, phrase="the dispute escalated", context="news article")
    assert out["id"] >= 1
    row = conn.execute("SELECT phrase, context FROM stuck_phrases").fetchone()
    assert row["phrase"] == "the dispute escalated"
    assert row["context"] == "news article"


def test_log_stuck_phrase_no_context(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_stuck_phrase(conn, phrase="x")
    row = conn.execute("SELECT context FROM stuck_phrases").fetchone()
    assert row["context"] is None


def test_log_production_attempt(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    out = log_production_attempt(
        conn,
        prompt="Say 'I went to the store yesterday'",
        my_answer="昨日店に行きました",
        correct_answer="昨日店に行きました",
        verdict="correct",
    )
    assert out["id"] >= 1
    row = conn.execute(
        "SELECT prompt, my_answer, correct_answer, verdict FROM production_attempts"
    ).fetchone()
    assert row["verdict"] == "correct"


def test_log_unknown_word(tmp_db_path: Path) -> None:
    conn = connect(tmp_db_path); init_schema(conn)
    log_unknown_word(conn, word="紛争", context="news headline")
    row = conn.execute("SELECT word, context FROM unknown_words").fetchone()
    assert row["word"] == "紛争"
    assert row["context"] == "news headline"


def test_log_empty_phrase_rejected(tmp_db_path: Path) -> None:
    import pytest
    conn = connect(tmp_db_path); init_schema(conn)
    with pytest.raises(ValueError):
        log_stuck_phrase(conn, phrase="   ")
```

- [ ] **Step 10.2: Run test to verify it fails**

Run: `uv run pytest tests/test_logs.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 10.3: Write `src/japanese_practice_mcp/tools/logs.py`**

```python
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
) -> dict[str, Any]:
    p = _require(prompt, "prompt")
    a = _require(my_answer, "my_answer")
    c = _require(correct_answer, "correct_answer")
    v = _require(verdict, "verdict")
    cur = conn.execute(
        "INSERT INTO production_attempts (prompt, my_answer, correct_answer, verdict) "
        "VALUES (?, ?, ?, ?)",
        (p, a, c, v),
    )
    return {"id": cur.lastrowid, "prompt": p, "verdict": v}


def log_unknown_word(
    conn: sqlite3.Connection,
    word: str,
    context: str | None = None,
) -> dict[str, Any]:
    w = _require(word, "word")
    cur = conn.execute(
        "INSERT INTO unknown_words (word, context) VALUES (?, ?)",
        (w, context),
    )
    return {"id": cur.lastrowid, "word": w, "context": context}
```

- [ ] **Step 10.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_logs.py -v`
Expected: 5 passed.

- [ ] **Step 10.5: Commit**

```bash
git add src/japanese_practice_mcp/tools/logs.py tests/test_logs.py
git commit -m "feat(tools): log_stuck_phrase, log_production_attempt, log_unknown_word"
```

---

## Task 11: MCP server wiring

**Files:**
- Create: `src/japanese_practice_mcp/server.py`

This task ties everything together. No unit tests for the server itself — the tool functions are already tested; the server is plumbing. A smoke test will be added later.

- [ ] **Step 11.1: Write `src/japanese_practice_mcp/server.py`**

```python
"""MCP server entry point. Wires FastMCP to our tool functions."""
import sqlite3
import sys
from pathlib import Path
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
    """Refresh WK caches if needed; return a list of staleness notes (empty if fresh)."""
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
        Default min_srs_stage=5 ("Guru+", what WK considers 'known').
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
    app.run()  # default transport: stdio


if __name__ == "__main__":
    run()
```

- [ ] **Step 11.2: Smoke-import the module**

Run: `uv run python -c "from japanese_practice_mcp.server import build_app; print('ok')"`
Expected: `ok`

- [ ] **Step 11.3: Run full test suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 11.4: Smoke-launch the server with a dummy token**

Run (PowerShell):
```powershell
$env:JPMCP_WANIKANI_TOKEN = "dummy"
$env:JPMCP_DATA_DIR = "$PWD\.smoke"
echo $null | uv run python -m japanese_practice_mcp 2>$null
```

This will likely error on the WK API call when a tool is invoked, but the server should *start* and exit cleanly when stdin closes. Just confirm no import-time exceptions. Expected: process exits (no traceback at startup).

Then remove the smoke dir: `Remove-Item -Recurse -Force .smoke`.

- [ ] **Step 11.5: Commit**

```bash
git add src/japanese_practice_mcp/server.py
git commit -m "feat(server): wire FastMCP to tool functions with audit + staleness notes"
```

---

## Task 12: README + register command

**Files:**
- Create: `README.md`

- [ ] **Step 12.1: Write `README.md`**

```markdown
# japanese-practice-mcp

A local MCP server that exposes my WaniKani progress and a private SQLite database of
grammar/log entries to Claude clients, so Claude can build Japanese production prompts
using only items I know.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/<you>/japanese-practice-mcp.git
cd japanese-practice-mcp
uv sync
```

## Configure

Create a config file at the platform-default location, or set env vars.

**Linux:** `~/.config/japanese-practice-mcp/config.toml`
**macOS:** `~/Library/Application Support/japanese-practice-mcp/config.toml`
**Windows:** `%APPDATA%\japanese-practice-mcp\config.toml`

```toml
wanikani_token = "your-personal-access-token"
# data_dir = "/custom/path"      # optional; default is platform-appropriate
# subjects_max_age_days = 7      # optional
# assignments_ttl_seconds = 3600 # optional
```

Get a WaniKani token at https://www.wanikani.com/settings/personal_access_tokens
(read-only is sufficient).

Env-var overrides:
- `JPMCP_WANIKANI_TOKEN` — overrides the token from the config file
- `JPMCP_DATA_DIR` — overrides the data directory
- `JPMCP_CONFIG` — alternate config file path

## Register with Claude Code

```bash
claude mcp add japanese-practice-mcp \
    -- uv --directory <ABSOLUTE_PATH_TO_REPO> run python -m japanese_practice_mcp
```

Verify: `claude mcp list` should show the server. In Claude Code, ask
*"What WaniKani vocabulary do I know at Guru+?"* and watch the tool call go through.

## What you can do once registered

- **Walk grammar:** *"walk me through N5 grammar points I haven't marked, k/l/u/m, fast"*
- **Production prompts:** *"give me 5 production prompts using vocab I know at Guru+
  and grammar I've marked known"*
- **Log getting stuck:** *"log: I got stuck trying to say 'the dispute escalated'"*
- **Update a mark:** *"mark 〜ながら as learning"*

## Tools exposed

| Tool | Purpose |
|---|---|
| `list_known_vocabulary` | WK vocab at or above an SRS stage |
| `is_word_known` | Fast lookup by Japanese or English |
| `list_known_grammar` | Grammar list filtered by status/level |
| `mark_grammar` | Single-point status update |
| `walk_grammar` | Stream one grammar point at a time + bulk-mark |
| `sample_for_prompts` | Random vocab+grammar sample for prompt building |
| `log_stuck_phrase` | Append-only stuck-phrase log |
| `log_production_attempt` | Append-only production attempt log |
| `log_unknown_word` | Append-only unknown-word log |

## Data layout

Everything lives in one SQLite database at `<data_dir>/japanese-practice.db`. Back
it up by copying that single file. WAL files (`-wal`, `-shm`) are recreated.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | I'm fluent in Python; stdlib `tomllib` |
| MCP SDK | `mcp` (FastMCP) | Official, decorator-based, stdio out of the box |
| Package manager | `uv` | Fast, reproducible, single binary |
| SQLite library | stdlib `sqlite3` | Schema is small — ORM would be overkill |
| Tests | `pytest` + `pytest-httpx` | Clean HTTP mocking |
| Layout | `src/japanese_practice_mcp/` | Avoids import-from-cwd footgun |
| Data dir | `platformdirs.user_data_dir(...)` | XDG-compliant on Linux, sensible on macOS/Windows |
| Concurrency | Sync end-to-end | One user, one process, blocking I/O is fine |
| License | MIT | Permissive, common |

## Out of scope (deliberately)

Production-SRS scheduling, tutor brief tools, coverage checks on passages, cohort
sampling, leech detection, log search, mined-vocab triage, journal/marker UI,
multi-source grammar reconciliation, auto-discovering Bunpro's rotating hash.

## Tests

```bash
uv run pytest
```

## Remote transport (deferred)

The server-tool boundary is transport-agnostic — `server.py` is the only file that
knows about FastMCP. Adding HTTPS later means swapping `app.run()` for a Starlette
mount; no tool logic changes.

## License

MIT. See [LICENSE](LICENSE).
```

- [ ] **Step 12.2: Commit**

```bash
git add README.md
git commit -m "docs: README with install, register, decisions, scope"
```

---

## Task 13: GitHub repo creation + push

- [ ] **Step 13.1: Check `gh` auth**

Run: `gh auth status`
Expected: shows the authenticated GitHub user. **If not authenticated**, STOP and ask the user to run `gh auth login`.

- [ ] **Step 13.2: Create the GitHub repo**

Run:
```bash
gh repo create japanese-practice-mcp --public --source . --remote origin --description "Local MCP server exposing my Japanese learning data for production practice."
```
Expected: repo created, `origin` configured.

If the repo name already exists on the user's account, STOP and ask whether to use a different name.

- [ ] **Step 13.3: Push**

Run:
```bash
git push -u origin main
```
Expected: all commits pushed.

- [ ] **Step 13.4: Verify**

Run: `gh repo view --web` to open the repo in a browser, OR `gh repo view` to print details. Confirm the README rendered.

---

## Self-review (run before declaring the plan complete)

**Spec coverage:**

| Spec item | Task |
|---|---|
| WaniKani v2 API w/ token auth, aggressive cache for subjects, 1h TTL for assignments | Task 5 (`subjects_max_age_days`, `assignments_ttl_seconds`) |
| Local SQLite, grammar list seeded from bunpro JSON dump, snapshot committed | Tasks 1, 3, 4 |
| Grammar columns: point, reading, level, status, note, timestamps | Task 3 (note: `reading` is nullable since bunpro lacks it; user can fill via `mark_grammar` note) |
| Stuck phrases / production attempts / unknown words tables | Task 3, 10 |
| Config: token, data dir, env-var override, never in source | Task 2 |
| `list_known_vocabulary(min_srs_stage, limit, source_filter)` | Task 7 |
| `list_known_grammar(status_filter, level_filter)` | Task 8 |
| `is_word_known(japanese_or_english)` | Task 7 |
| `sample_for_prompts(count, vocab_filter, grammar_filter)` | Task 9 |
| `walk_grammar(level_filter, status_filter)` with k/l/u/m responses | Task 8 |
| `mark_grammar(grammar_point, status, note)` | Task 8 |
| `log_stuck_phrase`, `log_production_attempt`, `log_unknown_word` | Task 10 |
| Local-first, no phoning home | Yes — only outbound traffic is to WaniKani |
| Graceful degradation w/ staleness indicator | Task 5 + Task 11 (`staleness_notes` field returned by relevant tools) |
| Meaningful error messages | Task 11 — exceptions in tools propagate as MCP errors; staleness is non-fatal |
| Audit every tool call | Task 6, applied in Task 11 |
| Transport-agnostic for future HTTPS | Task 11 — tool functions are pure; only `server.py` knows about FastMCP |
| Unit tests on tool logic | Tasks 2,3,4,5,6,7,8,9,10 |
| One command to install (`uv sync`), one to register (`claude mcp add`) | Task 12 |
| Note decisions in README | Task 12 |
| GitHub push | Task 13 |

**Placeholder scan:** None — every step contains complete code or exact commands.

**Type consistency:** Tool function signatures called from `server.py` match their definitions in `tools/*.py`. Audit decorator is consistent across the codebase.

**Out-of-scope:** No code, columns, or tasks are present for the deferred features (SRS scheduling, cohort sampling, leech detection, log search, journal, marker app, etc.).

---
