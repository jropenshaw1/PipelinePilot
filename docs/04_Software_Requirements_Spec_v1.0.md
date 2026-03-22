# PipelinePilot — Software Requirements Specification (SRS)

**Version:** 1.0  
**Date:** March 7, 2026  
**Author:** Jonathan Openshaw  
**Standard:** IEEE 830 / ISO/IEC 29148  
**Status:** Approved

---

## 1. Introduction

### 1.1 Purpose
This document defines the functional and non-functional requirements for PipelinePilot — an AI-assisted job search pipeline management tool. It serves as the authoritative requirements reference for implementation, testing, and future enhancement.

### 1.2 Scope
PipelinePilot manages the complete lifecycle of job opportunities from initial discovery through close. It integrates with the Job Fit Analyst Claude skill as a first-class external dependency and uses a filesystem-first storage architecture with SQLite as a derived index.

### 1.3 Definitions
- **Opportunity:** A single job role at a single company being tracked through the lifecycle
- **Artifact:** A document file produced by Job Fit Analyst and stored in the role folder
- **Index:** The SQLite database — derived from the filesystem, always rebuildable
- **Source of Truth:** The OneDrive filesystem — the record that is trusted when conflicts arise
- **Fit Threshold:** The configurable fit score percentage below which the tool suggests (but does not enforce) passing on a role

### 1.4 References
- `01_project_charter.md`
- `02_use_case_specification.md`
- `03_data_dictionary.md`
- `06_architecture_decision_records.md`

---

## 2. Overall Description

### 2.1 Product Perspective
PipelinePilot is a standalone Windows desktop application. It does not require internet connectivity for core functionality. It integrates with:
- **OneDrive:** For filesystem storage (user-managed, not API-controlled)
- **Job Fit Analyst skill:** External Claude skill invoked by the User independently
- **SQLite:** Local database file co-located with or near the job search root folder

### 2.2 Product Functions (Summary)
- Opportunity discovery triage and capture
- Automated folder and document creation
- Job Fit Analyst integration via filesystem artifact detection
- Full lifecycle status tracking
- Employer communication logging
- Action item and interview management
- Opportunity scoring dashboard
- Deterministic index rebuild from filesystem

### 2.3 User Characteristics
Single user. Technology executive with 28 years of IT experience. Not a developer. Expects a professional desktop application experience — not a browser tab, not a terminal.

### 2.4 Constraints
- Windows desktop only (no macOS, no web, no mobile)
- No internet connectivity required for core operations
- No multi-user support
- No salary tracking
- No automated email processing
- Fit threshold is a suggestion, not an enforced gate
- No shiny-object engineering — every dependency must justify its inclusion

### 2.5 Assumptions
- OneDrive is installed, authenticated, and syncing on the User's machine
- Job Fit Analyst skill is maintained as a separate codebase and invoked externally
- The User is responsible for manually running Job Fit Analyst and saving artifacts to the correct folder
- `fit_analysis.md` YAML front-matter schema is maintained by the Job Fit Analyst skill owner

---

## 3. Functional Requirements

### 3.1 Opportunity Management

**FR-01:** The system shall allow the User to create a new opportunity record by entering company name and role title.

**FR-02:** Before creating the folder, the system shall display all existing `Company_Role` folders in the job search root, sorted alphabetically, so the User can confirm no duplicate exists.

**FR-03:** The system shall sanitize company name and role title inputs according to the rules defined in the Data Dictionary before generating the folder name.

**FR-04:** The system shall display the proposed `folder_name` for User confirmation before creating any filesystem objects.

**FR-05:** Upon confirmation, the system shall create the `Company_Role` folder on OneDrive and create a blank `JD_Company_Role.docx` inside it. The filename is derived directly as `JD_` + `folder_name` + `.docx` — no additional sanitization required since folder_name is already clean.

**FR-06:** The system shall create a database record simultaneously with folder creation, with `status` = "Capturing" and `date_created` auto-set.

**FR-07:** The system shall allow the User to view all opportunity records in a sortable, filterable list view.

**FR-08:** The system shall allow the User to select any record and view and edit all fields on a single detail screen without navigating to a separate edit view.

**FR-09:** File reference fields shall display the current filename and provide a Browse button to navigate the local filesystem.

**FR-10:** The system shall auto-update `date_modified` on any field change.

**FR-11:** The system shall support soft-delete via the `archived` flag. Archived records shall remain queryable and visible when filters include archived records.

---

### 3.2 Fit Analysis Integration

**FR-12:** The system shall monitor the `Company_Role` folder for the presence of `fit_analysis.md`.

**FR-13:** When `fit_analysis.md` is detected, the system shall parse the YAML front-matter block and update the opportunity record with: `fit_score`, `fit_threshold`, `recommendation`, `decision_override`, `top_strengths`, `top_gaps`.

**FR-14:** The system shall display the configured fit threshold and flag opportunities where `fit_score` is below threshold with a visual indicator. This indicator is informational only — it shall not prevent the User from setting status to "Pursuing" or "Applied".

**FR-15:** If `fit_analysis.md` is present but YAML front-matter is missing or malformed, the system shall log a warning, notify the User, and leave fit fields null rather than erroring.

**FR-16:** The system shall never generate its own fit analysis or reasoning content. It shall only index what Job Fit Analyst produces.

---

### 3.3 Status and Lifecycle Management

**FR-17:** The system shall enforce that `status` is always one of the approved values: New / Capturing / Analyzing / Pursuing / Passed / Applied / In Review / Interviewing / Offer / Closed / Rejected.

**FR-18:** When `status` is set to "Applied", the system shall auto-set `follow_up_date` to `date_applied` + 14 days if `follow_up_date` is not already set.

