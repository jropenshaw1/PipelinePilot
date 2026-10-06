# PipelinePilot — Architecture Decision Records (ADRs)

**Version:** 1.2
**Date:** October 6, 2026
**Author:** Jonathan Openshaw
**Standard:** Michael Nygard ADR Format
**Status:** Approved

**Change Log:**
- **v1.0** (March 7–12, 2026) — ADR-001 through ADR-008
- **v1.1** (August 7, 2026) — ADR-009 (Posting Status Log, Action Items Scope, Ghosted Status), ADR-010 (Follow-Up Date Standardization), ADR-011 (Multi-Select Status Filtering)
- **v1.2** (October 6, 2026) — ADR-012 (Carry job_url Through OB Import and Promote)

---

## ADR-001: Filesystem as Source of Truth

**Date:** March 7, 2026
**Status:** Accepted

### Context
PipelinePilot requires both structured data (status, dates, scores) and unstructured artifacts (Word documents, markdown files). Two storage approaches were considered: database-primary (SQLite owns the record) or filesystem-primary (OneDrive folders own the record).

### Decision
The OneDrive filesystem is the source of truth. SQLite is a derived, rebuildable index.

### Rationale
- Files stored on OneDrive are automatically backed up and recoverable
- If the database is lost, it can be rebuilt from the filesystem via `rebuild-index`
- If files are lost, no database can recover them
- The most irreplaceable artifacts (tailored resume, cover letter) are files, not database rows
- When asked "which would you grieve more losing — the database or the files?" the answer was unambiguously the files
- This pattern is used in many AI-native internal tools: filesystem = truth, database = index

### Consequences
- Folder naming convention becomes critical — it is the primary key across both systems
- A folder renamed manually outside PipelinePilot breaks the primary key link
- A `rebuild-index` command is a required feature, not optional
- PipelinePilot must handle gracefully any state where filesystem and database are out of sync

---

## ADR-002: UI Framework — Python + CustomTkinter

**Date:** March 7, 2026
**Status:** Accepted

### Context
The existing tool used Streamlit, which required a background server process, a browser tab as the UI, manual shortcut creation, and icon hunting. This felt like a workaround, not an application.

Alternatives considered:
- **Streamlit** — rejected (background server process, no native Windows integration)
- **Electron** — rejected (overkill, heavy, fails KISS test)
- **React/web** — rejected (overkill, fails KISS test, requires web server)
- **Tkinter (standard)** — considered (too dated visually)
- **CustomTkinter** — selected
- **PyQt6** — considered (more powerful but more complex; fails relative KISS test)

### Decision
Python + CustomTkinter for the GUI layer.

### Rationale
- Launches as a native Windows desktop application — no background process, no browser
- Modern visual appearance compared to standard Tkinter
- Ships as a standard Python package via pip — no system dependencies
- Consistent with Python as the chosen language
- Low learning curve for future contributors
- Passes the KISS test: solves the problem without introducing unnecessary complexity

### Consequences
- Application limited to desktop (no web, no mobile) — acceptable per scope
- CustomTkinter is a third-party dependency — must be pinned in requirements.txt
- UI will not match native Windows 11 design language exactly — acceptable tradeoff

---

## ADR-003: SQLite as the Structured Data Index

**Date:** March 7, 2026
**Status:** Accepted

### Context
Structured data (status, dates, fit scores, contacts) needs a queryable store to support list views, filtering, sorting, and dashboard metrics.

Alternatives considered:
- **JSON files per opportunity** — rejected (no query capability, complex to filter/sort)
- **PostgreSQL / cloud database** — rejected (overkill, requires server, fails KISS test)
- **Supabase (OpenBrain pattern)** — rejected (external dependency, internet required, overkill for single user)
- **SQLite** — selected

### Decision
SQLite via Python's standard library `sqlite3` module.

