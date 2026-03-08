# PipelinePilot — Process Flow

**Version:** 1.0  
**Date:** March 7, 2026  
**Author:** Jonathan Openshaw  
**Standard:** BPMN 2.0 (narrative representation)  
**Status:** Approved

---

## 1. Overview

This document describes the end-to-end process flow for managing a job opportunity through PipelinePilot. It identifies all process steps, decision gates, validation points, and terminal outcomes.

The flow is organized into six stages matching the lifecycle defined in the Project Charter. Each stage includes: process steps, decision gates (◆), validation checks (✓), and stage exit criteria.

---

## 2. End-to-End Process Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: DISCOVERY                                                          │
│                                                                              │
│  [Job Alert Email Arrives]                                                   │
│       │                                                                      │
│       ▼                                                                      │
│  User opens alert → scans title, company, board alignment stats              │
│       │                                                                      │
│       ▼                                                                      │
│  User clicks through to full JD                                              │
│       │                                                                      │
│       ▼                                                                      │
│  User screens: degree requirement → location type → responsibilities         │
│       │                                                                      │
│       ▼                                                                      │
│  ◆ DECISION GATE: Pursue this role?                                         │
│       │                                                                      │
│    YES ──────────────────────────────────► STAGE 2: CAPTURE                │
│       │                                                                      │
│    NO  ──► Alert email deleted. No record created. END.                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: CAPTURE                                                            │
│                                                                              │
│  User opens PipelinePilot → selects "New Opportunity"                       │
│       │                                                                      │
│       ▼                                                                      │
│  PipelinePilot displays existing folders alphabetically                      │
│       │                                                                      │
│       ▼                                                                      │
│  ✓ VALIDATION: Does a folder already exist for this company + role?         │
│       │                                                                      │
│   DUPLICATE ──► User confirms duplicate. Discards alert. END.               │
│       │                                                                      │
│   NEW  ──► User enters company name and role title                          │
│       │                                                                      │
│       ▼                                                                      │
│  ✓ VALIDATION: Input sanitization                                           │
│       │    - Special characters stripped                                     │
│       │    - Spaces → underscores                                            │
│       │    - Max 60 chars combined                                           │
│       │                                                                      │
│       ▼                                                                      │
│  PipelinePilot previews folder_name                                          │
│       │                                                                      │
│  ◆ DECISION GATE: User confirms folder name?                                │
│       │                                                                      │
│    NO  ──► User edits name. Return to validation.                           │
│       │                                                                      │
│   YES  ──► PipelinePilot creates Company_Role folder on OneDrive            │
│       │                                                                      │
│       ▼                                                                      │
│  PipelinePilot creates blank jd.docx inside folder                          │
│       │                                                                      │
│       ▼                                                                      │
│  PipelinePilot creates DB record: status="Capturing", date_created=today    │
│       │                                                                      │
│       ▼                                                                      │
│  User opens jd.docx → pastes JD text, URL, contact details → saves          │
│       │                                                                      │
│       ▼                                                                      │
│  User sets: source, location_type, location_city, restrictions              │
│       │                                                                      │
│  STAGE 2 EXIT: folder created, jd.docx populated, record status="Capturing" │
│       │                                                                      │
│       ▼                                                                      │
│                          STAGE 3: FIT ANALYSIS                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: FIT ANALYSIS                                                       │
│                                                                              │
│  User invokes Job Fit Analyst skill (external — Claude Desktop/claude.ai)   │
│       │                                                                      │
│       ▼                                                                      │
│  User provides: master resume + jd.docx → Job Fit Analyst runs              │
│       │                                                                      │
│       ▼                                                                      │
│  Job Fit Analyst writes artifacts to Company_Role folder:                   │
│       - fit_analysis.md  (YAML front-matter + narrative)                    │
│       - fit_analysis.docx  (human-readable)                                 │
│       - Resume_CompanyName_RoleTitle.docx                                   │
│       - CoverLetter_CompanyName_RoleTitle.docx                              │
│       │                                                                      │
│       ▼                                                                      │
│  PipelinePilot detects fit_analysis.md                                      │
│       │                                                                      │
│  ✓ VALIDATION: YAML front-matter valid?                                     │
│       │                                                                      │
│   INVALID ──► Warning logged. User notified. Fit fields remain null.        │
│       │                                                                      │
│   VALID  ──► PipelinePilot parses YAML, updates DB record:                  │
│       │      fit_score, recommendation, top_strengths, top_gaps             │
│       │      status → "Analyzing"                                            │
│       │                                                                      │
│       ▼                                                                      │
│  User opens fit_analysis.docx and reviews Advocate/Auditor analysis         │
│       │                                                                      │
│  ◆ DECISION GATE: fit_score ≥ threshold AND User decides to proceed?       │
│       │                                                                      │
│   PASS ──► status → "Passed". decision_notes captured. Soft-archive. END.  │
│       │                                                                      │
│  PURSUE ──► status → "Pursuing"                                             │
│       │                                                                      │
│  STAGE 3 EXIT: fit analysis complete, artifacts saved, status="Pursuing"    │
│       │                                                                      │
│       ▼                                                                      │
│                          STAGE 4: APPLICATION                               │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 4: APPLICATION                                                        │
│                                                                              │
│  User reviews and refines tailored resume and cover letter                  │
│       │                                                                      │
│       ▼                                                                      │
│  User navigates to job_url and submits application                          │
│       │                                                                      │
│       ▼                                                                      │
│  User updates PipelinePilot record:                                         │
│       - status → "Applied"                                                   │
│       - date_applied → today                                                 │
│       - source confirmed                                                     │
│       - restrictions confirmed                                               │
│       │                                                                      │
│       ▼                                                                      │
│  PipelinePilot auto-sets follow_up_date = date_applied + 14 days            │
│       │                                                                      │
│       ▼                                                                      │
│  ◆ DECISION GATE: Confirmation email received?                              │
│       │                                                                      │
│   YES  ──► User pastes confirmation email text into confirmation_email field │
│       │                                                                      │
│    NO  ──► confirmation_email field left blank. follow_up_date still set.   │
│       │                                                                      │
│  STAGE 4 EXIT: status="Applied", date_applied set, follow_up_date set       │
│       │                                                                      │
│       ▼                                                                      │
│                          STAGE 5: TRACKING                                  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 5: TRACKING                                                           │
│                                                                              │
│  [Employer Communication Arrives — any type]                                │
│       │                                                                      │
│       ▼                                                                      │
│  User updates PipelinePilot record:                                         │
│       - last_communication_date → today                                     │
│       - last_communication_type → selected from list                        │
│       - communication_notes → dated entry appended                          │
│       │                                                                      │
│  ◆ BRANCH on communication_type:                                            │
│       │                                                                      │
│   ACKNOWLEDGMENT ──► status → "In Review". Continue monitoring.             │
│       │                                                                      │
│   PHONE SCREEN / INTERVIEW REQUEST ──►                                      │
│       - status → "Interviewing"                                              │
│       - User sets interview_date                                             │
│       - User adds action_items (research, prep, training)                   │
│       - User adds interview_notes before and after interview                │
│       │                                                                      │
│   REJECTION ──► status → "Rejected". Soft-archive. → STAGE 6              │
│       │                                                                      │
│   OFFER ──► status → "Offer". → STAGE 6                                    │
│       │                                                                      │
│   [follow_up_date reached with no response] ──►                             │
│       User decides: follow up manually or close role                        │
│       │                                                                      │
│  STAGE 5 EXIT: Terminal employer communication received                     │
│       │                                                                      │
│       ▼                                                                      │
│                          STAGE 6: CLOSE                                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 6: CLOSE                                                              │
│                                                                              │
│  User sets final status: Offer / Closed / Rejected                          │
│       │                                                                      │
│       ▼                                                                      │
│  User appends final communication_notes summary                             │
│       │                                                                      │
│       ▼                                                                      │
│  User sets archived = true                                                  │
│       │                                                                      │
│       ▼                                                                      │
│  Record remains in SQLite for reporting and pipeline metrics                │
│                                                                              │
│  END.                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Index Rebuild Process Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  REBUILD-INDEX PROCESS                                                       │
│                                                                              │
│  Trigger: User runs pipelinepilot rebuild-index (UI or CLI)                 │
│       │                                                                      │
│       ▼                                                                      │
│  PipelinePilot reads job search root folder from config                     │
│       │                                                                      │
│       ▼                                                                      │
│  Enumerate all subfolders in root                                           │
│       │                                                                      │
│  FOR EACH FOLDER:                                                            │
│       │                                                                      │
│       ▼                                                                      │
│  ✓ VALIDATION: Does folder match Company_Role naming convention?            │
│       │                                                                      │
│   NO  ──► Log warning. Skip folder. Continue.                               │
│       │                                                                      │
│   YES  ──► Check for jd.docx presence                                       │
│       │    - Missing: log warning, continue with partial record             │
│       │                                                                      │
│       ▼                                                                      │
│  Check for fit_analysis.md presence                                         │
│       │                                                                      │
│   NO  ──► fit fields remain null in record                                  │
│       │                                                                      │
│   YES  ──► Parse YAML front-matter                                          │
│       │                                                                      │
│  ✓ VALIDATION: YAML valid?                                                  │
│       │                                                                      │
│   INVALID ──► Log warning. Continue with null fit fields.                   │
│       │                                                                      │
│   VALID  ──► Extract: fit_score, recommendation, top_strengths, top_gaps   │
│       │                                                                      │
│       ▼                                                                      │
│  Normalize all extracted values                                             │
│       │                                                                      │
│       ▼                                                                      │
│  UPSERT record into SQLite (INSERT OR REPLACE)                              │
│  [Idempotent — safe to run any number of times]                             │
│       │                                                                      │
│  END FOLDER LOOP                                                             │
│       │                                                                      │
│       ▼                                                                      │
│  Emit summary report:                                                        │
│       - Folders scanned: N                                                   │
│       - Records indexed: N                                                   │
│       - Warnings: N                                                          │
│       - Failures: N                                                          │
│                                                                              │
│  END.                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Key Decision Gates Summary

| Gate | Stage | Question | Yes Path | No Path |
|---|---|---|---|---|
| DG-01 | Discovery | Pursue this role? | Capture | Discard alert |
| DG-02 | Capture | Duplicate folder exists? | Discard | Create new |
| DG-03 | Capture | Confirm folder name? | Create folder | Edit name |
| DG-04 | Fit Analysis | YAML front-matter valid? | Parse and index | Log warning |
| DG-05 | Fit Analysis | Proceed with application? | Pursuing | Passed |
| DG-06 | Application | Confirmation email received? | Paste text | Leave blank |
| DG-07 | Tracking | Communication type? | Branch by type | — |
| DG-08 | Rebuild | Folder matches convention? | Process | Skip with warning |
| DG-09 | Rebuild | YAML valid? | Extract fields | Null fit fields |

---

*This process flow was derived from a structured BABOK elicitation interview conducted March 7, 2026.*
