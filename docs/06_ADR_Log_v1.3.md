# PipelinePilot — Architecture Decision Records (ADRs)

**Version:** 1.3
**Date:** October 12, 2026
**Author:** Jonathan Openshaw
**Standard:** Michael Nygard ADR Format
**Status:** Approved

**Change Log:**
- **v1.0** (March 7–12, 2026) — ADR-001 through ADR-008
- **v1.1** (August 7, 2026) — ADR-009 (Posting Status Log, Action Items Scope, Ghosted Status), ADR-010 (Follow-Up Date Standardization), ADR-011 (Multi-Select Status Filtering)
- **v1.2** (October 6, 2026) — ADR-012 (Carry job_url Through OB Import and Promote)
- **v1.3** (October 12, 2026) — ADR-013 (Credentials by Vault Reference — No Secrets in pipelinepilot.config)

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

## ADR-013: Credentials by Vault Reference — No Secrets in pipelinepilot.config

**Date:** October 12, 2026
**Status:** Accepted (Jonathan Openshaw, October 12, 2026). Implementation pending: Phases 0–4 below.
**Relates to:** security review finding — live API keys stored in plain text in `pipelinepilot.config`; related fixes: Settings labels that called the OpenBrain key a "service_role JWT", and OB import returning an empty list on an authentication failure.

### Context

PipelinePilot holds two live secrets in plain text in `pipelinepilot.config`:

- `ob_supabase_key` — the per-consumer Supabase secret key used to read quick-fit entries from OpenBrain. Full read/write at the database, although PipelinePilot only reads.
- `anthropic_api_key` — used by the embedded fit analysis engine (JFA).

They are read in four places: the OB import in the desktop app (`pipelinepilot.py`), the MCP server's `run_ob_import` (`mcp_server/tools.py`, from config loaded at server start), the JFA launch check (`pipelinepilot.py`), and `fit_analysis_engine._get_api_key()`, which also falls back to a `ClaudeAPIkey.txt` file in the job search root. Settings shows both values in editable fields.

Both keys already live in a Dashlane "agent vault": a separate Dashlane account that holds only agent and API credentials. A post-hoc security review rated the plaintext config copies as a must-fix finding. Jonathan decided: PipelinePilot fetches both keys from the vault at runtime through `dcli`; programs and agents may call `dcli`, but values are never printed or echoed; OneDrive (including version history) counts as protected storage, so no rotation is required after the migration.

**Operational constraints set by Jonathan.** PipelinePilot runs the active job search, so the change must carry no risk of downtime or data corruption, with a tested backup and backout plan before the working copy is touched. When the vault needs re-authentication, Jonathan must be prompted to enter the master password. He must be able to see when the keys are retrieved.

**Observed `dcli` behavior (Windows, 2026-10-12).** Lexi's fact-check (2026-10-12) found **no official documentation** for `dcli status` output, or for `dcli read` behavior when locked or missing, or its exit codes; `dcli read` console output already changed in v6.2447.0. Everything below is observed on the installed version only. **Tested dcli version: ________ (record with `dcli --version` at Phase 1 start).** After any dcli upgrade, rerun the state-table tests before the next OB import or JFA run. Dashlane documents that `dcli` saves the master password in the OS keychain by default; `dcli lock` locks it until the master password is entered again. Documentation does not state session length, idle auto-lock, or forced re-login intervals. Tested on Jonathan's machine:
- `dcli status` never prompts. Unlocked: `Logged in: Yes`, `Login: <account>`, `Locked: No`. Locked: same with `Locked: Yes`. Logged out: `Logged in: No` (no `Locked` line).
- Locked: `dcli read …` and `dcli sync` prompt `Please enter your master password:` in the terminal; afterwards reads succeed without prompting.
- Logged out: `dcli sync` runs the full login in the terminal — account email → a dashlane.com device-registration URL printed in the terminal → token pasted from that page → email/authenticator one-time code → master password. A wrong master password discards the whole login (observed, not documented; harmless because Retry always re-checks status).