### Rationale
- Zero server infrastructure — single file on local disk
- Automatically backed up alongside OneDrive documents
- Standard library — no additional dependency
- Sufficient for single-user, up to 500 records, local queries
- Disposable and rebuildable from filesystem (see ADR-001)
- Industry-standard choice for embedded single-user applications

### Consequences
- No concurrent write access — acceptable for single-user tool
- Database file must be stored in a known, configurable location
- All queries must be designed to degrade gracefully if database is absent

---

## ADR-004: Dual Artifact Output from Job Fit Analyst (.docx + .md)

**Date:** March 7, 2026
**Status:** Accepted

### Context
The Job Fit Analyst skill currently outputs `.docx` files. PipelinePilot requires machine-parseable structured metadata to populate the SQLite index. Three approaches were evaluated:
1. Parse the existing `.docx` narrative — brittle, fragile
2. Change Job Fit Analyst to output `.md` only — loses rich document formatting
3. Output both `.docx` and `.md` from a single analyst run — dual artifact pattern

### Decision
Job Fit Analyst shall output two fit analysis artifacts per run:
- `fit_analysis.docx` — human-readable, rich formatting, for review and recruiter demos
- `fit_analysis.md` — markdown with YAML front-matter, for PipelinePilot indexing

### Rationale
- `.docx` preserves the full Advocate/Auditor narrative in a professional format readable by anyone
- `.md` with YAML front-matter is trivial to parse reliably — no brittle prose parsing
- PipelinePilot parses only the YAML header — the narrative body is untouched by the indexer
- One analyst run produces both artifacts — no extra User effort
- Separation of concerns: human interface (.docx) vs. machine interface (.md)
- GitHub renders `.md` files natively — excellent for showcase and demo

### Consequences
- Job Fit Analyst skill requires a code change to output both file types
- YAML front-matter schema must be maintained as a documented contract between the two systems
- `analysis_version` field in the YAML enables future model/version tracking
- PipelinePilot integration module must be updated if the YAML schema changes

---

## ADR-005: No Automated Email Processing

**Date:** March 7, 2026
**Status:** Accepted

### Context
Automating email capture (confirmation emails, employer communications) via Gmail API or IMAP integration was considered to reduce manual effort.

### Decision
No automated email processing. Email content is captured manually via paste-into-text-area.

### Rationale
- Gmail API integration introduces OAuth complexity, token management, and an external dependency
- The value gained (saving ~30 seconds of paste effort) does not justify the complexity introduced
- KISS: the User copies and pastes — this is a 10-second operation that requires no infrastructure
- Reduces attack surface and eliminates credential management concerns
- Consistent with the principle: every dependency must justify its inclusion

### Consequences
- User must manually paste confirmation email text into PipelinePilot
- No automatic detection of new employer communications
- Future enhancement path exists if User finds manual capture too burdensome

**Note (August 7, 2026):** The follow-up maintenance skill (Layer 3) uses Gmail MCP to *search* for employer communications during maintenance sessions and surface them for user review. This is consistent with ADR-005 — the skill reads Gmail as a signal source during an interactive session; it does not automatically process, capture, or act on emails without user direction.

---

## ADR-006: Reference and Index, Not Reinterpret

**Date:** March 7, 2026
**Status:** Superseded by ADR-008

### Context
When integrating with Job Fit Analyst output, two approaches were considered:
1. PipelinePilot generates its own fit summary by re-calling an AI model
2. PipelinePilot indexes the existing Job Fit Analyst artifact without generating new AI content

### Decision
PipelinePilot shall never generate its own AI reasoning content. It shall only index what Job Fit Analyst produces.

### Rationale
- Two AI reasoning artifacts for the same role creates drift — they may disagree
- Job Fit Analyst already produces high-quality Advocate/Auditor analysis — reinterpreting it adds no value
- The fit document doubles as an explainability and audit artifact — a second artifact undermines this
- Clean boundary between systems: Job Fit Analyst owns reasoning; PipelinePilot owns lifecycle tracking
- For enterprise AI governance audiences: one traceable artifact per decision is stronger than two competing ones

