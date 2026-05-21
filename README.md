# japanese-practice-mcp

A local MCP server that exposes my WaniKani progress and a private SQLite database of
grammar/log entries to Claude clients, so Claude can build Japanese production prompts
using only items I know.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ajwl27/japanese-practice-mcp.git
cd japanese-practice-mcp
uv sync
```

## Configure

Create a config file at the platform-default location, or set env vars.

- **Linux:** `~/.config/japanese-practice-mcp/config.toml`
- **macOS:** `~/Library/Application Support/japanese-practice-mcp/config.toml`
- **Windows:** `%APPDATA%\japanese-practice-mcp\config.toml`

```toml
wanikani_token = "your-personal-access-token"
# data_dir = "/custom/path"      # optional; default is platform-appropriate
# subjects_max_age_days = 7      # optional
# assignments_ttl_seconds = 3600 # optional
```

Get a WaniKani token at <https://www.wanikani.com/settings/personal_access_tokens>
(read-only is sufficient).

Env-var overrides (handy for testing or for keeping the token out of files):

- `JPMCP_WANIKANI_TOKEN` — overrides the token from the config file
- `JPMCP_DATA_DIR` — overrides the data directory
- `JPMCP_CONFIG` — alternate config file path

## Register with Claude Code

```bash
claude mcp add japanese-practice -- uv --directory <ABSOLUTE_PATH_TO_REPO> run python -m japanese_practice_mcp
```

Verify with `claude mcp list`. In a Claude Code session, ask
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
| `list_known_vocabulary` | WK vocabulary at or above an SRS stage |
| `is_word_known` | Fast lookup by Japanese or English |
| `list_known_grammar` | Grammar list filtered by status/level |
| `mark_grammar` | Single-point status update |
| `walk_grammar` | Stream one grammar point at a time + bulk-mark with `k`/`l`/`u`/`m`/`s` |
| `sample_for_prompts` | Random vocab+grammar sample for prompt building |
| `log_stuck_phrase` | Append-only stuck-phrase log |
| `log_production_attempt` | Append-only production attempt log |
| `log_unknown_word` | Append-only unknown-word log |

Every tool call is recorded in the `tool_audit` table. Tools that hit WaniKani
include a `staleness_notes` field — empty when the cache is fresh, populated
with a human-readable note when serving stale data (e.g. API was unreachable).

## Data layout

Everything lives in one SQLite database at `<data_dir>/japanese-practice.db`. Back
it up by copying that single file. WAL files (`-wal`, `-shm`) are auto-recreated.

The grammar list is seeded on first run from the committed snapshot at
[`seed/bunpro_deck_index.json`](seed/bunpro_deck_index.json) (from
[flio/wkanki](https://gitlab.com/flio/wkanki) — pinned so the seed never drifts).
Re-seeding is idempotent: existing rows (and any status you've set on them) are
preserved.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Fluent; stdlib `tomllib`; clean MCP SDK |
| MCP SDK | `mcp` (FastMCP) | Official Anthropic SDK; decorator-based; stdio default |
| Package manager | `uv` | Fast, reproducible, single binary |
| SQLite library | stdlib `sqlite3` | Schema is small — ORM would be overkill |
| Tests | `pytest` + `pytest-httpx` | Standard; clean HTTP mocking |
| Layout | `src/japanese_practice_mcp/` | Avoids import-from-cwd footgun |
| Data dir | `platformdirs.user_data_dir(...)` | XDG-compliant on Linux, sensible on macOS/Windows |
| Concurrency | Sync end-to-end | One user, one process, blocking I/O is fine |
| License | MIT | Permissive, common |

## Out of scope (deliberately deferred)

Production-SRS scheduling, tutor brief tools, coverage checks on passages, cohort
sampling, leech detection, log search, mined-vocab triage, journal/marker UI,
multi-source grammar reconciliation, auto-discovering Bunpro's rotating hash.

## Tests

```bash
uv run pytest
```

## Remote transport (deferred)

The tool layer is transport-agnostic — only [`server.py`](src/japanese_practice_mcp/server.py)
knows about FastMCP. Adding HTTPS later means swapping `app.run()` for a Starlette
mount; no tool logic changes.

## License

MIT. See [LICENSE](LICENSE).