**FR-19:** The system shall support all fields in the Employer Communications group and allow the User to append dated entries to `communication_notes`.

**FR-20:** When `last_communication_type` is set to "Interview Request", the system shall prompt the User to set `interview_date`.

---

### 3.4 Confirmation Email Capture

**FR-21:** The system shall provide a scrollable text area on the opportunity detail screen where the User can paste the full text of a confirmation email.

**FR-22:** This field shall have no character limit for practical purposes (SQLite TEXT type).

---

### 3.5 Dashboard

**FR-23:** The system shall provide an opportunity scoring dashboard displaying the following metrics derived from the SQLite index:
- Total opportunities (all statuses)
- By status: Captured, Analyzing, Pursuing, Applied, Interviewing, Offer, Closed/Rejected/Passed
- Fit analyses completed
- Average fit score (across all analyzed opportunities)
- Opportunities above fit threshold
- Follow-ups due today or overdue

**FR-24:** Dashboard metrics shall refresh on demand and on application launch.

---

### 3.6 Index Rebuild

**FR-25:** The system shall provide a `rebuild-index` command (accessible from the UI and/or CLI) that reconstructs the SQLite database entirely from the filesystem.

**FR-26:** The rebuild process shall be deterministic and idempotent — running it any number of times shall produce identical results.

**FR-27:** The rebuild process shall emit a summary report: folders scanned / records indexed / warnings / failures.

**FR-28:** The rebuild process shall use upsert operations (INSERT OR REPLACE) to ensure idempotency.

**FR-29:** Folders that do not match the `Company_Role` naming convention shall be logged as warnings and skipped, not treated as errors.

---

### 3.7 Configuration

**FR-30:** The system shall store the job search root folder path in a configuration file, not hardcoded.

**FR-31:** The fit threshold shall be configurable by the User in application settings. Default: 0.65.

**FR-32:** The `follow_up_date` auto-offset (default 14 days) shall be configurable in application settings.

---

## 4. Non-Functional Requirements

### 4.1 Usability

**NFR-01:** The application shall launch as a native Windows desktop application with a standard taskbar icon — no manual background process required, no terminal window visible to the User.

**NFR-02:** All CRUD operations on opportunity records shall complete within 2 seconds under normal OneDrive sync conditions.

**NFR-03:** The list view shall support sort and filter on all available fields without perceptible lag for up to 500 records.

**NFR-04:** The application shall provide clear, human-readable error messages for all failure conditions — no raw stack traces exposed to the User.

### 4.2 Reliability

**NFR-05:** Loss of the SQLite database shall result in zero permanent data loss. The filesystem is the source of truth; the database is rebuildable.

**NFR-05a:** The job search root folder must be located inside a cloud-synced directory (OneDrive, Google Drive, Dropbox, or equivalent). A local-only folder does not satisfy the filesystem-as-truth architecture. PipelinePilot cannot enforce this requirement programmatically but shall display a warning on first launch if the configured root path does not appear to reside within a known cloud-sync location.

**NFR-06:** The rebuild-index command shall complete successfully on a clean filesystem with no prior database present.

**NFR-07:** The application shall handle cloud sync delays gracefully (OneDrive, Google Drive, Dropbox, or equivalent) — folder creation operations shall confirm filesystem success before creating the database record.

### 4.3 Maintainability

**NFR-08:** The codebase shall follow PEP 8 Python style guidelines.

**NFR-09:** All configuration values shall be externalized to a config file — no hardcoded paths, thresholds, or user-specific values in source code.

**NFR-10:** The Job Fit Analyst integration shall be isolated in a dedicated module with a documented interface contract, so changes to Job Fit Analyst output format require changes only in that module.

**NFR-11:** The YAML front-matter parsing logic shall be covered by unit tests with known-good and known-bad fixture files.

### 4.4 Portability

**NFR-12:** The application shall run on Windows 10 and Windows 11.

**NFR-13:** The application shall be installable via a standard Python virtual environment and a `requirements.txt` file with no system-level dependencies beyond Python 3.10+.

### 4.5 Security

**NFR-14:** No sensitive data (API keys, credentials) shall be stored in the source code or committed to the GitHub repository.

**NFR-15:** The SQLite database shall be stored locally on the User's machine, not transmitted to any external service.

---

## 5. Interface Requirements

### 5.1 User Interface
- Native Windows desktop GUI using Python + CustomTkinter
- List view: sortable, filterable, all fields available as columns
- Detail view: all fields visible and editable on a single screen
- Dashboard view: pipeline metrics summary
- Settings screen: configurable threshold, follow-up offset, root folder path

### 5.2 Filesystem Interface
- Read/write access to OneDrive job search root folder
- Folder creation, document creation via `pathlib` and `python-docx`
- `fit_analysis.md` monitoring via filesystem polling or event detection

### 5.3 External Integration Interface
- Job Fit Analyst: filesystem-based (no API call from PipelinePilot to Job Fit Analyst)
- SQLite: via Python `sqlite3` standard library

---

## 6. Out of Scope (Explicit Exclusions)

The following are explicitly out of scope for v1.0 and shall not be implemented:

- Gmail API or any automated email reading/processing
- Browser automation or job board scraping
- Multi-user support or authentication
- Cloud hosting, SaaS deployment, or web interface
- Salary tracking of any kind
- AI reasoning generation within PipelinePilot (all AI output comes from Job Fit Analyst)
- Vector databases or semantic search
- Automated calendar integration
- Mobile or macOS support

---

*This SRS was produced following IEEE 830 / ISO/IEC 29148 standards from a structured BABOK elicitation interview conducted March 7, 2026.*