### Consequences
- PipelinePilot has no AI API dependency — it is a pure management tool
- All AI quality improvements flow through the Job Fit Analyst skill, not PipelinePilot
- `fit_analysis.md` is the single explainability record for every opportunity

*Superseded by ADR-008, March 12, 2026. The core principle (one authoritative AI artifact per role) remains in force. The constraint (no AI in PipelinePilot) is lifted.*

---

## ADR-007: Deterministic, Idempotent Rebuild Index

**Date:** March 7, 2026
**Status:** Accepted

### Context
Given that the filesystem is the source of truth and the database is derived, a recovery mechanism is required. The design of this mechanism is a deliberate architectural signal.

### Decision
`pipelinepilot rebuild-index` shall be deterministic and idempotent. It shall use UPSERT operations (INSERT OR REPLACE) so it can be run any number of times with identical results.

### Rationale
- Idempotency is a hallmark of resilient, production-grade system design
- A deterministic rebuild means the system is always recoverable from first principles
- UPSERT pattern eliminates the need for "was this already indexed?" bookkeeping
- Senior engineers and CTOs recognize idempotent rebuild as a maturity signal
- Supports development, testing, and production recovery with the same command

### Consequences
- All INSERT operations in the rebuild path must use INSERT OR REPLACE, not INSERT
- Rebuild must be tested against: empty database, partially populated database, fully populated database — all must produce identical results
- Summary report (scanned / indexed / warnings / failures) is required output for observability

---

## ADR-008: Embedded Fit Analysis Engine (Supersedes ADR-006)

**Date:** March 12, 2026
**Status:** Accepted

### Context

ADR-006 established that PipelinePilot would never generate its own AI reasoning content. The original design called for fit analysis to be produced exclusively by the Job Fit Analyst Claude skill, invoked externally, with PipelinePilot only indexing the resulting filesystem artifacts.

This decision rested on two assumptions:

1. Clean separation of concerns required a hard boundary — Job Fit Analyst owns reasoning, PipelinePilot owns lifecycle management
2. PipelinePilot was intended for free distribution as a standalone tool with no dependency on Job Fit Analyst, minimizing setup friction for end users

After several days of production use, reality challenged both assumptions. The external invocation model created real friction: switching to Claude.ai to run Job Fit Analyst and then returning to PipelinePilot interrupted the job search workflow at exactly the wrong moment. The tool was demonstrably more useful than anticipated. Optimizing for that usefulness outweighed the original simplicity goal.

Critically: both PipelinePilot and Job Fit Analyst are independently developed, freely distributed, open-source projects by the same author. The dependency is not proprietary. End users who want integrated fit analysis are asked to clone two public repos and configure one API key — a real but manageable cost.

### Decision

Embed `fit_analysis_engine.py` directly into PipelinePilot as a first-class integrated module. Fit analysis is initiated from within the PipelinePilot UI in a single action, requiring only a locally configured Anthropic API key.

The core architectural principle from ADR-006 is preserved: one authoritative AI reasoning artifact per role, no competing or duplicate analysis. The constraint it imposed (no AI API calls inside PipelinePilot) is lifted.

### Rationale

- Production use demonstrated the tool was valuable enough to optimize. Friction removed is value delivered.
- Both components are freely distributed — the dependency is transparent and the cost to end users is documented explicitly
- `fit_analysis_engine.py` is a distinct, isolated module with a documented interface. The boundary is maintained even though the invocation mechanism changed.
- The principle that matters (one authoritative artifact per role, no drift between competing reasoning sources) is fully preserved
- The original free-distribution intent is unchanged — installation now requires both repos and an API key, clearly documented in the README

### Consequences

