# Changelog

All notable changes to PipelinePilot are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] — 2026-04-06

### Added

- **Quick-Fit Log table** — new `quick_fit_log` SQLite table for rapid JD triage, with schema-enforced enums, CHECK constraints, and auto-promotion triggers. Schema per canonical specification (OB 8c17b063). Migration: `migrations/001_create_quick_fit_log.sql`.
- **OpenBrain import** (`ob_bridge.py`) — fetches structured `[quick-fit-log]` entries from Supabase-backed OpenBrain, parses the block format, validates against schema enums, and imports into SQLite with idempotent dedup via `ob_thought_id` unique column. Migration: `migrations/002_add_ob_thought_id.sql`.
- **Quick-Fit Log viewer** — new "⚡ Quick-Fit Log" screen in the desktop app with color-coded fit score and decision badges, decision filter dropdown, and summary metrics bar.
- **Import from OB button** — new "📥 Import from OB" sidebar action with progress indicator and import results screen showing fetched/parsed/imported/skipped counts.
- **OpenBrain configuration** — Supabase URL and service role key fields added to Settings screen, persisted in `pipelinepilot.config`.
- **Quick-fit reporting queries** (`queries/quick_fit_queries.sql`) — 14 pre-built analytical queries for source channel quality, pass reason distribution, pursue-to-pipeline conversion, geographic mismatch rates, company watch list candidates, and weekly activity summaries. Designed to activate after ~50 entries.
- **Streamlit capture form** (`quick_fit_capture.py`) — standalone web form for manual quick-fit entry with real-time sidebar log. Alternative to AI-based capture for direct data entry.
- **Unit tests** (`test_ob_bridge.py`) — 16 tests covering block parsing, enum validation, field extraction, timestamp normalization, and edge cases. All passing.

### Changed

- **Version** bumped to 0.2.0.
- **`database.py`** — `initialize_database()` now runs interviews table migration and quick-fit-log migrations (001 + 002) idempotently on startup.
- **`config.py`** — added `ob_supabase_url` and `ob_supabase_key` to config defaults.
- **`models.py`** — added `OB_SUPABASE_URL_KEY` and `OB_SUPABASE_KEY_KEY` constants.
- **`requirements.txt`** — added `requests>=2.31.0` for Supabase REST API access.
- **`pipelinepilot.py`** — added `ob_bridge` import, Quick-Fit Log nav item, Import from OB nav item, OB config fields in Settings, and associated view/handler methods.
- **README.md** — updated with Quick-Fit Log and OpenBrain integration documentation, corrected status to v0.2.0.
- **Stack description** — added `requests` to architecture overview.

### Architecture Decisions

- **AI as capture interface** — quick-fit triage happens conversationally through AI agents (Claude, ChatGPT). The AI produces schema-compliant structured blocks written to OpenBrain. PipelinePilot imports from OB. No manual form entry required for the primary workflow.
- **Client-side filtering** — OB import fetches recent thoughts via Supabase REST API and filters client-side for `[quick-fit-log]` content markers, avoiding dependency on OB's internal metadata schema.
- **Dedup via `ob_thought_id`** — each OpenBrain thought is imported at most once, tracked by unique UUID column with index. Repeated imports are safe and idempotent.

---

## [0.1.0] — 2026-03-08

### Added

- Initial release: CustomTkinter desktop application with dashboard, opportunity list, detail view, settings, and capture dialog.
- SQLite database layer with filesystem-first architecture.
- Fit analysis engine integration with Anthropic Claude API.
- Interviews table and migration.
- Rebuild index from filesystem.
- Full documentation set (7 documents, pre-implementation).
