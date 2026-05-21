# Changelog

All notable changes to PipelinePilot are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed

- **Pursuit Tracker now includes Capturing status** -- Pursuit Tracker previously only queried Analyzing and Pursuing statuses, so newly promoted or manually captured opportunities (which enter as Capturing) were invisible. All three pre-application statuses (Capturing, Analyzing, Pursuing) are now included, matching the intended workflow: every opportunity is tracked from first entry through Applied.
- **OB import summary diagnostics** -- import results now correctly separate duplicates (already imported entries) from parse failures (malformed content). Previously, both were reported as "parse failures" which created misleading error messages when re-importing existing quick-fit entries.

---

## [0.4.0] -- 2026-05-15

### Added

- **Pursuit Tracker view** -- new sidebar nav item showing a filtered view of opportunities in Analyzing or Pursuing status. Displays company/role, fit score, status badge, and three checklist columns (JFA, CL reviewed, resume reviewed) with a per-row Mark Applied button.
- **Follow-ups Due sidebar link** -- persistent nav link under Quick-Fit Log showing live count badge. Enabled and accent-colored when follow-ups are due; disabled and greyed when count is zero. Same query logic as the dashboard card, now always visible.
- **Pursuit Checklist in detail view** -- new section between Fit Analysis and Contact with three checkboxes: JFA completed, Cover letter reviewed, Resume reviewed. Persisted to SQLite.
- **Mark Applied one-click** -- available in both pursuit tracker rows and the detail view. Sets status to Applied, date_applied to today, follow_up_date to today plus configured offset in a single action.
- **Auto-fill date_applied** -- when status changes to Applied and date_applied is empty, auto-fills today's date (both Save and Mark Applied paths).
- **JFA completion auto-flag** -- fit_analysis_engine.py now sets `jfa_completed=1` in the SQLite update on successful analysis, removing the need for manual checkbox entry.
- **Follow-ups due database functions** -- `get_followups_due_count()` and `get_followups_due()` in database.py replace inline SQL in the UI layer.

### Changed

- **Default follow-up offset** changed from 14 to 30 days (`DEFAULT_FOLLOW_UP_OFFSET_DAYS` in models.py). Existing configs retain their saved value; update in Settings to apply.
- **Hardcoded 14-day offset** in `database.update_opportunity()` replaced with `DEFAULT_FOLLOW_UP_OFFSET_DAYS` constant.
- **Follow-ups view** refactored to use `database.get_followups_due()` instead of inline SQL.
- **Detail view navigation** -- opening a detail from the pursuit tracker returns to the pursuit tracker on close (not the opportunities list).
- **Sidebar row count** increased to accommodate two new nav items. Capture button repositioned accordingly.
- **Version** bumped to 0.4.0.

### Database Migration

- **Migration 006** (idempotent, inline in `migrate_add_quick_fit_log`): adds three columns to `opportunities` table: `cl_reviewed INTEGER NOT NULL DEFAULT 0`, `resume_reviewed INTEGER NOT NULL DEFAULT 0`, `jfa_completed INTEGER NOT NULL DEFAULT 0`.

---

## [0.3.0] -- 2026-04-06

### Added

- **Promote to Pipeline** -- QFL entries can be promoted to full pipeline opportunities via an editable PromoteWindow dialog. Company and role fields are editable with live folder name preview, duplicate warning, and pre-populated JD text from the captured opportunity artifact.
- **Sort dropdown** -- opportunity list now has a Sort selector with "Newest First" (default) and "Company Name" options. Options defined in `database.SORT_OPTIONS` dict; UI auto-populates from it. `COLLATE NOCASE` on company name sort.
- **PromoteWindow dialog** -- CTkToplevel with editable company/role fields, live folder preview, duplicate folder warning, source channel mapping, and location parser.
- **Migration 003** -- adds `promoted_folder_name` column to `quick_fit_log`.
- **Migration 004** -- drops `trg_auto_promote` trigger permanently.

### Fixed