- End users who want integrated fit analysis must: clone both repositories, install dependencies for both, and configure a valid Anthropic API key locally
- Users who want PipelinePilot as a standalone lifecycle tracker without AI analysis can still use it that way — fit analysis is an optional feature, not a requirement
- `requirements.txt` must include the `anthropic` library
- ADR-006 is superseded. The principle it protected remains. The constraint it imposed is lifted.
- Future changes to fit analysis logic require changes only in `fit_analysis_engine.py` — the module boundary is documented and maintained

---

## ADR-009: Posting Status Log, Action Items Scope Correction, and Ghosted Status

**Date:** August 7, 2026
**Status:** Accepted
**Supersedes:** Portions of PRD v1.3 §7.1 (action_items append behavior)

### Context

The `action_items` field was defined in Data Dictionary v1.0 §5.5 as: *"Free-text per-role task list: research, training, prep."* In practice, the field accumulated five distinct categories of data:

1. **STILL POSTED date trails** — posting verification timestamps (15+ records)
2. **GHOSTED markers** — terminal status indicators with dates (20+ records)
3. **Communication history** — LinkedIn messages, email exchanges (10+ records, duplicating `communication_notes`)
4. **One-time observations** — "Degree required", "Application lost in shuffle" (10+ records)
5. **Pending tasks** — the only content matching the Data Dictionary definition (3 records)

Analysis of all 62 populated `action_items` records across 197 opportunities confirmed that Category 5 (actual action items) represented less than 5% of the field's content. The scope creep was formalized in PRD v1.3 §7.1, which codified `pipi_log_still_posted` and `pipi_close_opportunity` (ghosted=true) appending structured data to `action_items` because no dedicated field existed at build time.

Separately, "Ghosted" was tracked as a text marker (`"GHOSTED: YYYY-MM-DD"`) appended to a free-text field rather than as a first-class lifecycle status. This required text parsing to identify ghosted opportunities, prevented dashboard reporting by closure reason, and created a dependency between status determination and free-text field content.

### Decision

**1. Add `posting_status_log` field.** A new TEXT column in the `opportunities` table. Machine-maintained — written exclusively by `pipi_log_still_posted` and `pipi_close_opportunity`. Not a free-text field for human notes. Format: `STILL POSTED: YYYY-MM-DD | YYYY-MM-DD | ...` on one line, `NOT POSTED: YYYY-MM-DD` on a separate line when posting disappearance is confirmed. All dates ISO 8601.

**2. Restore `action_items` to its Data Dictionary definition.** Pending human tasks only. STILL POSTED dates, GHOSTED markers, communication history, and one-time observations do not belong here.

**3. Add "Ghosted" as a first-class terminal status.** `STATUS_VALUES` gains "Ghosted". `TERMINAL_STATUSES` gains "Ghosted" alongside Passed, Offer, Closed, and Rejected. The `ghosted` boolean parameter on `pipi_close_opportunity` is removed — the full interface is `pipi_close_opportunity(folder_name, status="Ghosted")`.

### Rationale

- Single-purpose fields are queryable, parseable, and governable. A junk-drawer field requires text parsing and heuristics to extract meaning.
- The follow-up maintenance skill (Layer 3) is the primary consumer of posting status data. Building it against a mixed-content free-text field would inherit the mess.
- Ghosted is a distinct closure reason with different implications than Rejected or Closed. Dashboard metrics can now report these as distinct categories without text parsing.
- `pipi_close_opportunity` simplifies: one parameter removed, one code path eliminated.

### Consequences

- Migration required: STILL POSTED dates and GHOSTED markers in existing `action_items` records must be relocated to `posting_status_log` and status field respectively. All dates normalized to ISO 8601.
- `pipi_log_still_posted` in `tools.py` writes to `posting_status_log` instead of `action_items`.
- `pipi_close_opportunity` in `tools.py` drops the `ghosted` boolean parameter. When `status="Ghosted"`, appends `NOT POSTED: YYYY-MM-DD` to `posting_status_log`.
- PRD v1.3 §7.1 is superseded by PRD v1.4.
- Data Dictionary v1.0 §5.5 is superseded by Data Dictionary v1.1.
- Quick-fit status-update path must recognize "Ghosted" as a valid terminal status.
- Future analytics enabled: time from application to ghost, posting duration, ghost rate by company/industry.

