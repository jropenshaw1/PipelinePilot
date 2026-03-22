# PipelinePilot — Use Case Specification

**Version:** 1.0  
**Date:** March 7, 2026  
**Author:** Jonathan Openshaw  
**Standard:** UML Use Case / BABOK Process Flow  
**Status:** Approved

---

## 1. Actors

| Actor | Description |
|---|---|
| **User** | Jonathan Openshaw — the sole operator of PipelinePilot |
| **Job Fit Analyst** | External Claude skill; invoked by the User, writes artifacts to the filesystem |
| **Filesystem (OneDrive)** | Passive storage actor; source of truth for all artifacts |
| **SQLite Index** | Derived data store; rebuilt from filesystem on demand |

---

## 2. Use Case Overview

| ID | Use Case | Actor | Trigger |
|---|---|---|---|
| UC-01 | Discover and triage a job alert | User | Alert email arrives from job board |
| UC-02 | Capture a new opportunity | User | Decision to pursue a role |
| UC-03 | Run fit analysis | User + Job Fit Analyst | Role captured and ready to analyze |
| UC-04 | Apply for a role | User | Fit score ≥ 65% (suggested) and User decides to proceed |
| UC-05 | Record employer communication | User | Inbound email from employer |
| UC-06 | Manage follow-up and action items | User | Ongoing tracking need |
| UC-07 | Close a role | User | Offer accepted, rejection received, or role abandoned |
| UC-08 | Rebuild the SQLite index | User | Database lost, corrupted, or drifted from filesystem |
| UC-09 | View opportunity dashboard | User | User wants pipeline summary metrics |
| UC-10 | Update an existing record | User | Any field change needed on an existing opportunity |

---

## 3. Use Case Detail

---

### UC-01: Discover and Triage a Job Alert

**Actor:** User  
**Trigger:** Job alert email arrives from a job board  
**Precondition:** User has active alert subscriptions on one or more job boards

**Happy Path:**
1. User opens alert email and scans job title, company name, and any alignment stats provided by the board
2. User clicks through to the full job description
3. User scans for degree requirements
4. User determines location / remote / hybrid / onsite
5. User self-assesses whether stated responsibilities are worth pursuing
6. **Decision gate:** Pursue → UC-02 | Pass → alert email deleted, no record created

**Failure Modes:**
- Job posting link is broken or expired → User notes this, discards alert
- Duplicate role already exists in PipelinePilot → User confirms duplicate, discards alert

**Post-condition:** Either a new opportunity record is initiated (UC-02) or the alert is discarded with no record created.

---

### UC-02: Capture a New Opportunity

**Actor:** User  
**Trigger:** User decides to pursue a role following UC-01  
**Precondition:** User has decided to pursue the role

**Happy Path:**
1. User opens PipelinePilot and selects "New Opportunity"
2. PipelinePilot displays existing `Company_Role` folders alphabetically
3. User confirms no duplicate folder exists for this company and role
4. User enters company name and role title
5. PipelinePilot validates input: sanitizes special characters, enforces max length, previews generated folder name
6. User confirms folder name
7. PipelinePilot creates `Company_Role` folder on OneDrive
8. PipelinePilot creates a blank `JD_Company_Role.docx` inside the folder (= `JD_` + `folder_name` + `.docx` — no additional sanitization)
9. User opens `JD_Company_Role.docx`, pastes job description, URL, and contact details, saves
10. PipelinePilot creates the database record with status = "Captured", date_discovered auto-set
11. User sets source, location type, location city, and any restrictions (degree required / culture concern / relocation required)

**Validation Rules:**
- `company_name`: alphanumeric + spaces + limited special chars; ampersands → stripped; commas → stripped
- `role_title`: same rules
- `folder_name` = `CompanyName_RoleTitle` with spaces → underscores, max 60 characters combined
- Preview shown before folder creation; User must confirm