- **Trigger bug** -- `trg_auto_promote` from migration 001 was automatically setting `promoted_to_pipeline=1` on any QFL entry with `decision=pursue` at insert time, causing the Promote button to disappear before the user clicked it. Trigger dropped permanently. Truth check changed from `promoted_to_pipeline == 1` to `promoted_folder_name IS NOT NULL`.
- **False positive reset** -- entries with `promoted_to_pipeline=1` but no `promoted_folder_name` are reset to 0 on migration.
- **Orphan detection** -- `promote_quick_fit()` handles folder-without-DB and DB-without-folder orphan states gracefully.

### Changed

- **Version** bumped to 0.3.0.
- **Promotion truth check** -- `promoted_folder_name IS NOT NULL` is the canonical test for whether a QFL entry has been promoted (not the `promoted_to_pipeline` flag).

---

## [0.2.0] -- 2026-04-06

### Added

- **Quick-Fit Log table** -- new `quick_fit_log` SQLite table for rapid JD triage, with schema-enforced enums, CHECK constraints, and auto-promotion triggers. Schema per canonical specification (OB 8c17b063). Migration: `migrations/001_create_quick_fit_log.sql`.
- **OpenBrain import** (`ob_bridge.py`) -- fetches structured `[quick-fit-log]` entries from Supabase-backed OpenBrain, parses the block format, validates against schema enums, and imports into SQLite with idempotent dedup via `ob_thought_id` unique column. Migration: `migrations/002_add_ob_thought_id.sql`.
- **Quick-Fit Log viewer** -- new "Quick-Fit Log" screen in the desktop app with color-coded fit score and decision badges, decision filter dropdown, and summary metrics bar.
- **Import from OB button** -- new "Import from OB" sidebar action with progress indicator and import results screen showing fetched/parsed/imported/skipped counts.
- **OpenBrain configuration** -- Supabase URL and service role key fields added to Settings screen, persisted in `pipelinepilot.config`.
- **Quick-fit reporting queries** (`queries/quick_fit_queries.sql`) -- 14 pre-built analytical queries for source channel quality, pass reason distribution, pursue-to-pipeline conversion, geographic mismatch rates, company watch list candidates, and weekly activity summaries. Designed to activate after ~50 entries.
- **Streamlit capture form** (`quick_fit_capture.py`) -- standalone web form for manual quick-fit entry with real-time sidebar log. Alternative to AI-based capture for direct data entry.
- **Unit tests** (`test_ob_bridge.py`) -- 16 tests covering block parsing, enum validation, field extraction, timestamp normalization, and edge cases. All passing.

### Changed

- **Version** bumped to 0.2.0.
- **`database.py`** -- `initialize_database()` now runs interviews table migration and quick-fit-log migrations (001 + 002) idempotently on startup.
- **`config.py`** -- added `ob_supabase_url` and `ob_supabase_key` to config defaults.
- **`models.py`** -- added `OB_SUPABASE_URL_KEY` and `OB_SUPABASE_KEY_KEY` constants.
- **`requirements.txt`** -- added `requests>=2.31.0` for Supabase REST API access.
- **`pipelinepilot.py`** -- added `ob_bridge` import, Quick-Fit Log nav item, Import from OB nav item, OB config fields in Settings, and associated view/handler methods.
- **README.md** -- updated with Quick-Fit Log and OpenBrain integration documentation, corrected status to v0.2.0.
- **Stack description** -- added `requests` to architecture overview.

### Architecture Decisions

- **AI as capture interface** -- quick-fit triage happens conversationally through AI agents (Claude, ChatGPT). The AI produces schema-compliant structured blocks written to OpenBrain. PipelinePilot imports from OB. No manual form entry required for the primary workflow.
- **Client-side filtering** -- OB import fetches recent thoughts via Supabase REST API and filters client-side for `[quick-fit-log]` content markers, avoiding dependency on OB's internal metadata schema.
- **Dedup via `ob_thought_id`** -- each OpenBrain thought is imported at most once, tracked by unique UUID column with index. Repeated imports are safe and idempotent.

---

## [0.1.0] -- 2026-03-08

### Added

- Initial release: CustomTkinter desktop application with dashboard, opportunity list, detail view, settings, and capture dialog.
- SQLite database layer with filesystem-first architecture.
- Fit analysis engine integration with Anthropic Claude API.
- Interviews table and migration.
- Rebuild index from filesystem.
- Full documentation set (7 documents, pre-implementation).
