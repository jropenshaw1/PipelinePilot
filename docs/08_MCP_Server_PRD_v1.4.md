# PipelinePilot MCP Server — Product Requirements Document

**Version:** 1.4  
**Date:** August 7, 2026  
**Author:** Jonathan Openshaw  
**Drafter:** Claude (Anthropic)  
**Status:** Implemented

**Change Log:**
- **v1.0** — Initial draft
- **v1.1** — Incorporated follow-up workflow clarifications (action_items append behavior, follow-up date logic, ghosted closure format, scope boundary with follow-up skill)
- **v1.2** — Corrected SQL logging target from stdout to stderr (stdio MCP protocol conflict, raised by Codex during implementation planning); documented `PIPI_MCP_DB_PATH` test override; documented known follow-up offset inconsistency between Data Dictionary and code
- **v1.3** — Post-implementation corrections. Tool count corrected from 16 to 15 in §11 (arithmetic error in the Definition of Done; the §6 table was always correct). Replaced the §9.3 log format example with output actually captured from the SQLite trace callback. Noted scenario 17's deferred live verification.
- **v1.4** — Schema change: added `posting_status_log` column (ADR-009). `pipi_log_still_posted` writes to `posting_status_log` instead of `action_items`. `pipi_close_opportunity` drops `ghosted` boolean parameter; "Ghosted" added as terminal status (ADR-009). Follow-up dates snap to next Monday, initial offset driven by config at 14 days (ADR-010). `pipi_query_pipeline` accepts multi-select `status_filter` (ADR-011). Resolved §7.3 known inconsistency.

---

## 1. Problem Statement

PipelinePilot's SQLite database is the structured index of Jonathan's job search pipeline. Today, pipeline updates captured during Claude sessions (status changes, communications logged, opportunities closed, follow-up dates extended) are written to OpenBrain as structured entries, then manually imported or entered into PipelinePilot by Jonathan. This manual sync gap creates three problems:

1. **Latency** — Pipeline state in PIPI lags behind decisions made in conversation, sometimes by hours or days.
2. **Friction** — Every status update requires Jonathan to context-switch from the conversation to the desktop app.
3. **Drift** — OB entries and PIPI records can diverge when manual sync is skipped or partially completed.

## 2. Proposed Solution

A lightweight MCP (Model Context Protocol) server that exposes PipelinePilot's existing `database.py` functions as tools callable from Claude sessions. The server runs locally on Jonathan's machine and connects to Claude Desktop via the standard MCP configuration.

The MCP server is a **thin tool layer**, not a new application. It imports and calls existing PipelinePilot functions. It introduces no new business logic, no new validation rules, and no new data model changes beyond those specified by ADR-009, ADR-010, and ADR-011. If `database.py` does not support an operation, the MCP server does not offer it.

### 2.1 Relationship to Follow-Up Skill

The MCP server is **Layer 1** of a three-layer follow-up architecture:

| Layer | Component | Responsibility |
|---|---|---|
| Layer 1 | **PIPI MCP Server** (this PRD) | Database read/write. Exposes `job_url`, `posting_status_log`, `action_items`, `follow_up_date`, `status`. Knows nothing about Gmail or web pages. |
| Layer 2 | **Existing connected tools** | Gmail MCP (search Applied folder), web_fetch (check if URL returns a live posting). Already available in every session. |
| Layer 3 | **Follow-Up Skill** (separate deliverable) | Orchestration procedure that tells Claude how to run the full follow-up workflow across all three layers. Specification complete (followup-maintenance SKILL.md v1.0). |

This PRD covers Layer 1 only. The follow-up skill is a separate artifact.

## 3. Project Goals

### Primary Goal — Close the Sync Gap
Enable Claude to read from and write to PipelinePilot's SQLite database directly during conversation, eliminating the manual OB-to-PIPI sync step for routine operations.

### Secondary Goal — Preserve Architecture Integrity
Respect PipelinePilot's filesystem-first architecture. The MCP server wraps existing functions; it does not bypass, duplicate, or extend them. All writes go through `database.py` validation paths.

### Tertiary Goal — Public Showcase
Demonstrate MCP server implementation as a practical extension of an existing open-source project. Clean, documented, consistent with PipelinePilot's engineering standards.

## 4. Scope

### In Scope

