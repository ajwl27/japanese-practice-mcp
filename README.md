# japanese-practice-mcp

A local MCP server that turns Claude into a *production-practice* partner for
Japanese. It exposes what you already know (from WaniKani) and what you've
marked or logged yourself (in a local SQLite database), so Claude can build
prompts using only items in your active vocabulary, walk you through grammar
quickly, and remember what you're struggling with across sessions.

## What it does

In a Claude Code session, once registered, you can say things like:

- *"Walk me through N4 grammar I haven't marked, show a quick example with each, k/l/u/m."*
- *"Give me 5 production prompts using stuff I solidly know."*
- *"Actually 食べる is fading for me — mark it as struggling."*
- *"What should I be drilling right now?"*
- *"I learned 足を引っ張る from Mariko today, log it."*
- *"I keep getting 約束 wrong, add it to my priority list."*
- *"Mark ても as learning."*

Claude figures out which tool to call and disambiguates with you when your
query matches multiple items.

## How it works

Three data layers, one process, one SQLite file:

1. **WaniKani cache (read-only mirror).** On startup, the server syncs WK
   subjects and assignments into SQLite. Subjects refresh weekly; assignments
   refresh hourly. When the WaniKani API is unreachable, you get cached data
   with a `staleness_notes` field telling Claude how stale it is.

2. **Grammar split into seed + state.** A pinned snapshot of the
   [flio/wkanki](https://gitlab.com/flio/wkanki) Bunpro grammar dump ships
   with the repo as a read-only seed (canonical form + JLPT level only — no
   readings, meanings, or examples). Your marks live in a separate
   `grammar_state` table. If you've never touched a grammar point, it has no
   row. Reseeding never overwrites your marks.

3. **Personal-state tables.** WaniKani overrides (fading/struggling/priority/
   buried), expressions you've logged, mined words you've encountered, stuck
   phrases, production attempts — all in plain SQLite tables that Claude reads
   and writes through tools.

The schema deliberately stores **only the canonical form** for anything Claude
can re-derive — no frozen readings, meanings, or type tags. Claude regenerates
interpretation from the form on every read. This keeps the database small and
prevents stale-metadata drift.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ajwl27/japanese-practice-mcp.git
cd japanese-practice-mcp
uv sync
```

## Configure

Get a WaniKani personal access token (read-only is sufficient):
<https://www.wanikani.com/settings/personal_access_tokens>

Then either drop a config file at the platform-default location:

- **Linux:** `~/.config/japanese-practice-mcp/config.toml`
- **macOS:** `~/Library/Application Support/japanese-practice-mcp/config.toml`
- **Windows:** `%APPDATA%\japanese-practice-mcp\config.toml`

```toml
wanikani_token = "your-personal-access-token"
# data_dir = "/custom/path"        # optional
# subjects_max_age_days = 7        # optional
# assignments_ttl_seconds = 3600   # optional
```

…or set env vars (handy for keeping the token out of files):

- `JPMCP_WANIKANI_TOKEN` — overrides the token from config
- `JPMCP_DATA_DIR` — overrides the data directory
- `JPMCP_CONFIG` — alternate config file path

## Register with Claude Code

```bash
claude mcp add japanese-practice -- uv --directory <ABSOLUTE_PATH_TO_REPO> run python -m japanese_practice_mcp
```

Verify with `claude mcp list`. First call to a vocab tool triggers an initial
WaniKani sync (~30s for the full subject set).

## Tools

| Tool | What it does |
|---|---|
| `list_known_vocabulary` | WK vocab at or above an SRS stage; auto-excludes fading/struggling/buried |
| `is_word_known` | Fuzzy lookup by Japanese, kana, or English. Returns all matches with SRS + override |
| `override_vocabulary` | Mark a WK item fading / struggling / priority / buried |
| `list_known_grammar` | Grammar list filtered by status / JLPT level |
| `mark_grammar` | Fuzzy status update; returns candidates on ambiguity |
| `walk_grammar` | Stream one grammar point at a time + remaining count, for fast bulk-marking |
| `sample_for_prompts` | Random vocab + grammar sample for prompt-building |
| `list_priority_items` | Unified "what should I drill" view |
| `log_expression` | Log an idiom / compound / proverb / set phrase |
| `log_mined_word` | Log a word you didn't know |
| `log_stuck_phrase` | Log an English phrase you got stuck trying to say |
| `log_production_attempt` | Log a prompt + your answer + correct answer + verdict |

Every tool call is recorded in the `tool_audit` table.

## Schema philosophy

**Store the canonical form. Re-derive everything else.**

Meanings, readings, JLPT-level labels, type tags, examples — Claude can
regenerate all of this from the canonical Japanese form on every read. Storing
it freezes interpretation at write time and creates a maintenance burden for
data that's easier to recompute. So the personal-state tables only carry what
Claude *can't* infer: the user's status, their notes, timestamps, and the
override state.

This applies to `grammar_state` (form + status + note + timestamp),
`expressions` (form + context + note + timestamp), `mined_words` (word +
context + note + timestamp), and `wk_overrides` (subject_id + status + note +
timestamp). The grammar seed itself is form + JLPT level only.

## Data layout

Everything lives in one SQLite database at `<data_dir>/japanese-practice.db`.
Back it up by copying that file. WAL files (`-wal`, `-shm`) are auto-recreated.

## Migrating from v0.1

v0.2 changes the schema significantly. On first startup, the server applies a
migration that:

- Splits the old `grammar` table into `grammar_seed` (form + level) and
  `grammar_state` (only your actual marks). The `reading` column is dropped.
- Renames `unknown_words` → `mined_words` and adds a `note` column.
- Creates new `expressions` and `wk_overrides` tables.

User data is preserved. Migrations are idempotent and tracked in the
`schema_version` table.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Stdlib `tomllib`; clean MCP SDK |
| MCP SDK | `mcp` (FastMCP) | Official Anthropic SDK; decorator-based; stdio default |
| Package manager | `uv` | Fast, reproducible, single binary |
| Storage | SQLite via stdlib `sqlite3` | Schema is small; one file to back up |
| Schema | Canonical form + state only | Don't freeze metadata Claude can re-derive |
| Data dir | `platformdirs.user_data_dir(...)` | XDG-compliant; cross-platform |
| Concurrency | Sync end-to-end | One user, one process |
| Tests | `pytest` + `pytest-httpx` | Standard; clean HTTP mocking |
| License | MIT | Permissive |

## Out of scope (deliberately deferred)

Production-SRS scheduling, tutor brief tools, coverage checks on passages,
cohort sampling, leech detection, log search, mined-vocab triage workflow,
journal / marker UI, multi-source grammar reconciliation, auto-discovering
Bunpro's rotating data hash.

## Tests

```bash
uv run pytest
```

## Remote transport (deferred)

Tool logic is transport-agnostic — only [`server.py`](src/japanese_practice_mcp/server.py)
knows about FastMCP. Adding HTTPS later means swapping `app.run()` for a
Starlette mount; no tool logic changes.

## License

MIT. See [LICENSE](LICENSE).