---

## ADR-010: Follow-Up Date Standardization — Config-Driven Offset with Monday Snap

**Date:** August 7, 2026
**Status:** Accepted
**Resolves:** PRD v1.3 §7.3 Known Inconsistency

### Context

Follow-up date calculation had three inconsistencies documented across the codebase:

| Source | Stated Offset | Actually Used |
|---|---|---|
| Data Dictionary v1.0 §5.5 | 14 days | No — documentation only |
| Process Flow v1.0, Stage 4 | 14 days | No — documentation only |
| Definition of Done v1.0 §2 | 14 days (default) | No — documentation only |
| `models.py` constant | 30 days | Yes — imported directly by `database.py` |
| `config.py` / `pipelinepilot.config` | 30 days | No — config key exists but `database.py` imports the constant instead |
| `tools.py` `log_still_posted()` | 7 days | Yes — hardcoded `timedelta(days=7)` |

Three different numbers in play (14, 30, 7), two hardcoded, and the one configurable path never read by the code that sets follow-up dates.

Separately, follow-up dates could land on any day of the week. In practice, the user runs follow-up maintenance as a dedicated Monday session. Mid-week follow-up dates created interruptions during pipeline-building work and uneven batch accumulation.

### Decision

**1. Config-driven initial offset, default 14 days.** `database.py` reads `follow_up_offset_days` from config. `models.py` constant updated from 30 to 14 as fallback default.

**2. All follow-up dates snap to next Monday.** A single utility function, `next_monday(reference_date)`, returns the next Monday strictly after the given date. Both paths use it: initial follow-up = `next_monday(date_applied + offset_days)`, still-posted recheck = `next_monday(today)`.

**3. `log_still_posted` hardcoded 7-day interval removed.** Replaced by `next_monday(today)`.

### Rationale

- One lever, one source. The config value is authoritative. The constant is the fallback.
- Monday maintenance is a workflow decision. Most employer rejections arrive Friday afternoons and weekends. Monday morning maintenance reviews the full week's signals in one session.
- Predictable batching. Every follow-up date is a Monday. No mid-week stragglers.

### `next_monday()` Specification

```python
def next_monday(reference_date: date) -> date:
    """Return the next Monday strictly after reference_date.

    If reference_date is a Monday, returns the following Monday (7 days later),
    not the same day — prevents setting a follow-up for today and immediately
    surfacing it as due.
    """
    days_ahead = 7 - reference_date.weekday()  # weekday(): Mon=0, Sun=6
    if days_ahead == 7:  # reference_date is already Monday
        days_ahead = 7   # snap to next Monday, not today
    return reference_date + timedelta(days=days_ahead)
```

### Consequences

- `models.py`: `DEFAULT_FOLLOW_UP_OFFSET_DAYS` changes from 30 to 14.
- `database.py`: `update_opportunity()` reads offset from config. `next_monday()` added as module-level utility.
- `tools.py`: `log_still_posted()` calls `next_monday(today)` instead of `today + timedelta(days=7)`.
- `pipelinepilot.config`: `follow_up_offset_days` value updated from 30 to 14.
- Existing follow-up dates are not retroactively migrated — they snap to Mondays as each opportunity is processed in the next maintenance session.

---

## ADR-011: Multi-Select Status Filtering

**Date:** August 7, 2026
**Status:** Accepted

### Context

`get_all_opportunities()` in `database.py` and `pipi_query_pipeline` in the MCP server accept a single `status_filter` string. Common workflow patterns require viewing multiple statuses simultaneously — for example, all active opportunities (Applied + In Review + Interviewing), or all terminal outcomes (Closed + Rejected + Ghosted + Passed).

### Decision