- MCP server exposing read and write tools against `pipelinepilot.db`
- Tools wrap existing `database.py`, `models.py`, `config.py`, and `ob_bridge.py` functions
- Local execution only (stdio transport, not HTTP)
- Configuration via `config.load_config()` (existing module) for database path resolution
- Logging of every SQL statement executed to stderr (see §9)
- Claude Desktop MCP configuration snippet documented in README
- Structured append logic for `posting_status_log` field (STILL POSTED log, NOT POSTED entry on ghosted closure) — see §7.1
- Environment-variable database override for isolated testing (see §5.5)
- "Ghosted" as a first-class terminal status (ADR-009)
- Config-driven follow-up offset with Monday-snap scheduling (ADR-010)
- Multi-select status filtering (ADR-011)
- One new column: `posting_status_log TEXT` added to `opportunities` table (ADR-009)

### Out of Scope

- New database tables
- New business logic beyond what `database.py` already implements
- HTTP/SSE transport (local stdio only for v1)
- Desktop UI changes to PipelinePilot
- Authentication or multi-user support
- Filesystem operations (folder creation, artifact management)
- OB bridge automation (run_import remains a manual trigger)
- fit_analysis.md parsing or Job Fit Analyst integration
- Gmail search or job URL verification (handled by Layer 2/3)
- Follow-up orchestration logic (handled by Layer 3 skill)

## 5. Architecture

### 5.1 Placement

Module within the existing PipelinePilot repository:

```
PipelinePilot/
  mcp_server/
    __init__.py
    server.py          # MCP server entry point
    tools.py           # Tool definitions wrapping database.py
    README.md          # Setup and Claude Desktop config instructions
  config.py            # Existing — imported for load_config()
  database.py          # Existing — imported by tools.py
  models.py            # Existing — imported by tools.py
  ob_bridge.py         # Existing — imported for run_import()
  pipelinepilot.config # Existing — read via config.load_config()
  migrations/
    migrate_action_items_to_posting_status_log.py  # One-time data relocation (ADR-009)
  ...
```

### 5.2 Dependencies

- `mcp` — Anthropic's MCP Python SDK, declared in `requirements.txt` as `mcp>=1.0.0`
- `sqlite3` — Standard library
- All existing PipelinePilot dependencies

### 5.3 Transport

stdio (standard input/output) — the default for local MCP servers. Claude Desktop launches the server as a subprocess.

**Protocol constraint:** stdio transport reserves stdout exclusively for JSON-RPC message framing. The server must not write any non-protocol bytes to stdout. See §9 for the resulting logging requirement.

### 5.4 Configuration and Path Resolution

The MCP server reuses the existing `config.py` module rather than parsing configuration independently:

- `server.py` resolves the repository root via `Path(__file__).resolve().parents[1]` and inserts it into `sys.path` before importing project modules, making imports independent of the working directory Claude Desktop launches from.
- `config.load_config()` returns the merged configuration dict. `config.CONFIG_PATH` is anchored to `config.py`'s own directory, so it resolves correctly regardless of subprocess working directory.
- The database path is derived via `database.get_db_path(config["job_search_root"])`.

The Claude Desktop config entry points to the server entry point:

```json
{
  "mcpServers": {
    "pipelinepilot": {
      "command": "python",
      "args": ["C:\\path\\to\\PipelinePilot\\mcp_server\\server.py"],
      "env": {}
    }
  }
}
```

### 5.5 Test Database Override

The server supports a single environment variable, `PIPI_MCP_DB_PATH`, which overrides the config-derived database path when set.

**Purpose:** isolated test execution against a disposable copy of the database without editing the live configuration.

**Behavior:**
- When `PIPI_MCP_DB_PATH` is set, the server uses that path and logs the override to stderr at startup.
- When unset (normal Claude Desktop operation), the path is derived from `config.load_config()` as described in §5.4.

**Constraint:** This override exists for testing only. It is not part of normal operation and must not be set in the Claude Desktop configuration.

## 6. Tool Definitions

Each tool maps to one or more existing `database.py` functions. Tools are grouped by operation type.

**Total: 15 tools** — 5 read (§6.1) + 9 write (§6.2) + 1 import (§6.3).

### 6.1 Read Tools