**Failure Modes:**
- Folder name exceeds max length → User prompted to shorten company or role name
- Folder already exists with identical name → User warned, no duplicate created
- OneDrive path not accessible → Error displayed, User directed to check connection

**Post-condition:** `Company_Role` folder exists on OneDrive, `JD_Company_Role.docx` created, database record exists with status = "Captured".

---

### UC-03: Run Fit Analysis

**Actor:** User + Job Fit Analyst  
**Trigger:** User is ready to analyze a captured role  
**Precondition:** `Company_Role` folder exists, `jd.docx` contains job description

**Happy Path:**
1. User selects opportunity record in PipelinePilot and chooses "Run Fit Analysis"
2. User opens Job Fit Analyst skill (external — Claude Desktop or claude.ai)
3. User provides master resume (V13 or current) and `jd.docx` to Job Fit Analyst
4. Job Fit Analyst produces four artifacts and saves to `Company_Role` folder:
   - `fit_analysis.md` (YAML front-matter + narrative — PipelinePilot index source)
   - `fit_analysis.docx` (human-readable — review and recruiter demo)
   - `Resume_CompanyName_RoleTitle.docx` (tailored resume)
   - `CoverLetter_CompanyName_RoleTitle.docx` (cover letter)
5. PipelinePilot detects new `fit_analysis.md`, parses YAML front-matter, updates record:
   - `fit_score` populated
   - `status` → "Analyzed"
6. User opens `fit_analysis.docx` and reviews Advocate/Auditor analysis and gap detail
7. **Decision gate:** fit_score ≥ 65% threshold (suggested, not enforced) AND User decides to proceed → UC-04 | User decides to pass → status → "Passed", decision_notes captured

**YAML Front-Matter Fields Parsed by PipelinePilot:**
```yaml
---
company: Acme Corp
role: Director, Cloud Infrastructure
job_url: https://example.com/job123
analysis_date: 2026-03-07
analysis_tool: job-fit-analyst
analysis_version: 1.0
fit_score: 0.75
fit_threshold: 0.65
recommendation: pursue
decision_override: false
top_strengths:
  - Cloud FinOps leadership
  - Vendor management governance
  - Enterprise infrastructure strategy
top_gaps:
  - SaaS product operations
  - Startup scaling experience
---
```

**Failure Modes:**
- `fit_analysis.md` missing or malformed YAML → PipelinePilot logs warning, record not auto-updated, User notified
- Fit score below threshold → Tool flags, User may override with decision_notes

**Post-condition:** `fit_analysis.md` and `fit_analysis.docx` exist in folder, record updated with fit score and status.

---

### UC-04: Apply for a Role

**Actor:** User  
**Trigger:** User decides to submit an application  
**Precondition:** Fit analysis complete, artifacts reviewed, User decides to proceed

**Happy Path:**
1. User reviews tailored resume and cover letter, makes any final edits
2. User navigates to job posting URL (from `jd.docx` or `job_url` field)
3. User completes and submits the application on the employer's site
4. User returns to PipelinePilot and updates record:
   - `status` → "Applied"
   - `date_applied` → today
   - `source` confirmed
   - `degree_required` restriction confirmed or cleared
5. User receives confirmation email from employer
6. User copies and pastes confirmation email text into `confirmation_email` field
7. PipelinePilot saves record, sets `follow_up_date` to 14 days from `date_applied`

**Failure Modes:**
- Job posting URL returns 404 → User notes in decision_notes, attempts direct application or LinkedIn
- No confirmation email received → `confirmation_email` field left blank, follow-up date still set

**Post-condition:** Record status = "Applied", date_applied set, confirmation email stored, follow-up date set.

---

### UC-05: Record Employer Communication

**Actor:** User  
**Trigger:** Inbound email received from employer  
**Precondition:** Application submitted (status = "Applied" or later)