`status_filter` accepts a list of status strings. The SQL query builds a `WHERE status IN (?, ?, ...)` clause. Backward compatibility preserved: a single string is accepted and wrapped in a list internally.

### Rationale

- Multi-status views are the natural query pattern for pipeline review.
- The addition of "Ghosted" (ADR-009) makes this more pressing — terminal statuses now include five values.
- Backward compatibility means no existing code breaks.

### Consequences

- `database.py`: `get_all_opportunities()` parameter `status_filter: str | list[str] | None`. Each value validated against `STATUS_VALUES`.
- `tools.py`: `query_pipeline()` validates and accepts list for status filter.
- Desktop UI: Multi-select widget replaces single-select dropdown (lower priority).
- MCP tool schema: `status_filter` type changes from `string | null` to `string | array[string] | null`.

---

## ADR-012: Carry job_url Through OB Import and Promote

**Date:** October 6, 2026
**Status:** Accepted

### Context

The quick-fit skill requires `job_url` on every `[quick-fit-log]` block, and the data dictionary (v1.1) makes `job_url` required at capture. In practice the URL never reached a promoted opportunity. It was lost at three points:

1. `ob_bridge.parse_ob_thought()` parsed every `key: value` line, but built the SQLite record from a fixed field list that did not include `job_url`.
2. The `quick_fit_log` table had no `job_url` column, so there was nowhere to store it.
3. `database.promote_quick_fit()` built the opportunity record and JD file without a URL, so the Job URL field on every promoted opportunity started empty.

The URL had to be re-pasted by hand, usually at application time.

### Decision

Store `job_url` on `quick_fit_log` (migration 010) and carry it end to end: OB block → `parse_ob_thought()` → `quick_fit_log.job_url` → `promote_quick_fit()` → `opportunities.job_url` and the `Job URL:` line of the JD file.

- `job_url` stays **optional at import**. Entries written before the capture rule still import; a missing URL is not a parse failure.
- Migration 010 runs **after** migration 008 in `migrate_add_quick_fit_log()`. Migration 008 rebuilds the table from an explicit column list and would drop `job_url` on a fresh install if the column were added first.
- A one-time script, `migrations/backfill_job_url_from_ob.py`, fills `job_url` for entries imported before this fix by re-reading their OB blocks (matched on `ob_thought_id`) and, for promoted entries, the linked opportunity (matched on `promoted_folder_name`). **Existing values are never overwritten.** A URL already in PipelinePilot was most likely pasted by hand at application time and is treated as authoritative. Dry run by default; `--apply` takes a timestamped backup first.

### Alternatives Considered

- **Re-read OB at promote time instead of storing the URL.** Rejected: promote would depend on OpenBrain being reachable and on the thought still existing, and `quick_fit_log` rows would remain incomplete for queries and review.
- **Make `job_url` required at import.** Rejected: every pre-rule entry would become a parse failure on re-import, and recruiter-sourced roles with no public posting would fail. Enforcement stays at capture.
- **Backfill that overwrites existing URLs with the OB value.** Rejected: manual entries made at application time are newer and more accurate than the capture-time URL.

### Consequences

- `quick_fit_log` gains `job_url TEXT` (additive, nullable). `opportunities` schema is unchanged.
- `filesystem.create_opportunity_folder_with_jd()` and `_create_blank_jd()` accept an optional `job_url`.
- New tests in `test_ob_bridge.py` cover a block with and without `job_url`.
- Promoted opportunities open with the posting URL already filled in.

---

*ADRs 001–007 produced from a structured requirements interview and cross-platform AI design session (Claude + ChatGPT) conducted March 7, 2026.*
*ADR-008 added March 12, 2026, following several days of production use.*
*ADRs 009–011 added August 7, 2026, driven by follow-up maintenance skill design work and data analysis of all 197 pipeline records.*
*ADR-012 added October 6, 2026, after tracing why job URLs captured at quick-fit never reached promoted opportunities.*