| Tool Name | Description | Wraps | Parameters |
|---|---|---|---|
| `pipi_query_pipeline` | List active opportunities with optional filters | `get_all_opportunities()` | `status_filter` (optional, accepts `string \| list[string] \| null` — ADR-011), `include_archived` (bool, default false), `sort_by` (optional) |
| `pipi_get_opportunity` | Fetch a single opportunity by folder_name | `get_opportunity()` | `folder_name` (required) |
| `pipi_get_dashboard` | Return pipeline metrics (counts by status, avg fit, follow-ups due) | `get_dashboard_metrics()` | None |
| `pipi_get_followups_due` | Return opportunities with overdue follow-up dates | `get_followups_due()` | None |
| `pipi_search_opportunities` | Search opportunities by company name or role title substring | Parameterized SELECT (company_name LIKE or role_title LIKE) | `search_term` (required) |

### 6.2 Write Tools

| Tool Name | Description | Wraps | Parameters |
|---|---|---|---|
| `pipi_update_status` | Change opportunity status | `update_opportunity()` | `folder_name` (required), `status` (required, validated against STATUS_VALUES) |
| `pipi_update_followup` | Set or extend follow-up date | `update_opportunity()` | `folder_name` (required), `follow_up_date` (required, ISO 8601) |
| `pipi_log_communication` | Record employer communication | `update_opportunity()` | `folder_name` (required), `last_communication_date` (required), `last_communication_type` (required, validated against LAST_COMM_TYPES), `communication_notes` (optional) |
| `pipi_update_contact` | Set or update recruiter/hiring manager contact info | `update_opportunity()` | `folder_name` (required), `contact_name` (optional), `contact_email` (optional) |
| `pipi_close_opportunity` | Set terminal status with optional communication notes | `update_opportunity()` | `folder_name` (required), `status` (required, must be in TERMINAL_STATUSES including "Ghosted"), `communication_notes` (optional). When `status="Ghosted"`, appends `NOT POSTED: YYYY-MM-DD` to `posting_status_log`. |
| `pipi_archive_opportunity` | Soft delete an opportunity | `archive_opportunity()` | `folder_name` (required) |
| `pipi_mark_applied` | Set status to Applied with date and schedule Monday follow-up | `update_opportunity()` | `folder_name` (required), `date_applied` (required, ISO 8601), `job_url` (optional). Follow-up date auto-generated as `next_monday(date_applied + follow_up_offset_days)`. Offset read from config (default 14). |
| `pipi_log_still_posted` | Append today's date to `posting_status_log` STILL POSTED line and set follow-up to next Monday | `update_opportunity()` | `folder_name` (required) |
| `pipi_add_interview` | Create an interview record linked to an opportunity | Parameterized INSERT into interviews table | `folder_name` (required), `interview_type` (required), `scheduled_date` (required), `interviewer_name` (optional), `interviewer_title` (optional), `notes` (optional) |

### 6.3 Import Tools

| Tool Name | Description | Wraps | Parameters |
|---|---|---|---|
| `pipi_run_ob_import` | Trigger OpenBrain bridge import | `ob_bridge.run_import()` | None (reads Supabase creds from config) |

## 7. Field-Level Behaviors

### 7.1 posting_status_log — Machine-Maintained Posting Lifecycle

This field stores posting verification history and closure evidence. It is written exclusively by MCP tools — it is not a free-text field for human notes. Two tools write to this field:

#### pipi_log_still_posted

Reads the current `posting_status_log` value. Finds the `STILL POSTED:` line. If it exists, appends today's date pipe-delimited. If it does not exist, creates the line. All dates are ISO 8601 (YYYY-MM-DD).

Example — field before:
```
STILL POSTED: 2026-07-07 | 2026-07-16 | 2026-07-27
```

Field after calling `pipi_log_still_posted` on 2026-08-07:
```
STILL POSTED: 2026-07-07 | 2026-07-16 | 2026-07-27 | 2026-08-07
```

Example — field before (empty):
```
(null)
```

Field after:
```
STILL POSTED: 2026-08-07
```

This tool also sets `follow_up_date` to `next_monday(today)` — the next Monday strictly after the validation date.

#### pipi_close_opportunity with status="Ghosted"

When status is "Ghosted", appends `NOT POSTED: YYYY-MM-DD` to `posting_status_log` (preserving existing STILL POSTED line above), then sets `status` to "Ghosted".

Example — field before:
```
STILL POSTED: 2026-07-07 | 2026-07-16 | 2026-07-27
```

Field after calling `pipi_close_opportunity(status="Ghosted")` on 2026-08-07:
```
STILL POSTED: 2026-07-07 | 2026-07-16 | 2026-07-27
NOT POSTED: 2026-08-07
```

