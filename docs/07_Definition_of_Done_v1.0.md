# PipelinePilot — Definition of Done

**Version:** 1.0  
**Date:** March 7, 2026  
**Author:** Jonathan Openshaw  
**Status:** Approved

---

## 1. Purpose

The Definition of Done (DoD) establishes the criteria that must be met before any feature, milestone, or the overall project can be considered complete. It prevents scope creep, ensures quality, and serves as a public signal of engineering discipline on GitHub.

This DoD applies at three levels: **Feature**, **Release**, and **Project**.

---

## 2. Feature-Level Definition of Done

A feature is **Done** when all of the following are true:

### Functional Completeness
- [ ] The feature implements all requirements specified in the SRS for that feature
- [ ] All defined use cases in the Use Case Specification that touch this feature behave as documented
- [ ] All decision gates and validation rules defined in the Process Flow are correctly enforced
- [ ] Edge cases and failure modes documented in the Use Case Specification are handled gracefully — no raw exceptions exposed to the User

### Code Quality
- [ ] Code follows PEP 8 Python style guidelines
- [ ] No hardcoded paths, thresholds, or user-specific values in source code — all externalized to config
- [ ] Functions and classes have docstrings
- [ ] No commented-out dead code committed
- [ ] All configuration values have documented defaults

### Testing
- [ ] Feature has been manually exercised against at least one real opportunity record
- [ ] YAML front-matter parsing logic (if touched) is covered by unit tests using known-good and known-bad fixture files
- [ ] `rebuild-index` tested against: empty database, partially populated database, fully populated database — all produce identical results

### Data Integrity
- [ ] No operation creates an orphaned database record without a corresponding filesystem folder
- [ ] No operation creates a filesystem folder without a corresponding database record
- [ ] `date_modified` is updated on every field change
- [ ] `date_created` is never modified after initial creation

### Configuration
- [ ] Feature respects the configured job search root folder path
- [ ] Feature respects the configured fit threshold
- [ ] Feature respects the configured follow-up offset (default 14 days)

### Documentation
- [ ] If a new field is added, the Data Dictionary is updated
- [ ] If a new use case is added, the Use Case Specification is updated
- [ ] If a new architectural decision is made, an ADR is written
- [ ] README reflects any new configuration requirements

---

## 3. Release-Level Definition of Done

A release is **Done** when all of the following are true:

### Functional Baseline
- [ ] All features targeted for this release meet the Feature-Level DoD
- [ ] Application launches as a native Windows desktop application — no terminal window, no manual background process
- [ ] Application handles OneDrive sync delays gracefully — no silent data loss
- [ ] `rebuild-index` completes successfully from a fresh filesystem state with no prior database

### End-to-End Validation
- [ ] At least 5 real job applications tracked end-to-end through the complete lifecycle: Discovery → Capture → Fit Analysis → Application → Tracking → Close
- [ ] Opportunity scoring dashboard displays accurate pipeline metrics for all tracked roles
- [ ] `rebuild-index` run after end-to-end test — result matches pre-rebuild state exactly

### Quality Gates
- [ ] No known data loss bugs open
- [ ] No known silent failure bugs open (failures that report success without completing the action)
- [ ] No sensitive data committed to the repository (API keys, credentials, personal data, test data with real contact info)

### GitHub Readiness
- [ ] `requirements.txt` is current and pinned
- [ ] `README.md` passes the 30-second CTO test (see Section 5)
- [ ] `.gitignore` excludes: SQLite database file, config file with local paths, `__pycache__`, `.env`, any files containing personal job search data
- [ ] All seven pre-code documentation artifacts are committed to `/docs`

---

## 4. Project-Level Definition of Done

The project is **Done** when all of the following are true:

### Documentation Set (Pre-Code Commitment)
- [ ] `docs/01_project_charter.md` — committed before first line of implementation code
- [ ] `docs/02_use_case_specification.md` — committed before first line of implementation code
- [ ] `docs/03_data_dictionary.md` — committed before first line of implementation code
- [ ] `docs/04_software_requirements_specification.md` — committed before first line of implementation code
- [ ] `docs/05_process_flow.md` — committed before first line of implementation code
- [ ] `docs/06_architecture_decision_records.md` — committed before first line of implementation code
- [ ] `docs/07_definition_of_done.md` — committed before first line of implementation code

### Functional Requirements
- [ ] All 32 functional requirements (FR-01 through FR-32) in the SRS are implemented and verified
- [ ] All 15 non-functional requirements (NFR-01 through NFR-15) are met
- [ ] All 10 use cases (UC-01 through UC-10) are implemented and exercised

### Production Use
- [ ] Tool is in active production use for Jonathan's 2026 job search
- [ ] At least 5 applications tracked end-to-end with no data integrity issues
- [ ] `rebuild-index` has been exercised at least once in production (not just test)

### LinkedIn and GitHub Publication
- [ ] GitHub repository published with complete documentation set committed before implementation history
- [ ] LinkedIn post published following approved narrative arc (see Project Charter Section 10)
- [ ] README passes the 30-second CTO test (see Section 5 below)
- [ ] GitHub commit history shows documentation committed before implementation — this is visible evidence of the discipline being claimed

---

## 5. The 30-Second CTO Test

The README must pass the following test: a CTO or VP Engineering who opens the repository and spends 30 seconds reading the README should immediately understand:

1. **What problem this solves** — stated in one sentence, in plain language
2. **That documentation came first** — the `/docs` folder is visible and linked in the README before any feature list
3. **That architectural decisions were made deliberately** — ADRs are mentioned and linked
4. **That this is a production tool, not a toy** — real use is stated explicitly
5. **The engineering leadership message** — requirements, architecture, design decisions, validation, quality control. The implementation is a team sport. In 2026, one of those team members is AI.

**The README must not lead with:**
- A feature list
- Installation instructions
- Screenshots
- Badges

**The README must lead with:**
- The problem statement
- The process signal (documentation before code)
- The leadership framing

---

## 6. What Done Is Not

To prevent scope creep and prevent the perfect from being the enemy of the good, the following are explicitly **not** required for Done:

- Perfect UI polish — functional and clean is sufficient
- Native Windows 11 design language compliance
- Automated test suite beyond YAML parsing unit tests
- CI/CD pipeline
- Code coverage metrics
- Multi-platform support (macOS, Linux, web, mobile)
- Gmail API integration
- Salary tracking of any kind
- Any feature not defined in the SRS v1.0

---

## 7. Governance

This Definition of Done may be amended by the Product Owner (Jonathan Openshaw) at any time. Amendments must be:
- Documented with a version increment
- Committed to the repository
- Applied retroactively to any open work in progress

No feature may be declared Done by an AI implementation partner without explicit confirmation from the Product Owner through the chat interface.

---

*This Definition of Done was produced as part of the pre-code documentation set for PipelinePilot, March 7, 2026. All seven documents were written before any implementation code was committed — this is the standard being claimed.*