**Security model, stated plainly.** While the agent vault is unlocked, any process running as Jonathan's Windows user can read it. The Windows sign-in is the effective lock. The separate agent-only account limits what such access can reach. "Never stored" below means no application-controlled persistence; the value necessarily exists briefly in process memory while a request is made.

### Decision

**1. One credential module.** New `vault.py` is the only code that touches a credential value outside the HTTP request that uses it. `get_secret(item, caller)` runs `dcli status` (no shell, `stdin` closed, stdout/stderr captured, 10-second timeout), parses it, and evaluates these rows **in order; the first match wins**. Anything not matched fails closed.

| # | `dcli status` result | Action |
|---|---|---|
| 1 | `dcli` not found | `VaultError("dcli-missing")` |
| 2 | Non-zero exit, timeout, unparseable output, or any field appearing twice with different values | No read. `VaultError("status-unrecognized")` |
| 3 | `Logged in: No` (`Locked` and `Login` not required; ignored if present) | Open unlock window (§2); `VaultError("not-logged-in")` |
| 4 | `Logged in: Yes` but `Locked` or `Login` missing | No read. `VaultError("status-unrecognized")` |
| 5 | `Logged in: Yes`, `Login` does **not** match the configured account (locked **or** unlocked) | No read, no window. `VaultError("wrong-account")`: "dcli is logged in to a different Dashlane account. Run `dcli logout`, then Retry to log in to the agent vault." Wrong account wins over locked so the window never unlocks the wrong vault. |
| 6 | `Logged in: Yes`, `Login` matches, `Locked: Yes` | Open unlock window (§2); `VaultError("locked")` |
| 7 | `Logged in: Yes`, `Login` matches, `Locked: No` | Append `attempt`; `dcli read`; append `retrieved`; return value |

Parsing: field names and Yes/No values compared case-insensitively after trimming; `Login` compared to the configured account email after trimming and lower-casing.

**Read by item ID, not title.** Dashlane documents that `dl://<title>` returns the *first* item with that title, so a duplicate or renamed item could silently hand over the wrong key. Config therefore stores the Dashlane **item ID** for each key, and reads use `dcli read dl://<item-id>/password` (ID lookup is also faster). Test vault access shows each item's title (`dl://<item-id>/title`) for confirmation, never the secret.

**Clean environment for dcli.** `vault.py` runs every `dcli` command with `DASHLANE_SERVICE_DEVICE_KEYS` and `DASHLANE_ENROLLED_TEAM_DEVICE_KEYS` removed from the child environment, so a stray variable cannot switch dcli to a different account or device mode.

**Version on record.** The first `get_secret` call in each process runs `dcli --version` and logs it (event `dcli-version`, version string only), so an upgrade is visible in the access log next to any change in behavior.