For non-Ghosted terminal statuses (Closed, Rejected, Passed), `posting_status_log` is not modified. Those closures are status-driven, not posting-driven.

### 7.2 action_items — Restored Scope

`action_items` holds pending human tasks only — things the user still needs to do. `pipi_log_still_posted` and `pipi_close_opportunity` no longer write to this field. No MCP tool appends structured data to `action_items`. The field is read/write for the user via the desktop UI and via `pipi_update_opportunity` (if exposed in a future version). See ADR-009 for the rationale and migration plan.

### 7.3 follow_up_date — Monday-Snap Logic

All follow-up dates are set to a Monday, via `next_monday()`:

```python
def next_monday(reference_date: date) -> date:
    """Return the next Monday strictly after reference_date."""
    days_ahead = 7 - reference_date.weekday()
    if days_ahead == 7:
        days_ahead = 7
    return reference_date + timedelta(days=days_ahead)
```

**Initial follow-up (pipi_mark_applied):**
`follow_up_date = next_monday(date_applied + timedelta(days=follow_up_offset_days))`

The offset is read from config (`follow_up_offset_days`). Default: 14 days. Fallback: `DEFAULT_FOLLOW_UP_OFFSET_DAYS` from `models.py` (also 14).

**Still-posted recheck (pipi_log_still_posted):**
`follow_up_date = next_monday(today)`

**Manual override (pipi_update_followup):**
Caller provides the exact target date. No automatic Monday snap — the caller is responsible for choosing the date. Validation: must not precede `date_applied`.

### 7.4 Known Inconsistency — RESOLVED

PRD v1.3 §7.3 documented a known inconsistency between the Data Dictionary (14 days), `models.py` (30 days), and `config.py` (config key existed but was never read). Resolved by ADR-010:

- `models.py` constant updated to 14
- `database.py` reads from config, falls back to constant
- `pipelinepilot.config` value updated to 14
- Data Dictionary v1.1 reflects the corrected behavior

## 8. Validation Rules

All validation follows existing `database.py` and `models.py` rules:

- `status` must be in `STATUS_VALUES` (Title Case), which now includes "Ghosted"
- `status_filter` accepts a single string or list of strings; each validated against `STATUS_VALUES`
- `last_communication_type` must be in `LAST_COMM_TYPES`
- `interview_type` must match the CHECK constraint enum
- Dates must be valid ISO 8601 (YYYY-MM-DD)
- `folder_name` must reference an existing opportunity (validated before write)
- `date_applied` cannot precede `date_discovered`
- `follow_up_date` cannot precede `date_applied` (if both set)
- Terminal statuses (Passed, Offer, Closed, Ghosted, Rejected) are validated via `TERMINAL_STATUSES`
- `posting_status_log` dates must be ISO 8601 (YYYY-MM-DD), enforced by tool code

The MCP server validates inputs before calling `database.py`. Invalid inputs return a clear error message naming the invalid field and the allowed values. Error messages must never include configuration values, file paths outside the repository, or credentials.

## 9. Logging and Governance

### 9.1 Logging Target — stderr, not stdout

**All SQL logging is written to stderr.**

**Rationale:** stdio MCP transport reserves stdout exclusively for JSON-RPC message framing. Writing log output to stdout corrupts the protocol stream and prevents Claude Desktop from connecting. Claude Desktop captures subprocess stderr as server logs, so stderr satisfies the observability requirement without breaking the transport.

This corrects PRD v1.0 and v1.1, both of which incorrectly specified stdout. Any implementation, README, or governance text stating stdout is superseded by this section.

### 9.2 Logging Mechanism

SQL statements are captured via a SQLite trace callback:

- `tools.py` preserves the original `database._connect` reference, then replaces `database._connect` with a wrapper that calls the original factory and installs `connection.set_trace_callback(...)` before returning the connection.
- Because functions in `database.py` resolve `_connect` from module globals at call time, this reaches every connection created by its public functions without modifying `database.py`.
- The same callback is installed on connections used by the direct search query and interview insert.
- The monkey patch must be documented inline as an intentional, load-bearing decision.

**Failure modes:**
- If callback installation fails, the wrapper raises a server-visible error rather than proceeding silently without logging.
- Exceptions raised inside the callback are caught and reported on stderr; they must not interrupt a database operation already in progress.

### 9.3 Governance Constraints

Per CLAUDE.md:

