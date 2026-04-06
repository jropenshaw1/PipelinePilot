# CLAUDE.md — PipelinePilot Agent Instructions

This file governs how AI coding agents (Claude Code, Cursor, Codex, etc.) work in this repo.
Read this file at the start of every session. These are standing orders, not suggestions.

## What This Repo Is

PipelinePilot is a job search pipeline tracker built in Python with a SQLite backend.
It is a personal tool — single user, no multi-tenancy, no auth layer.
The filesystem is the source of truth. SQLite is a derived, rebuildable index.

**Stack:** Python 3.x, SQLite, filesystem-first architecture
**Primary files:** `pipelinepilot.py`, `database.py`, `models.py`, `config.py`, `fit_analysis_engine.py`, `ob_bridge.py`
**Database:** `pipelinepilot.db` (SQLite, single file, rebuildable via `rebuild_index`)

## Behavioral Standards (TSH-9 / LENS)

These govern how you interact, not just what you build.

**TSH-9 anchor:** Truth-anchored, direct, peer-level.
- State uncertainty explicitly. Never confident-sound on weak ground.
- Name tradeoffs and limits plainly. Peer-level candor over politeness.
- If something will break, say so before executing.

**LENS constraints (applied to all output):**
1. **Confirm Before Executing** — For any multi-step or consequential change, state the plan and wait for approval before touching files.
2. **Verify Before Including** — Do not invent or infer schema fields, function names, or conventions. Read the actual code first.
3. **Substance Before Surface** — Lead with correctness and gaps. Formatting and polish come after.
4. **Precise Word, Not Approximate Word** — Exact, concrete language. No filler: "genuinely," "great question," "absolutely."
5. **Actual Reasoning, Not Plausible Sentiment** — Show the reasoning chain. Not "this is cleaner" but "this avoids X problem because Y."
6. **Voice Over Formula** — High information density, no boilerplate, no stock openers.

## Architecture Rules

- **SQLite only.** No Postgres syntax. No UUID, TIMESTAMPTZ, BIGSERIAL, plpgsql, or auth.users.
- **TEXT for all dates.** ISO 8601 format: YYYY-MM-DD. Never use DATE type with SQLite-incompatible assumptions.
- **INTEGER PRIMARY KEY AUTOINCREMENT** for new tables. Not UUID.
- **TEXT foreign keys** to `opportunities(folder_name)` — that is the primary key of the main table.
- **PRAGMA foreign_keys = ON** belongs in the connection setup, not inside schema strings.
- **Never use `DROP TABLE`, `DROP DATABASE`, `TRUNCATE`, or unqualified `DELETE FROM`.**
- **Never alter or drop existing columns** in the `opportunities` table. Adding columns is fine.
- `SCHEMA` in `database.py` is the canonical opportunities table. Do not modify it without explicit instruction.

## Code Standards

- Follow existing naming conventions: `snake_case` for functions and variables, descriptive names.
- CHECK constraints use Title Case values matching PipelinePilot's existing style (e.g. `'Phone Screen'`, not `'phone_screen'`).
- All new tables must include `date_created TEXT NOT NULL` and `date_modified TEXT NOT NULL`.
- Migration functions must be idempotent — use `CREATE TABLE IF NOT EXISTS`.
- New schema constants follow the pattern: `TABLENAME_SCHEMA = """..."""` alongside the existing `SCHEMA` constant.

## Things You Must Not Do

- Do not add columns or tables that were not explicitly requested.
- Do not change field names from what was agreed in the plan.
- Do not substitute your own judgment for the agreed schema — if something is unclear, ask.
- Do not run any SQL against the database without showing the full statement first.
- Do not assume Postgres conventions. Always check SQLite compatibility.
- Do not add `scheduled_time`, `timezone`, `interviewer_email`, `location`, or any other field unless explicitly asked.

## Working Style

- **Show the plan before executing.** For any change touching more than one function, present the full diff or proposed code block and wait for approval.
- **Small tasks, test, commit.** One logical change per commit. Do not bundle unrelated changes.
- **If a task will touch more than 3 files, propose a plan first.**
- **If you have been running for more than 5 minutes without showing results, stop and check.**
- Commit messages follow the pattern: `feat:`, `fix:`, `refactor:`, `docs:` prefix + short description.

## Key Reference Files

- `database.py` — schema definitions and all database operations (opportunities, interviews, quick_fit_log)
- `models.py` — constants: STATUS_VALUES, SOURCE_VALUES, LOCATION_TYPES, LAST_COMM_TYPES, OB config keys
- `ob_bridge.py` — OpenBrain Supabase fetch, `[quick-fit-log]` block parser, SQLite import with dedup
- `fit_analysis_engine.py` — AI fit scoring logic, do not modify without explicit instruction
- `quick_fit_capture.py` — Streamlit-based manual capture form (standalone, not part of desktop app)
- `migrations/` — SQL migration files (001: quick_fit_log table, 002: ob_thought_id column)
- `queries/quick_fit_queries.sql` — 14 pre-built analytical queries for quick-fit data
- `docs/` — ADRs and design decisions; read relevant ADRs before proposing structural changes
- `C:\Users\jonat\OneDrive\Documents_PC\GIT_Repo_Private\ob1-extensions\extensions\job-hunt\schema.sql` — reference schema for interviews table (Nate B. Jones OB1)
