# japanese-practice-mcp

A bridge between [Claude](https://claude.ai) and your Japanese learning data,
so Claude can build practice prompts using only the words and grammar **you
already know**, walk you through unfamiliar grammar quickly, and remember what
you're struggling with from one conversation to the next.

You bring two things:

- A **WaniKani** account ([wanikani.com](https://www.wanikani.com)), the SRS
  app that tracks the Japanese vocabulary and kanji you've learned. The
  server reads your progress from WaniKani's API.
- A way to chat with Claude that supports **MCP servers** — either
  [Claude Code](https://docs.anthropic.com/claude/docs/claude-code) (the CLI)
  or the [Claude desktop app](https://claude.ai/download). (The browser
  version of Claude doesn't currently work — it needs a remote-hosted
  server, and this one runs locally on your computer.)

> **What's MCP?** It's a way for Claude to use tools you give it during a
> conversation. This project provides such tools: ask Claude *"give me 5
> production prompts using stuff I know"* and it calls these tools behind
> the scenes to look up what's in your WaniKani Guru pile and what grammar
> you've marked as confident.

## What you can do

Once it's set up, you can say things like this to Claude and it will just
work:

- *"Walk me through some N4 grammar I haven't marked yet — one at a time, give
  me a quick example, and ask me whether I know each one."*
- *"Give me 5 production prompts using vocabulary I solidly know."*
- *"Actually 食べる is fading for me — mark it as something I'm struggling with."*
- *"What should I be drilling right now?"*
- *"I learned the idiom 足を引っ張る today, log it for me."*
- *"I keep getting 約束 wrong — add it to my priority list."*
- *"Mark ても as something I'm learning."*

Claude figures out which tool to call. If your phrasing is ambiguous (say,
multiple grammar points match), it'll ask you to clarify rather than guess.

## How it works

Everything lives in one small SQLite database on your computer:

1. **Your WaniKani progress** is mirrored locally so Claude can see, instantly,
   which vocabulary you know at which SRS level. The mirror refreshes
   automatically (weekly for the word list, hourly for your SRS state). If
   WaniKani's servers are down, you keep working with the cached data.
2. **A grammar list** (≈900 Japanese grammar points across JLPT N5–N1, from
   the open [Bunpro deck dump](https://gitlab.com/flio/wkanki)) ships with
   the project. You mark items as `learning`, `known`, or `mastered` as you
   go. Anything you haven't touched is "unknown".
3. **Personal notes:** words you've encountered but didn't know, expressions
   you want to remember, phrases you got stuck trying to say, and corrections
   on WaniKani's view of your knowledge (e.g. "yes WaniKani thinks I know
   this, but actually I'm forgetting it").

When you talk to Claude, it reads from these tables, writes back when you
ask it to record something, and uses your data to keep its prompts grounded
in things you actually know.

## Install

You'll need:

- **Python 3.11 or newer** ([python.org](https://www.python.org/downloads/))
- **uv**, a Python package manager ([install instructions](https://docs.astral.sh/uv/getting-started/installation/))
- **git** ([git-scm.com](https://git-scm.com/downloads))

In a terminal:

```bash
git clone https://github.com/ajwl27/japanese-practice-mcp.git
cd japanese-practice-mcp
uv sync
```

`uv sync` downloads the dependencies into an isolated environment. It takes
about a minute.

## Get a WaniKani token

The server needs read-only access to your WaniKani account.

1. Go to <https://www.wanikani.com/settings/personal_access_tokens>.
2. Click **Generate a new token**.
3. Leave all the permission checkboxes unchecked — read-only is enough.
4. Copy the token. It looks like a UUID:
   `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.

Now tell the server about it. The easiest way is a small config file at a
fixed location:

| Your OS | Folder to create | Full path to the file |
|---|---|---|
| Linux | `~/.config/japanese-practice-mcp/` | `~/.config/japanese-practice-mcp/config.toml` |
| macOS | `~/Library/Application Support/japanese-practice-mcp/` | `~/Library/Application Support/japanese-practice-mcp/config.toml` |
| Windows | `%APPDATA%\japanese-practice-mcp\` | `%APPDATA%\japanese-practice-mcp\config.toml` |

> **Where is `%APPDATA%` on Windows?** It's a shortcut to
> `C:\Users\<your-username>\AppData\Roaming`. The fastest way to open it:
> press **Win + R**, type `%APPDATA%`, hit Enter. A File Explorer window
> opens at the right place. Create a new folder called
> `japanese-practice-mcp` inside it, then create `config.toml` inside that.

Put a single line in `config.toml`:

```toml
wanikani_token = "paste-your-token-here"
```

Save and close. The server will find it automatically next time it starts.

> If you'd rather use an environment variable, set
> `JPMCP_WANIKANI_TOKEN=your-token` before launching Claude. The variable
> takes precedence over the config file when both are set.

## Connect it to Claude

### Claude Code (terminal)

In **macOS / Linux / Git Bash on Windows**:

```bash
claude mcp add japanese-practice -- uv --directory <ABSOLUTE_PATH_TO_REPO> run python -m japanese_practice_mcp
```

In **Windows PowerShell**, the `--` separator gets eaten before reaching
Claude Code. Use the `--%` stop-parsing token instead:

```powershell
claude mcp add japanese-practice --% -- uv --directory C:/Users/you/japanese-practice-mcp run python -m japanese_practice_mcp
```

Replace the path with where you cloned the repo (run `pwd` inside that
folder to see it). **Use forward slashes** in the path — they work on
Windows and avoid backslash-escaping headaches.

Verify with `claude mcp list` — you should see
`japanese-practice: ... - ✓ Connected`.

By default the server is added at "local" scope (the current project
only). To make it available from any directory, add `-s user`:

```bash
claude mcp add japanese-practice -s user -- uv --directory <ABSOLUTE_PATH_TO_REPO> run python -m japanese_practice_mcp
```

Then start a Claude Code session and try one of the example prompts above.

### Claude desktop app

The desktop app's **Settings → Extensions** screen is for one-click
prepackaged extensions (`.mcpb` files reviewed by Anthropic). For a local
project like this one, you still need to add a small JSON snippet by hand —
the app provides a button that opens the right file for you.

1. Open the Claude desktop app.
2. Open **Settings → Developer → Edit Config**. This opens
   `claude_desktop_config.json` in your text editor.
3. Add (or merge) the `japanese-practice` entry below into the file. If
   the file is empty, paste the whole block; if it already has
   `mcpServers`, add the inner `"japanese-practice": {...}` entry alongside
   the others.

   ```json
   {
     "mcpServers": {
       "japanese-practice": {
         "command": "uv",
         "args": [
           "--directory", "<ABSOLUTE_PATH_TO_REPO>",
           "run", "python", "-m", "japanese_practice_mcp"
         ]
       }
     }
   }
   ```

   Replace `<ABSOLUTE_PATH_TO_REPO>` with the full path to where you cloned
   this repo (e.g. `C:\\Users\\you\\japanese-practice-mcp` on Windows —
   **note the double backslashes** inside JSON strings).
4. Save the file and fully quit + restart the desktop app.
5. In a new conversation, you should see a small tool indicator (often a
   slider/hammer icon) confirming the server is connected.

If something goes wrong, the desktop app shows MCP server errors at
**Settings → Developer**.

### First conversation

The very first time you ask Claude something that needs your WaniKani data,
the server downloads your full subject list from WaniKani. This takes about
30 seconds. After that it's instant — the data is cached locally and only
refreshed in the background.

## The tools Claude can use

You usually don't need to know these by name — Claude picks the right one
based on what you ask. But here's the cheat sheet:

| Tool | What it does |
|---|---|
| `list_known_vocabulary` | Lists WaniKani words you know at or above a given SRS stage. Skips anything you've flagged as fading, struggling, or buried. |
| `is_word_known` | Looks up a word (in Japanese, kana, or English) and tells Claude where it is in your WaniKani progress. |
| `override_vocabulary` | Marks a WaniKani word as fading, struggling, priority, or buried — to override what WaniKani thinks you know. |
| `list_known_grammar` | Lists grammar points filtered by JLPT level and/or by how well you know them. |
| `mark_grammar` | Records that you've reached a new status on a grammar point (learning / known / mastered). |
| `walk_grammar` | Streams grammar points one at a time, with a remaining counter, for fast review sessions. |
| `sample_for_prompts` | Picks a random sample of words and grammar to seed a practice prompt. |
| `list_priority_items` | A combined "what should I drill right now" view across vocabulary, grammar, and your notes. |
| `log_expression` | Records an idiom, four-character compound, proverb, set phrase, or onomatopoeia. |
| `log_mined_word` | Records a word you encountered but didn't know. |
| `log_stuck_phrase` | Records an English phrase you got stuck trying to say in Japanese. |
| `log_production_attempt` | Records a production prompt, your answer, the correct answer, and how it went. |

Every tool call is logged to a `tool_audit` table inside the database, so
you can audit what Claude did later.

## Where your data lives

Everything's in one SQLite file at `<data_dir>/japanese-practice.db`. The
default `data_dir`:

| Your OS | Path |
|---|---|
| Linux | `~/.local/share/japanese-practice-mcp/` |
| macOS | `~/Library/Application Support/japanese-practice-mcp/` |
| Windows | `%LOCALAPPDATA%\japanese-practice-mcp\` |

To back up everything you've logged and marked, copy that single `.db` file.
The two adjacent `-wal` and `-shm` files are temporary and auto-recreated.

## Schema philosophy (for the curious)

The database deliberately stores **only the canonical Japanese form** for
anything Claude can re-derive — no frozen meanings, readings, or type tags.
Meanings change with context; readings depend on how a word is used; type
tags are interpretation. Claude regenerates all of that from the form on
every read, which keeps the database small and avoids stale-metadata drift.

So the personal-state tables only carry what Claude *can't* infer: your
chosen status, your notes, timestamps, and override flags.

## Migrating from v0.1

If you used an earlier version, the v0.2 server auto-upgrades your database
on first startup. Your existing marks and logs are preserved. Migrations are
idempotent and tracked in a `schema_version` table.

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

## Out of scope (deliberately)

This project is intentionally small. It does **not** include: an SRS
scheduler, a leech-detection algorithm, full-text search over your logs, a
mined-vocab triage UI, a journal, a notes app, multi-source grammar
reconciliation, or auto-discovery of Bunpro's rotating data hash. The tools
here are the surface; the intelligence is Claude.

## Running the tests

```bash
uv run pytest
```

## Remote / hosted version (not yet)

Right now the server only runs on your own machine, communicating with
Claude over the standard MCP stdio transport. A future version could expose
the same tools over HTTPS so that the browser version of Claude could use
them too. The code is structured to make that swap easy — only `server.py`
would need to change.

## License

MIT. See [LICENSE](LICENSE).

## Configuration knobs

For reference, the full set of optional settings in `config.toml`:

```toml
wanikani_token = "wk_…"              # required
data_dir = "/custom/path"            # default: platform-appropriate user data dir
subjects_max_age_days = 7            # how long before re-syncing WK's word list
assignments_ttl_seconds = 3600       # how long before re-syncing your SRS state
```

Environment variables (override the file when set):

- `JPMCP_WANIKANI_TOKEN`
- `JPMCP_DATA_DIR`
- `JPMCP_CONFIG` (alternate path to `config.toml`)
