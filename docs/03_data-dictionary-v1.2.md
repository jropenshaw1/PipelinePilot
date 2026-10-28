# PipelinePilot — Data Dictionary

**Version:** 1.2  
**Date:** October 28, 2026  
**Author:** Jonathan Openshaw  
**Status:** Approved

**Change Log:**
- **v1.0** (March 7, 2026) — Initial release
- **v1.1** (August 7, 2026) — Added `posting_status_log` field (ADR-009). Restored `action_items` to task-only scope (ADR-009). Added "Ghosted" to status lifecycle (ADR-009). Corrected follow-up offset to 14 days with Monday-snap behavior (ADR-010). Added multi-select status filtering (ADR-011). Pursuit tracker columns (`cl_reviewed`, `resume_reviewed`, `jfa_completed`) documented (previously added via migration 006 without Data Dictionary update).
- **v1.2** (October 28, 2026) — Status model v2 (ADR-014): ten statuses in three groups, Ready added, New / Capturing / In Review retired, Offer no longer terminal, default status Analyzing. Archive on Done: `archived` set with the folder move to the archive root; optional `archive_root` config key; folder-name suffix on reuse.

---

## 1. Overview

PipelinePilot maintains a single logical entity: the **Opportunity**. Each opportunity represents one job role at one company being tracked through the full job search lifecycle.

The data model has two physical representations:
- **Filesystem (OneDrive):** The source of truth. A `Company_Role` folder containing all artifacts.
- **SQLite Table (`opportunities`):** A derived, rebuildable index of structured fields extracted from filesystem artifacts.

The folder name (`Company_Role`) is the **primary key** across both representations.

---

## 2. Folder Naming Convention

**Pattern:** `CompanyName_RoleTitle`

**Sanitization Rules:**
| Input Character | Output |
|---|---|
| Space | Underscore `_` |
| Ampersand `&` | Stripped |
| Comma `,` | Stripped |
| Period `.` | Stripped |
| Forward slash `/` | Stripped |
| All other special chars | Stripped |
| Maximum combined length | 60 characters |

**Examples:**
| Company | Role | Folder Name |
|---|---|---|
| AT&T | Director, IT | `ATT_Director_IT` |
| Choice Hotels International | Sr. Director Cloud Infrastructure | `ChoiceHotelsInternational_SrDirectorCloudInfrastructure` |
| Cambridge Investment Research | VP IT Infrastructure & Operations | `CambridgeInvestmentResearch_VPITInfrastructureOperations` |

**Reuse:** if a generated name is already in use (checked case-insensitively against database keys and folders under the job search root and the archive root), a `_YYYY-MM` suffix is added, then `_YYYY-MM-2`, `_YYYY-MM-3` and so on, with the base shortened so the full name stays within 60 characters (ADR-014).

**Rule:** Folder name is previewed and confirmed by User before creation. Once created, it is never renamed without using PipelinePilot — a manual rename breaks the primary key link.

---

## 3. Filesystem Artifacts

Each `Company_Role` folder is expected to contain the following files:

| Filename | Type | Created By | Required | Description |
|---|---|---|---|---|
| `JD_Company_Role.docx` | Word document | PipelinePilot (blank) + User (content) | Yes | Job description, URL, contact details. Filename = `JD_` + `folder_name` + `.docx`. No separate sanitization — folder_name is already clean. |
| `fit_analysis.md` | Markdown + YAML | Job Fit Analyst skill | No (required for fit indexing) | YAML front-matter metadata + narrative analysis |
| `fit_analysis.docx` | Word document | Job Fit Analyst skill | No | Human-readable fit analysis for review and demos |
| `Resume_CompanyName_RoleTitle.docx` | Word document | Job Fit Analyst skill | No | Tailored resume for this role |
| `CoverLetter_CompanyName_RoleTitle.docx` | Word document | Job Fit Analyst skill | No | Tailored cover letter for this role |

---

## 4. fit_analysis.md — YAML Front-Matter Schema

PipelinePilot parses **only** the YAML front-matter block. The narrative body is ignored by the indexer and preserved for human reading.

```yaml
---
company: string           # Company name (human-readable, not sanitized)
role: string              # Role title (human-readable, not sanitized)
job_url: string           # URL to original job posting
analysis_date: date       # ISO 8601 format: YYYY-MM-DD
analysis_tool: string     # e.g. "job-fit-analyst"
analysis_version: string  # e.g. "1.0" — supports future model tracking
fit_score: float          # 0.00 to 1.00
fit_threshold: float      # Threshold used at time of analysis (e.g. 0.65)
recommendation: string    # "pursue" | "pass" | "undecided"
decision_override: bool   # true if User overrode recommendation
top_strengths:            # List of 2–5 strings
  - string
top_gaps:                 # List of 2–5 strings
  - string
---
```

---

## 5. SQLite Table: `opportunities`