**Happy Path:**
1. User receives email from employer
2. User opens PipelinePilot and selects the relevant opportunity record
3. User updates:
   - `last_communication_date` → today
   - `last_communication_type` → Acknowledgment / Rejection / Phone Screen Request / Interview Request / Offer / Other
   - `communication_notes` → appends summary of communication with date prefix
4. If communication_type = "Interview Request":
   - User sets `interview_date`
   - User adds `action_items` for interview preparation
   - `status` → "Interviewing"
5. If communication_type = "Rejection":
   - `status` → "Rejected"
   - Role soft-archived via `archived` flag

**Failure Modes:**
- Ambiguous communication type → User selects "Other" and notes detail in communication_notes

**Post-condition:** Communication logged, status updated, interview date set if applicable.

---

### UC-06: Manage Follow-up and Action Items

**Actor:** User  
**Trigger:** User needs to add, review, or complete action items for a role  
**Precondition:** Opportunity record exists

**Happy Path:**
1. User selects opportunity record
2. User views or edits `action_items` free-text field
3. User updates `follow_up_date` if needed
4. User adds interview prep notes to `interview_notes`

**Post-condition:** Action items and follow-up date current.

---

### UC-07: Close a Role

**Actor:** User  
**Trigger:** Role reaches a terminal state  
**Precondition:** Active opportunity record exists

**Happy Path:**
1. User selects opportunity record
2. User sets `status` to one of: Offer / Closed / Rejected
3. User adds final `communication_notes` summary
4. User sets `archived` = true (soft delete — record remains queryable)

**Post-condition:** Record closed, archived flag set, record remains in database for reporting.

---

### UC-08: Rebuild the SQLite Index

**Actor:** User  
**Trigger:** Database lost, corrupted, out of sync, or fresh installation  
**Precondition:** OneDrive `Company_Role` folder structure intact

**Happy Path:**
1. User runs `pipelinepilot rebuild-index` command
2. PipelinePilot enumerates all `Company_Role` folders under job search root
3. For each folder:
   a. Validates folder naming convention
   b. Checks for expected documents (`JD_Company_Role.docx`, `fit_analysis.md`)
   c. Parses YAML front-matter from `fit_analysis.md` if present
   d. Normalizes values
   e. Upserts SQLite record (idempotent — safe to run multiple times)
   f. Logs warnings for missing or invalid artifacts
4. Emits summary report: roles scanned / indexed / warnings / failures

**Design Constraint:** Command must be deterministic and idempotent. Running it once or ten times produces identical results.

**Failure Modes:**
- Folder naming does not match `Company_Role` convention → logged as warning, skipped
- `fit_analysis.md` missing → record created with fit_score null, warning logged
- YAML front-matter malformed → warning logged, raw parsing attempted

**Post-condition:** SQLite index reflects current filesystem state.

---

### UC-09: View Opportunity Dashboard

**Actor:** User  
**Trigger:** User wants a pipeline summary  
**Precondition:** SQLite index populated

**Dashboard Metrics:**
- Roles Discovered (total records)
- Roles Captured (status ≠ Discarded)
- Fit Analyses Run
- Applications Submitted
- Active Interviews
- Offers
- Closed / Rejected
- Average Fit Score across all analyzed roles
- Roles Above Threshold (fit_score ≥ configurable threshold)
- Pipeline stage distribution view

**Post-condition:** Dashboard displays current metrics from SQLite.

---

### UC-10: Update an Existing Record

**Actor:** User  
**Trigger:** Any field on an existing opportunity needs updating  
**Precondition:** Record exists

**Happy Path:**
1. User selects record from list view
2. All fields visible and editable on single detail screen (no separate edit screen)
3. File attachment fields show current filename with a Browse button to navigate to the file
4. User edits any field and saves
5. `date_modified` auto-updated

**Post-condition:** Record updated, date_modified current.

---

*This specification was derived from a structured BABOK elicitation interview conducted March 7, 2026.*