- No DROP, TRUNCATE, or unqualified DELETE operations are exposed as tools
- All opportunity writes go through `update_opportunity()`, which auto-sets `date_modified`
- The MCP server never modifies schema beyond the governed additions specified by ADR-009

Log format — the SQLite trace callback delivers the statement with bound parameters already expanded inline, so no separate parameter list is emitted:

```
[2026-07-27T16:29:48] PIPI-MCP | UPDATE opportunities SET status = 'In Review', date_modified = '2026-07-27' WHERE folder_name = 'ArrayTest_MCPDue'
```

**Note:** because values are expanded inline, stderr logs contain actual field data — including contact emails and communication notes when those fields are written. Claude Desktop captures stderr as local subprocess logs. This is acceptable for single-user local operation but should be considered if the transport is ever changed per §13.

## 10. Error Handling

| Condition | Behavior |
|---|---|
| Database file not found | Return error naming the expected path source (config key or env override), without printing credential values |
| folder_name not found | Return error: "Opportunity '{folder_name}' not found" |
| Invalid status value | Return error listing valid STATUS_VALUES |
| Invalid status_filter list entry | Return error identifying the invalid value and listing all valid STATUS_VALUES |
| Invalid communication type | Return error listing valid LAST_COMM_TYPES |
| Invalid date format | Return error: "Date must be YYYY-MM-DD format" |
| SQLite locked (desktop app has it open) | Retry once after 1 second, then return error suggesting closing the desktop app |
| Config file missing | Return error with expected config path |
| Trace callback installation failure | Raise server-visible error; do not proceed unlogged |

## 11. Definition of Done

- [x] MCP server starts cleanly via `python mcp_server/server.py`
- [x] All 15 tools respond correctly to valid inputs
- [x] All validation rules reject invalid inputs with clear error messages
- [x] Claude Desktop can connect and invoke all tools
- [x] Read tools return accurate data matching desktop app queries
- [x] Write tools update the database and are visible in the desktop app on refresh
- [x] `pipi_log_still_posted` correctly appends dates to `posting_status_log` (pipe-delimited)
- [x] `pipi_close_opportunity` with `status="Ghosted"` appends `NOT POSTED` to `posting_status_log`
- [x] **Every SQL statement is logged to stderr; stdout carries only JSON-RPC protocol messages**
- [x] `requirements.txt` declares the `mcp` dependency
- [x] README documents Claude Desktop configuration, the 15 tools, the stderr logging rationale, and `PIPI_MCP_DB_PATH` usage
- [x] CLAUDE.md updated with `mcp_server/` reference (thin-wrapper role, config-based, stdio, stderr SQL logging)
- [x] All changed files reviewed for private-path and credential leakage before commit
- [x] Committed to PipelinePilot repo under `mcp_server/` directory
- [x] "Ghosted" recognized as terminal status in all tool validation paths
- [x] Follow-up dates snap to next Monday via `next_monday()` utility
- [x] `follow_up_offset_days` read from config (default 14)
- [x] Multi-select `status_filter` accepted in `pipi_query_pipeline`

## 12. Test Scenarios

All scenarios execute against a disposable copy of the database (`pipelinepilot_test.db`) via `PIPI_MCP_DB_PATH`. The live database is never opened for writes during testing. The live database file hash is verified unchanged after the suite completes.

### v1.3 Scenarios (1–20)