**Table Name:** `opportunities`  
**Primary Key:** `folder_name`

### 5.1 Identity & Source Fields

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `folder_name` | TEXT | NOT NULL | — | Primary key. Auto-generated from company_name + role_title. Filesystem anchor. |
| `company_name` | TEXT | NOT NULL | — | Human-readable company name as entered by User |
| `role_title` | TEXT | NOT NULL | — | Human-readable role title as entered by User |
| `job_url` | TEXT | NOT NULL | — | URL to original job posting. **Required at capture.** (v1.1: enforcement added at quick-fit and capture entry points) |
| `source` | TEXT | NULL | — | Source board: LinkedIn / Indeed / Monster / Dice / Lensa / Ladders / Recruiter / Company Direct / Other |
| `source_other` | TEXT | NULL | — | Free-text clarification when source = "Other" (e.g., "Mary Beth") |
| `date_discovered` | DATE | NOT NULL | Current date | Auto-set when record is created |
| `restrictions` | TEXT | NULL | — | Pipe-delimited multi-select: "Degree Required \| Culture Concern \| Relocation Required" |
| `location_type` | TEXT | NULL | — | Remote / Hybrid / Onsite |
| `location_city` | TEXT | NULL | — | City and state if relevant |

### 5.2 Fit & Decision Fields

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `fit_score` | REAL | NULL | — | 0.00–1.00. Parsed from fit_analysis.md YAML front-matter |
| `fit_threshold` | REAL | NULL | 0.65 | Configurable threshold used at time of analysis |
| `recommendation` | TEXT | NULL | — | "pursue" / "pass" / "undecided" — from Job Fit Analyst |
| `decision_override` | INTEGER | NOT NULL | 0 | Boolean (0/1). True if User overrode Job Fit Analyst recommendation |
| `decision_notes` | TEXT | NULL | — | User's subjective override reasoning or gap assessment notes |
| `top_strengths` | TEXT | NULL | — | JSON array of strings parsed from fit_analysis.md |
| `top_gaps` | TEXT | NULL | — | JSON array of strings parsed from fit_analysis.md |

### 5.3 Application Fields

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `status` | TEXT | NOT NULL | "New" (schema); every insert path sets "Analyzing" | Lifecycle status (ADR-014): Analyzing / Ready / Applied / Pursuing / Interviewing / Offer / Passed / Rejected / Ghosted / Closed. See §6 for groups. |
| `date_applied` | DATE | NULL | — | Date application submitted |
| `confirmation_email` | TEXT | NULL | — | Paste area for confirmation email text content |
| `contact_name` | TEXT | NULL | — | Recruiter or hiring manager name |
| `contact_email` | TEXT | NULL | — | Recruiter or hiring manager email |

### 5.4 Employer Communications Fields

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `last_communication_date` | DATE | NULL | — | Date of most recent inbound employer message |
| `last_communication_type` | TEXT | NULL | — | Acknowledgment / Rejection / Phone Screen Request / Interview Request / Offer / Other |
| `communication_notes` | TEXT | NULL | — | Running log of employer touchpoints. Each entry prefixed with date. |

### 5.5 Follow-up, Action Items & Posting Status Fields

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `follow_up_date` | DATE | NULL | — | Auto-set to next Monday on or after (`date_applied` + `follow_up_offset_days`). Config-driven; default offset is 14 days. All follow-up dates snap to Monday. See ADR-010. |
| `action_items` | TEXT | NULL | — | **Pending human tasks only.** Things the user still needs to do: "Check LinkedIn connection status", "Send thank-you note", "Review benefits package". If nothing is pending, this field is empty. STILL POSTED dates, GHOSTED markers, communication history, and one-time observations do not belong here. See ADR-009. |
| `posting_status_log` | TEXT | NULL | — | **Machine-maintained posting lifecycle data.** Written exclusively by `pipi_log_still_posted` and `pipi_close_opportunity`. Not a free-text field for human notes. Format: `STILL POSTED: YYYY-MM-DD \| YYYY-MM-DD \| ...` on one line, `NOT POSTED: YYYY-MM-DD` on a separate line when posting disappearance is confirmed. All dates ISO 8601. See ADR-009. |
| `interview_date` | DATE | NULL | — | Scheduled interview date and time |
| `interview_notes` | TEXT | NULL | — | Pre- and post-interview notes |

### 5.6 Pursuit Tracker Fields

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `cl_reviewed` | INTEGER | NOT NULL | 0 | Boolean (0/1). Cover letter reviewed and finalized for this opportunity. |
| `resume_reviewed` | INTEGER | NOT NULL | 0 | Boolean (0/1). Tailored resume reviewed and finalized for this opportunity. |
| `jfa_completed` | INTEGER | NOT NULL | 0 | Boolean (0/1). Full Job Fit Analyst run completed for this opportunity. |

