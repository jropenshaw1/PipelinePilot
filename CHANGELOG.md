# Changelog

All notable changes to PipelinePilot are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **`test_job_url.py`** -- 9 end-to-end tests for ADR-012: fresh-install migration order (010 survives 008's table rebuild), OB thought → import → promote → `opportunities.job_url` and the JD `Job URL:` line, pre-ADR entries without a URL, and the backfill (dry run writes nothing, apply fills only empty values, a manual URL is never overwritten, a missing opportunity record is skipped), plus a test proving the backup includes WAL-resident rows.
- **GitHub Actions CI** (`.github/workflows/tests.yml`) -- runs the test suite on every push and pull request (Python 3.12).
- **`database.backup_database()`** -- consistent database copy via SQLite's online backup API.
- **PipelinePilot MCP server** (`mcp_server/`) -- local stdio MCP server exposing the SQLite pipeline to Claude Desktop as a thin wrapper over `database.py`, `config.py`, and `ob_bridge.py`. Read tools: `pipi_query_pipeline`, `pipi_get_opportunity`, `pipi_get_dashboard`, `pipi_get_followups_due`, `pipi_search_opportunities`. Write tools: `pipi_update_status`, `pipi_update_followup`, `pipi_log_communication`, `pipi_update_contact`, `pipi_close_opportunity`, `pipi_archive_opportunity`, `pipi_mark_applied`, `pipi_log_still_posted`, `pipi_add_interview`. Import: `pipi_run_ob_import`. SQL statements are traced to stderr (stdout is reserved for JSON-RPC). `PIPI_MCP_DB_PATH` points the server at a disposable test database. Spec: `docs/08_MCP_Server_PRD_v1.4.md`. Setup: `mcp_server/README.md`.
- **`posting_status_log` field** (ADR-009) -- machine-maintained posting lifecycle record on `opportunities`: `STILL POSTED: YYYY-MM-DD | YYYY-MM-DD | ...` plus `NOT POSTED: YYYY-MM-DD` on ghosted closure. Written only by `pipi_log_still_posted` and `pipi_close_opportunity`.
- **Ghosted status** (ADR-009) -- first-class terminal status in `STATUS_VALUES` and `TERMINAL_STATUSES`. Excluded from follow-ups due, like the other terminal statuses.
- **Multi-select status filter** (ADR-011) -- `get_all_opportunities()` and `pipi_query_pipeline` accept a single status or a list. Desktop multi-select widget not yet built.
- **`database.next_monday()`** and **`database.initial_follow_up()`** (ADR-010) -- one function for the Monday snap, one for the first follow-up date. Every caller uses them.
- **`config.get_follow_up_offset_days()`** -- the single accessor for the follow-up offset. Reads `pipelinepilot.config` on every call, so a change saved in Settings takes effect immediately in the desktop app and in a running MCP server, with no restart. Falls back to `DEFAULT_FOLLOW_UP_OFFSET_DAYS` if the key is missing or not a whole number of at least 1.
- **`POST_APPLICATION_STATUSES`** in `models.py` -- the one list that decides when "Mark Applied" is hidden. Replaces two duplicated inline sets in `pipelinepilot.py`.
- **`test_follow_up.py`** -- 13 tests covering the offset accessor (fallbacks, live re-read), Monday snap, and `update_opportunity()` follow-up auto-set.
- **`AGENTS.md`** -- agent induction file: project shape, architecture conventions, and the governance reference for coding agents working in this repo.
- **Quick-Fit Log archive** -- manual archive system for QFL entries. Toggle button ("📦 View Archive" / "📋 View Active") in the filter bar switches between active and archived views. Per-row 📦 button archives individual entries with confirmation dialog. Decision filter works in both views. Archive button only visible in active view.
- **Auto-fill date fields on status dropdown change** -- selecting "Applied" from the status dropdown in Detail view now instantly populates date_applied (today) and follow_up_date (the Monday after today + configured offset, via `database.initial_follow_up()`) on screen, so the user can see and adjust before clicking Save. Only fires when fields are empty; respects manual entries. Existing _save() auto-fill retained as safety net.
- **Parse failure diagnostics** -- every OB import parse failure now carries the rejection reason (missing required fields, invalid `source_channel` / `role_level` / `quick_fit` / `decision`, or `decision=pass` without `primary_pass_reason`), the thought's created date, and a 300-character preview of the raw entry (newlines shown as ⏎). Previously a failure showed only the thought ID and company/role, so diagnosing it meant opening the thought in OpenBrain.
- **"Not QFL" line on the import summary** -- thoughts that mention the `[quick-fit-log]` tags in prose but contain no block (for example, Context Rescue handoffs) are listed separately with created date and first line, and are no longer counted as parse failures.

### Changed

- **Follow-up dates** (ADR-010) -- every follow-up date is a Monday. Initial follow-up = `next_monday(date_applied + offset)`. Still-posted recheck = `next_monday(today)`, replacing the hardcoded 7 days in `log_still_posted()`.
- **Default follow-up offset** changed from 30 to 14 days (`DEFAULT_FOLLOW_UP_OFFSET_DAYS`, ADR-010). Reverses the 0.4.0 change.
- **`database.update_opportunity()`** -- `follow_up_offset_days` parameter removed. The offset is resolved inside `initial_follow_up()` from live config, so no caller can pass a stale or hardcoded value.
- **`pipi_log_still_posted`** writes to `posting_status_log` instead of `action_items` (ADR-009).
- **`pipi_close_opportunity`** -- `ghosted` boolean removed. Use `status="Ghosted"`, which appends `NOT POSTED: YYYY-MM-DD` to `posting_status_log` (ADR-009). Breaking change for MCP callers that passed `ghosted=true`.
- **Fit analysis prompt caching** -- `fit_analysis_engine.py` marks the system prompt and the resume as cache breakpoints, so back-to-back JFA runs against the same resume reuse the cached prefix (about 90% lower input-token cost from the second run on, 5-minute TTL). No change to output.
- **Settings label** for the follow-up offset now states that dates snap to the next Monday.
- **OB import fetch** -- `fetch_qfl_thoughts()` now filters server-side (`content LIKE '%[/quick-fit-log]%'`) and paginates (500 per page, up to 50 pages, ordered `created_at desc, id desc`). The client-side check for both opening and closing tags is kept as a second guard. Replaces the v0.2.0 approach of fetching the newest 200 thoughts of any type and filtering client-side. Signature change: `limit` replaced by `page_size` and `max_pages`.
- **`run_import()` result** -- adds `non_qfl_skipped: list[str]`. `parse_failures` now holds only QFL blocks that failed validation.
- **_field_option helper** now accepts an optional `on_change` callback, passed through to CTkOptionMenu `command`. Backward compatible (defaults to None).
- **_refresh_qfl** now passes `show_archived` parameter to `get_quick_fit_entries()` based on archive toggle state.
- **QFL metrics** now count active entries only (`archived = 0`) for the header total, decision breakdown pills, and fit breakdown.
- **QFL row text truncation** -- company (24 chars), role (28 chars), and location (20 chars) fields truncate with ellipsis to prevent long entries from pushing action buttons off screen.
- **QFL archive performance** -- archiving a row now destroys the row widget in-place instead of triggering a full page reload. Confirmation dialog removed for faster batch archiving.
- **ob_bridge.py enum sync** -- `VALID_ROLE_LEVELS` now includes `Sr. Manager`; `VALID_SOURCE_CHANNELS` now includes `company-site`. Aligns parser validation with quick-fit skill v1.3.1 and migration 008 CHECK constraints.
- **ob_bridge.py alias normalization** -- `parse_qfl_block` now normalizes known AI-generated enum variants before validation via `PASS_REASON_ALIASES` and `ROLE_LEVEL_ALIASES` maps. Aliases like `domain-mismatch` → `wrong-domain`, `Senior Manager` → `Sr. Manager`, etc. are resolved with info-level logging. Unknown values still fail validation. Root cause: AI agents generating close-but-wrong enum values (e.g. `domain-mismatch` instead of `wrong-domain`) caused silent parse failures on OB import.
- **quick_fit_capture.py enum sync** -- `ROLE_LEVELS` now includes `Sr. Manager`; `SOURCE_CHANNELS` now includes `company-site`. Aligns Streamlit capture form with ob_bridge and migration 008 CHECK constraints.

### Database Migration

- **Migration 010** (idempotent, inline in `migrate_add_quick_fit_log`, runs after 008): adds `job_url TEXT` to `quick_fit_log` (ADR-012).
- **`migrations/backfill_job_url_from_ob.py`** (one-time, manual): re-reads `[quick-fit-log]` blocks from OpenBrain and fills empty `quick_fit_log.job_url` (matched on `ob_thought_id`) and empty `opportunities.job_url` for promoted entries (matched on `promoted_folder_name`). Never overwrites an existing URL. Dry run by default; `--apply` writes after taking a timestamped backup.
- **Migration 007** (idempotent, inline in `migrate_add_quick_fit_log`): adds `archived INTEGER NOT NULL DEFAULT 0` column to `quick_fit_log` table.
- **Migration 009** (idempotent, `migrate_add_posting_status_log`): adds `posting_status_log TEXT` to `opportunities`.
- **`migrations/migrate_action_items_to_posting_status_log.py`** (one-time, manual): relocates STILL POSTED trails and GHOSTED markers from `action_items` to `posting_status_log` and status, normalizing dates to ISO 8601. Dry run by default; `--apply` writes after taking a timestamped backup. Records that already have `posting_status_log` data are skipped.
- **Migration 008** (idempotent, inline in `migrate_add_quick_fit_log`): table rebuild adding `Sr. Manager` to `role_level` CHECK constraint and `company-site` to `source_channel` CHECK constraint. Root cause: May 2026 job search scope expansion to include Sr. Manager roles was not reflected in the schema enum, causing 8 OB import parse failures in a single QF batch session.

### Fixed

- **Migration backups could miss recent writes** -- `backfill_job_url_from_ob.py` and `migrate_action_items_to_posting_status_log.py` backed up with `shutil.copy2`, which copies only the main database file. PipelinePilot runs in WAL mode, so commits not yet checkpointed live in the `-wal` file and were absent from the backup. Both now use SQLite's backup API. Found in an external engineering review (Gee, 2026-10-06).
- **Job URL lost between quick-fit and pipeline** (ADR-012) -- the `job_url` line in every `[quick-fit-log]` block was parsed but dropped by `parse_ob_thought()`, `quick_fit_log` had no column for it, and `promote_quick_fit()` never passed it on. It is now carried from OB import through promote into `opportunities.job_url` and the `Job URL:` line of the JD file. `job_url` remains optional at import, so older entries without it still import.
- **Pursuit Tracker now includes Capturing status** -- Pursuit Tracker previously only queried Analyzing and Pursuing statuses, so newly promoted or manually captured opportunities (which enter as Capturing) were invisible. All three pre-application statuses (Capturing, Analyzing, Pursuing) are now included, matching the intended workflow: every opportunity is tracked from first entry through Applied.
- **Follow-up offset ignored by the desktop app** -- five UI paths (Mark Applied from the Pursuit Tracker, Mark Applied from Detail view, status-change auto-fill, and two in Save) computed follow-up dates themselves with a hardcoded 30-day fallback and no Monday snap. Changing the offset in Settings had no reliable effect, and desktop-set dates disagreed with MCP-set dates. All paths now call `database.initial_follow_up()`.
- **Follow-up offset change required MCP server restart** -- the server read the offset from config loaded at startup. It now reads it live through `config.get_follow_up_offset_days()`.
- **`update_opportunity()` could skip the follow-up auto-set** -- it used `setdefault`, which does nothing when the key is present with value `None` (an empty field from Detail view). Now assigns directly.
- **"Mark Applied" shown on Ghosted opportunities** -- the inline status sets predated ADR-009 and omitted Ghosted. Fixed by `POST_APPLICATION_STATUSES`.
- **Follow-ups Due view crash on malformed dates** -- a non-ISO `follow_up_date` no longer breaks the view; the row renders and the bad value is logged. Detail view Save now rejects malformed dates in `date_applied`, `follow_up_date`, `interview_date`, and `last_communication_date` with a format message.
- **`launch.bat`** now starts from its own folder (`%~dp0`) instead of a hardcoded user-profile path, so it survives profile and drive changes.
- **Personal paths and project identifiers removed from docs and code** -- example config values, local folder paths, and the OpenBrain project URL in `CHANGESET_ob_import.md`, `CLAUDE.md`, `docs/08_MCP_Server_PRD_v1.4.md`, and the "OB Not Configured" message are replaced with placeholders.
- **Older QFL entries unreachable by import** -- as OpenBrain grew past 200 thoughts, QFL entries older than the newest 200 thoughts (of any type) fell out of the fetch window and could never be imported. Fixed by the server-side filter and pagination above.
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