| # | Scenario | Expected Result |
|---|---|---|
| 1 | `pipi_query_pipeline` with no filters | Returns all non-archived opportunities |
| 2 | `pipi_query_pipeline` with status_filter="Applied" | Returns only Applied opportunities |
| 3 | `pipi_get_opportunity` with valid folder_name | Returns full opportunity record |
| 4 | `pipi_get_opportunity` with invalid folder_name | Returns clear error |
| 5 | `pipi_update_status` to "Applied" | Updates status, sets date_modified |
| 6 | `pipi_update_status` to "InvalidStatus" | Returns validation error with allowed values |
| 7 | `pipi_mark_applied` with date | Sets status, date_applied, auto-generates follow_up_date as next Monday after date_applied + 14 days |
| 8 | `pipi_close_opportunity` with "Closed" | Sets terminal status, appends communication_notes |
| 9 | `pipi_close_opportunity` with `status="Ghosted"` | Sets status to "Ghosted", appends `NOT POSTED: YYYY-MM-DD` to `posting_status_log` |
| 10 | `pipi_log_communication` with valid type | Updates all communication fields |
| 11 | `pipi_get_followups_due` | Returns only opps with follow_up_date <= today and non-terminal status (excludes Ghosted) |
| 12 | `pipi_get_dashboard` | Returns metrics matching desktop app dashboard; follow_ups_due excludes Ghosted |
| 13 | `pipi_add_interview` with valid data | Creates interview record linked to opportunity |
| 14 | `pipi_search_opportunities` for "Array" | Returns Array Technologies record |
| 15 | `pipi_log_still_posted` on opp with existing `posting_status_log` STILL POSTED line | Appends today's date pipe-delimited, sets follow_up_date to next Monday |
| 16 | `pipi_log_still_posted` on opp with null `posting_status_log` | Creates `STILL POSTED: YYYY-MM-DD`, sets follow_up_date to next Monday |
| 17 | `pipi_run_ob_import` | Executes OB bridge and returns import summary. **Verified on the configuration-error path only** — `ob_supabase_url` and `ob_supabase_key` were empty in the local config at initial build time, so a live import could not run. `ob_bridge.run_import()` is pre-existing code; the MCP wrapper is thin. Live verification deferred pending credential configuration. |
| 18 | `pipi_log_still_posted` then `pipi_close_opportunity(status="Ghosted")` | STILL POSTED dates preserved in `posting_status_log`, `NOT POSTED` entry appended below |
| 19 | Inspect stdout during any tool invocation | Contains only JSON-RPC protocol messages, no log lines |
| 20 | Inspect stderr during any write tool invocation | Contains timestamped SQL statement with parameters |

### v1.4 Scenarios (21–30)

| # | Scenario | Expected Result |
|---|---|---|
| 21 | `pipi_log_still_posted` on opp with existing `posting_status_log` | Appends today's date pipe-delimited to STILL POSTED line. `action_items` unchanged. `follow_up_date` set to next Monday. |
| 22 | `pipi_log_still_posted` on opp with null `posting_status_log` | Creates `STILL POSTED: YYYY-MM-DD`. `action_items` unchanged. |
| 23 | `pipi_close_opportunity(status="Ghosted")` | Status set to "Ghosted". `NOT POSTED: YYYY-MM-DD` appended to `posting_status_log`. `action_items` unchanged. |
| 24 | `pipi_close_opportunity` with former `ghosted=true` parameter | Tool rejects `ghosted=true` as unknown parameter. |
| 25 | `pipi_close_opportunity(status="Closed")` | Status set to "Closed". `posting_status_log` unchanged. |
| 26 | `pipi_query_pipeline(status_filter=["Applied", "In Review"])` | Returns only Applied and In Review opportunities. |
| 27 | `pipi_query_pipeline(status_filter="Applied")` | Backward compatible — returns only Applied. |
| 28 | `pipi_query_pipeline(status_filter=["Applied", "InvalidStatus"])` | Returns validation error listing valid statuses. |
| 29 | `pipi_mark_applied` on a Wednesday | `follow_up_date` is a Monday (next Monday after date_applied + 14 days). |
| 30 | `pipi_log_still_posted` run on a Thursday | `follow_up_date` is the following Monday, not today + 7. |

## 13. Future Considerations

- ~~Follow-up offset reconciliation~~ — **Resolved** by ADR-010.
- **Follow-Up Skill (Layer 3)** — Orchestration procedure skill. Specification complete (followup-maintenance SKILL.md v1.0). Ready for deployment after v1.4 code changes ship and migration runs.
- **Data migration** — `migrations/migrate_action_items_to_posting_status_log.py` relocates STILL POSTED and GHOSTED data from `action_items` to `posting_status_log` and status field. Dry-run by default; `--apply` creates timestamped backup. See ADR-009 Consequences.
- **Filesystem operations** — folder creation, JD document generation (requires `filesystem.py` integration)
- **QFL tools** — direct quick-fit-log queries and archives via MCP
- **Batch operations** — update multiple opportunities in one call (e.g., batch followup extension)
- **Event notifications** — push alerts when follow-up dates pass due
- **HTTP/SSE transport** — for use outside Claude Desktop (e.g., Claude.ai web via tunnel)

---

*This PRD was produced through a structured design session on July 27, 2026, building on the existing PipelinePilot Project Charter v1.0 and Data Dictionary v1.0. Updated with follow-up workflow clarifications and implementation-planning corrections from Jonathan and Codex. v1.4 changes driven by ADR-009, ADR-010, and ADR-011, produced August 7, 2026.*