### 5.7 Housekeeping Fields

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `date_created` | DATE | NOT NULL | Current date | Auto-set on record creation. Never modified. |
| `date_modified` | DATE | NOT NULL | Current date | Auto-updated on any field change |
| `archived` | INTEGER | NOT NULL | 0 | Boolean (0/1). Set to 1 when the opportunity enters a Done status and its folder moves to the archive root (ADR-014). Archived records remain queryable and are excluded from active views. |

---

## 6. Status Lifecycle

```
Analyzing → Ready → Applied → Pursuing → Interviewing → Offer
    ↓         ↓        ↓          ↓            ↓           ↓
  Passed   Passed   Rejected / Ghosted / Closed (any stage after Ready)
```

| Group (ADR-014) | Statuses | Meaning |
|---|---|---|
| My move | Analyzing, Ready, Offer | The next action is the user's |
| Their move | Applied, Pursuing, Interviewing | Waiting on the employer or recruiter |
| Done | Passed, Rejected, Ghosted, Closed | Terminal; folder moves to the archive root and `archived` is set |

- **Analyzing:** imported or created, awaiting fit analysis or a decision. Default for every new record.
- **Ready:** analysis done, decided to apply, not yet submitted.
- **Applied:** submitted. For recruiter-submitted roles: right-to-represent signed and submission details sent.
- **Pursuing:** still live after the first follow-up.
- **Interviewing:** in an interview loop, including recruiter screens before the client conversation.

**Terminal statuses:** Passed / Rejected / Ghosted / Closed. Offer is not terminal (ADR-014). A role that returns after Done is a new opportunity record.

**Ghosted** (v1.1): Indicates no employer response despite confirmed application and active posting tracking. Distinct from Closed (user-initiated withdrawal or posting removed without tracking) and Rejected (explicit employer communication declining the candidate). Supports post-mortem analytics: ghost rate by company, time to ghost, posting duration before disappearance.

---

## 7. Configuration Keys

`pipelinepilot.config` stores settings and vault references, never credential values.

| Key | Required | Default | Description |
|---|---|---|---|
| `job_search_root` | Yes | — | Cloud-synced root containing the job-search database and opportunity folders. |
| `fit_threshold` | No | `0.65` | Minimum Job Fit Analyst score used for recommendation logic. |
| `follow_up_offset_days` | No | `14` | Days added to the application date before snapping to the next Monday. |
| `resume_path` | For Job Fit Analyst | — | Path to the resume supplied to the analysis workflow. |
| `context_skill_path` | No | — | Optional path to personal context used by the analysis workflow. |
| `ob_supabase_url` | For OpenBrain | — | OpenBrain Supabase project URL; not a secret. |
| `agent_vault_account` | For vault-backed features | — | Dashlane agent-vault login account; not a secret. |
| `ob_key_vault_id` | For OpenBrain | — | Dashlane item ID for the OpenBrain credential; not the credential value. |
| `anthropic_key_vault_id` | For Job Fit Analyst | — | Dashlane item ID for the Anthropic credential; not the credential value. |
| `dcli_path` | No | `dcli` from `PATH` | Optional full path to the Dashlane CLI executable. |
| `archive_root` | No | `001_ArchiveJobSearch`, sibling of `job_search_root` | Folder that receives opportunity folders when they enter a Done status (ADR-014). |

The retired plaintext keys `ob_supabase_key` and `anthropic_api_key` are not read. Runtime credentials are retrieved per operation and are not persisted by PipelinePilot.

---

## 8. Field Validation Rules

| Field | Rule |
|---|---|
| `company_name` | Required. Min 2 chars. Max 40 chars. Alphanumeric + spaces + hyphens only after sanitization. |
| `role_title` | Required. Min 2 chars. Max 40 chars. Same sanitization rules. |
| `folder_name` | Auto-generated. Max 60 chars combined. Preview required before creation. |
| `job_url` | Required at capture. Must be a valid URL string. |
| `fit_score` | Float 0.00–1.00. Null if analysis not yet run. |
| `fit_threshold` | Float 0.00–1.00. Default 0.65. Configurable in settings. |
| `source` | Must be from approved list. If "Other" selected, `source_other` required. |
| `status` | Must be from approved list. Filtering accepts single value or list of values (ADR-011). |
| `location_type` | Must be from approved list if populated. |
| `date_applied` | Cannot precede `date_discovered`. |
| `follow_up_date` | Cannot precede `date_applied` if both are set. Always a Monday. |
| `posting_status_log` | Machine-written only. Dates must be ISO 8601 (YYYY-MM-DD). |

---

*Data Dictionary v1.1 produced August 7, 2026. Updated for ADR-013 on October 12, 2026. Changes driven by ADR-009, ADR-010, ADR-011, and ADR-013. Incorporates field additions from migration 006 (pursuit tracker columns) that were previously undocumented.*