**Account binding.** New non-secret config setting `agent_vault_account` (the agent account's email). It is required: if empty, `get_secret` raises `VaultError("not-configured")` without calling `dcli read`. It is also printed in the unlock window header.

**Retry never trusts the window.** PipelinePilot never treats the unlock window's exit code as proof of authentication. Retry (desktop dialog) or a repeated MCP call reruns `get_secret` from the top, starting with `dcli status`. A cancelled window, a failed sync, or a wrong master password therefore simply shows up as the same state on the next status check.

**2. One unlock window for both states.** When the vault is locked or logged out, PipelinePilot opens a visible console window titled *Unlock agent vault* running a small helper, `unlock_window.py`. The helper sets its console title to *Unlock agent vault* itself, then prints a header — the agent account email to use, and the login steps in order (email → open the printed dashlane.com link → paste the token → one-time code → master password; locked vaults ask for the master password only) — then runs `dcli sync` attached to that console. **If `dcli sync` exits 0, the helper exits and the window closes by itself.** If it exits non-zero, the helper prints "Login did not complete — press Enter to close this window, then click Retry in PipelinePilot" and waits for Enter. The helper never captures `dcli` output and never reads a credential. The master password, token and one-time code are typed into `dcli` only; no PipelinePilot code sees them. No custom form.

The desktop app shows: "Complete the steps in the Unlock agent vault window, then click Retry." MCP callers receive the same text as a tool error and relay it. **No window storms:** within one process, `vault.py` keeps the handle of the helper it launched. While that helper is still running, Retry launches no second window and raises "The Unlock agent vault window is still open. Finish there, or press Enter to close it, then Retry." Because a successful helper exits on its own, an old window can never block the unlock window for a later relock. (Separate processes — the desktop app and the MCP server — could each open one; accepted.) If the window cannot be launched, the error says so and tells Jonathan to run `dcli sync` in a terminal.

**3. Values are never printed or stored.** `get_secret()` captures `dcli read` stdout/stderr (never inherits the console), never logs them, never formats the process object or raw output into any message, and raises `VaultError` with `from None` so no captured output travels in a chained exception. Errors name the item and a fixed failure class only. The value is never written to disk, environment variables or the config file, and is not cached across operations. Each OB import (desktop or MCP) and each JFA run calls `get_secret` once and passes the value straight to the request client. **Test vault access** discards returned values. HTTP/SDK debug logging (`httpx`, `anthropic`, `supabase`) stays at WARNING or above so request headers are never logged.

**4. Vault access log — the record is a precondition.** In `logs/` in the PipelinePilot folder (gitignored), one file per process so the desktop app and the MCP server never write to the same file: `vault_access_desktop.log` and `vault_access_mcp.log` (Windows gives no cross-process atomic-append guarantee; separate files remove the question without locking code). One line per event, written with a single write and flushed: ISO timestamp, item name, caller, event. Never a value.
- Callers (fixed list): `desktop-ob-import`, `desktop-jfa`, `mcp-ob-import`, `settings-test`.
- Events (fixed list): `dcli-version`, `attempt`, `retrieved`, `locked`, `not-logged-in`, `wrong-account`, `unlock-window-opened`, `status-unrecognized`, `item-failed`, `timeout`, `dcli-missing`, `not-configured`.
- Ordering: `attempt` is appended before `dcli read`; `retrieved` is appended after a successful read and **before** the value is returned. If either append fails (missing or unwritable `logs/`), `get_secret` discards the value and raises `VaultError("log-unwritable")` — no key is ever handed out without a record.
- Semantics, named accurately: the log proves **retrieval from the vault by a named caller**. It does not record whether the downstream request then succeeded; because keys are fetched once per OB import or JFA run, retrieval time is the operation time. It also shows how often re-authentication is actually needed.

**5. Config holds names, not values.** `pipelinepilot.config` gains `agent_vault_account`, `ob_key_vault_id` and `anthropic_key_vault_id` (Dashlane item IDs of the two key items; required, no defaults; looked up once in Phase 1), and optional `dcli_path` (default `dcli` on PATH). The code stops reading `ob_supabase_key` and `anthropic_api_key` and never falls back to them. They are removed from `DEFAULTS`; whether they survive in the file during burn-in no longer matters for backout (see Backout).

**6. Failures are visible.** In `ob_bridge.fetch_qfl_thoughts()`, a non-200 response from Supabase raises an error instead of returning `[]`, so a bad vault credential cannot masquerade as an empty import. Shipped as its own commit with its own test, separately revertible.

**7. Remove the `ClaudeAPIkey.txt` fallback** from `fit_analysis_engine._get_api_key()` and the JFA launch check.

**8. Settings.** The two key fields are replaced by `agent_vault_account`, the two vault item IDs, and a **Test vault access** button that runs the full flow for both items and reports `OK` or the failure class, never a value. Labels and the "OB Not Configured" message stop referring to a "service_role JWT" — its own commit.

### Rollout, backup and backout

This change touches no database schema and no opportunity folders, but backup and backout are planned for the corruption case anyway, and rehearsed before the working copy is touched. Backups live in the protected OneDrive tree; config backups contain the legacy key values and are deleted in Phase 4.

**The backup set is the only supported database recovery path. OneDrive version history is not one:** it keeps 30 days, a replace-by-rename may not be recorded as a version, and OneDrive can upload a live `.db` and its `-wal` at different moments, so cloud versions of the database may be inconsistent.  is about key exposure, not recovery.

**Before any backup or restore:** be online, or set `00_JobSearch` and `PipelinePilot_Backups` to *Always keep on this device* (cloud-only placeholders download when read; offline reads fail and the run reports FAIL rather than skipping). **Pause OneDrive sync for the duration of a restore** so it cannot hold files open (the restore retries a locked replace three times, then fails safely with production unchanged).

**Phase 0 — Mark the recovery point.** In the working PipelinePilot folder: confirm `git status` is clean; tag the current commit `pre-adr013`.

**Phase 1 — Build, test and rehearse away from the working copy.** Separate checkout on branch `adr-013-vault`, with its own `pipelinepilot.config` pointing at a **copy** of the database and a scratch job search root; MCP tested against the same copy via `PIPI_MCP_DB_PATH`.
- *Build pass criteria:* automated tests green (see Tests); manual runs in **both** the desktop app and the MCP tool of: unlocked; locked (`dcli lock` first); logged out; wrong password then successful retry; window closed without completing then retry; access log lines correct; sentinel absent everywhere.
- *Backout rehearsal (on the clone, before cutover):* the backup and restore scripts read paths from the config beside them, so run from the clone checkout they act only on the clone. With the clone stopped: run `PipelinePilotBackupFile.bat`; damage the clone (change the config, delete rows); run `PipelinePilotRestoreFile.bat --only config`, then `--only database`; confirm `RESULT: PASS`, `integrity_check` = `ok` and row counts matching the backup; check out `pre-adr013` in the clone; start the desktop app and the MCP server against the restored clone; read-only smoke test (open pipeline view, list opportunities via MCP). Record the time taken. Cutover does not start until this passes.

**Phase 2 — Cutover, at a quiet time.**
1. Fully stop PipelinePilot **and** Claude Desktop (which hosts the MCP server); confirm no process holds `pipelinepilot.db`. Pause OneDrive sync until step 2 finishes.
2. Fresh cutover backup: run `PipelinePilotBackupFile.bat`. It copies the database through SQLite's backup API (WAL contents included), the config, and the job search root; records size, modified time and SHA-256 for every file in `manifest.csv`; runs `PRAGMA integrity_check` and per-table row counts; and writes `BACKUP_COMPLETE` only if every item verified. Cutover continues only on `RESULT: PASS` **and** `VALID FOR CUTOVER: YES` (the tool marks a backup not valid for cutover if PipelinePilot, its MCP server or Claude Desktop was running, or if its process check could not run).
3. Merge `adr-013-vault` to `main`; pull in the working folder.
4. Start **PipelinePilot only** (Claude Desktop stays closed, so the MCP server cannot run with incomplete settings). Set and save `agent_vault_account` and the two item names in Settings. Run Test vault access, one OB import, one JFA run.
5. Start Claude Desktop. Run one MCP OB import. Check the access log for all four operations.

**Stop / backout triggers (Phases 2–3).** Any of: `integrity_check` not `ok`; opportunity row count drops unexpectedly; OB import or JFA fails for a reason other than vault state that Jonathan can clear by unlocking; any key value appears in a log, dialog, error or file; Jonathan's call.

**Backout (any time in Phases 2–3).**
1. Fully stop PipelinePilot and Claude Desktop; pause OneDrive sync. (The restore refuses to run while either is running, or if it cannot confirm they are stopped.)
2. `git checkout pre-adr013` in the working folder.
3. Run `PipelinePilotRestoreFile.bat --only config` and choose the cutover backup. It re-verifies the backup's hashes, saves the current config under `RESTORE_<time>/pre_restore/`, and restores the config that holds the legacy key values. Settings changes made during burn-in are lost — accepted for a 7-day window. If that copy is unusable, re-enter the two values by hand from the Dashlane agent vault.
4. Restart and smoke test as in the rehearsal (`integrity_check`, row count, pipeline view, one MCP list).
5. Only if step 4 fails: `PipelinePilotRestoreFile.bat --only database` (run `--dry-run` first). It moves any live `-wal`/`-shm` aside before restoring. This loses opportunity changes made since cutover; note them before restoring and re-enter by hand. The replaced database is kept in `pre_restore/`.

**Phase 3 — Burn-in, 7 days of normal use.** Review `logs/vault_access.log` at the end: every retrieval has a caller; no unexpected callers; re-authentication frequency noted.

**Phase 4 — Completion (Jonathan sign-off required).** Remove `ob_supabase_key` and `anthropic_api_key` from `pipelinepilot.config` by hand; confirm with a count-only key-shape check that the file contains no secret-shaped string; delete the cutover and rehearsal config backups. This closes the one-step code-only rollback: after Phase 4, running `pre-adr013` again needs the keys re-entered by hand from the vault. is then resolved. The `pre-adr013` tag and the DB backups stay.

### Rationale

- One place for each secret (the vault), one module that reads it, nothing written back to disk.
- `dcli status` gives a prompt-free state probe, so the program never hangs on an unanswerable prompt; the state table makes every outcome explicit and anything unexpected fails closed.
- One `dcli`-owned window for both locked and logged-out keeps the master password and second factor out of PipelinePilot entirely, with the least code.
- Binding to the configured account stops a same-named item in the wrong vault from being sent to a service.
- Per-operation fetch is the simplest correct design for infrequent operations; a rotated key takes effect on the next operation, so the next Anthropic key rotation becomes a vault-only change.
- A fail-closed access log means every key handed out has a record.
- Backout restores the cutover config instead of relying on legacy fields surviving in place, so no settings-save path can break rollback.

### Rejected Alternatives

- **Environment variables filled by `launch.bat`.** Two launch paths would each need a launcher; values would sit in inherited process environments.
- **Windows Credential Manager / Python `keyring`.** A second secret store beside the vault; two places to rotate.
- **Keep the keys in the config file because OneDrive is protected.**  chose one location per secret.
- **Detect a locked vault by timing out a read.** Slower, and indistinguishable from other hangs.
- **dcli non-interactive service-device mode** (`dcli devices register` + `DASHLANE_SERVICE_DEVICE_KEYS`, documented, no prompts). Puts a vault-wide secret back into an environment variable or file — the problem this ADR removes — and drops the master-password prompt Jonathan asked for.
- **Pass the master password to `dcli` programmatically, or collect login steps in a custom PipelinePilot form.** Routes the master password and second factor through PipelinePilot code.
- **Background credential broker or app-lifetime cache.** More moving parts; a rotated key would not apply until restart.
- **Per-request "key used" event at each call site** (suggested in review). Retrieval is once per operation, so retrieval time already answers "when were my keys used"; extra events add code in two modules for little gain. Rejected by Jonathan, 2026-10-12.
- **Code-only backout relying on legacy fields surviving every settings save** (v2). Replaced by restoring the cutover config backup.

### Consequences

- **Dependency:** `dcli` installed and logged in to the agent account on any machine that runs OB import or JFA. All other PipelinePilot functions work without it.
- **To verify in Phase 1:** that the MCP server, started by Claude Desktop, can open the unlock window (Windows `CREATE_NEW_CONSOLE`). If it cannot, MCP returns the error with instructions to unlock from the desktop app or run `dcli sync` in a terminal; this is acceptable.
- **Backup and restore tooling (already built, tool v1.2):** `PipelinePilotBackupFile.bat`, `PipelinePilotRestoreFile.bat`, `tools/pp_backup_restore.py`. Backup: SQLite backup API, `integrity_check`, row counts, `foreign_key_check`, `user_version` and schema hash compared source-to-copy; SHA-256 per file; `VALID FOR CUTOVER` flag; process re-check at end. Restore: re-verifies the backup; refuses while PipelinePilot, the MCP server or Claude Desktop runs, or when the process check fails; stages and verifies a temp copy before touching production; moves live `-wal`/`-shm` aside only at the replace and puts them back if it fails; retries locked replaces; saves replaced files to `pre_restore/`; halts on a database/config failure; `--dry-run`, `--only`, `--path`. Every run, including refused ones, writes `run.log`, `manifest.csv`, `summary.json` and a line in `PipelinePilot_audit.log`. Tested on scratch data (cases listed in OB).
- **Code:** new `vault.py` and `unlock_window.py`; changes to `config.py`, `models.py`, `pipelinepilot.py` (Settings, OB import, JFA check), `mcp_server/tools.py`, `fit_analysis_engine.py`, `ob_bridge.py`; `.gitignore` covers `logs/`.
- **Tests (mocked subprocess, synthetic sentinel secret, no real vault):**
  - State table: each row, including logged out without a `Locked` line, case/whitespace variants, duplicate contradictory fields, unparseable output, status non-zero and timeout.
  - Account binding: wrong account while unlocked and while locked; `agent_vault_account` empty.
  - Read failures: non-zero, empty output, timeout (including a read that hangs while the vault is unlocked, e.g. an auto-sync waiting on input), `dcli` missing.
  - Read by ID: `dl://<item-id>/password` used; Test vault access shows the title only; the two Dashlane environment variables are absent from the dcli child environment; `dcli-version` logged once per process.
  - Unlock window: launched once per process while running; launch failure reported; Retry reruns status.
  - Access log: `attempt` before read; `retrieved` before return; unwritable/missing `logs/` → no value returned; fixed caller/event values; desktop and MCP callers write to their own files.
  - No-leak: sentinel absent from stdout/stderr, exception text and `__cause__`/`__context__`, dialog/MCP error text, access log, other app logs, config, environment, argv, and any file written during the run.
  - Unlock helper: `dcli sync` exit 0 → helper exits; non-zero → helper waits, Retry reports the window still open; after it is closed, Retry opens a new window. Successful login, later relock → a new window opens.
  - State-table precedence: logged out with and without `Locked`/`Login`; wrong account while locked → `wrong-account`, no window; `Logged in: Yes` missing `Locked` or `Login` → `status-unrecognized`.
  - `ob_bridge` non-200 raises; MCP `run_ob_import` uses `get_secret()`; a changed vault value is used on the next operation.
- **Docs:** README setup, Data Dictionary config keys, CHANGELOG, MCP Server PRD (credential source).
- **No rotation** is required by this change. The Anthropic key still rotates before its expiry date.
- **Out of scope:** credentials held by other tools and agents.

### Review

Reviewed under Jonathan's multi-model review gate before acceptance: Claude (author), Gee (ChatGPT) in three rounds, Mini (Gemini) on design and code, and Lexi (Perplexity) as a fact-check of the external dcli, SQLite, Windows and OneDrive assumptions. All three reviewers returned APPROVE_WITH_CHANGES. Every blocking finding was fixed before acceptance, including two defects in the backup/restore tool found by the fact-check (a failed replace could strand the live WAL file; a failed process check let a restore proceed). Two suggestions were declined for simplicity: reading the Claude Desktop config to identify the MCP server (restore refuses whenever Claude Desktop runs), and having the unlock window report its own visibility (verified in Phase 1, with a fallback).

---

*ADRs 001–007 produced from a structured requirements interview and cross-platform AI design session (Claude + ChatGPT) conducted March 7, 2026.*
*ADR-008 added March 12, 2026, following several days of production use.*
*ADRs 009–011 added August 7, 2026, driven by follow-up maintenance skill design work and data analysis of all 197 pipeline records.*
*ADR-012 added October 6, 2026, after tracing why job URLs captured at quick-fit never reached promoted opportunities.*
*ADR-013 added October 12, 2026, after a security review found live API keys in plain text in the config file; reviewed by Claude, ChatGPT, Gemini and Perplexity before acceptance.*
