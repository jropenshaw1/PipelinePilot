# PipelinePilot

> *AI-assisted job search pipeline management — built the right way.*

---

## The Problem

Active job searching across multiple boards generates a flood of alerts that quickly becomes unmanageable. Roles get missed. Applications go untracked. Follow-ups slip. Documents scatter. There is no system — just inbox entropy.

PipelinePilot solves that. It manages the complete lifecycle of every job opportunity from first alert through final close, integrates with an AI fit analysis skill to score and reason about each role, and keeps everything organized in a durable, filesystem-first structure that survives any database failure.

---

## How This Was Built

**Documentation first. Code second. No exceptions.**

Every architectural decision, requirement, use case, data field, and process flow was defined, documented, and committed to this repository before a single line of implementation code was written.

This is not a portfolio decoration. It is a production tool I depend on for my own job search — built with the same discipline I would apply to any enterprise system.

The engineering sequence:

```
1. Requirements interview (BABOK elicitation)
2. Project Charter
3. Use Case Specification  
4. Data Dictionary
5. Software Requirements Specification (IEEE 830 / ISO/IEC 29148)
6. Process Flow (BPMN 2.0)
7. Architecture Decision Records
8. Definition of Done
── first commit of implementation code ──
```

The commit history reflects this. The timestamps are not edited.

---

## Documentation

All pre-code documentation is in [`/docs`](./docs):

| Document | Standard |
|---|---|
| [01 — Project Charter](./docs/01_project_charter.md) | BABOK |
| [02 — Use Case Specification](./docs/02_use_case_specification.md) | UML / BABOK |
| [03 — Data Dictionary](./docs/03_data_dictionary.md) | ISO/IEC 11179 |
| [04 — Software Requirements Specification](./docs/04_software_requirements_specification.md) | IEEE 830 / ISO/IEC 29148 |
| [05 — Process Flow](./docs/05_process_flow.md) | BPMN 2.0 |
| [06 — Architecture Decision Records](./docs/06_architecture_decision_records.md) | Michael Nygard ADR |
| [07 — Definition of Done](./docs/07_definition_of_done.md) | — |

---

## Architecture at a Glance

**Mantra:** Disciplined simplicity.

**Stack:** Python · CustomTkinter · SQLite · python-docx · pathlib

**Core design decisions:**

- **Filesystem is truth.** OneDrive folders are the source of record. SQLite is a derived, rebuildable index — losing the database is an inconvenience, not a disaster.
- **Folder name is the primary key.** `Company_Role` convention enforced at creation, previewed before commit, sanitized deterministically.
- **AI artifacts are documents.** Every Job Fit Analyst output is a durable filesystem artifact — inspectable, indexable, auditable. Not a transient API response.
- **Reference and index, never reinterpret.** PipelinePilot indexes fit analysis output. It never generates a competing AI reasoning artifact.
- **Idempotent recovery.** `pipelinepilot rebuild-index` reconstructs the entire SQLite database from the filesystem. Run it once or ten times — same result.

Seven Architecture Decision Records document every significant choice, including what was rejected and why. See [`/docs/06_architecture_decision_records.md`](./docs/06_architecture_decision_records.md).

---

## Key Features

- **Opportunity capture** — creates `Company_Role` folder and blank job description document in one action
- **Fit analysis integration** — parses YAML front-matter from `fit_analysis.md` to index score, recommendation, strengths, and gaps without duplicating reasoning
- **Full lifecycle tracking** — Discovery → Capture → Fit Analysis → Application → Tracking → Close
- **Employer communication log** — running dated log per role; confirmation email paste capture
- **Action items and interview management** — per-role task list, interview date, pre/post notes
- **Opportunity scoring dashboard** — pipeline metrics by stage, average fit score, follow-ups due
- **Rebuild index** — deterministic, idempotent recovery from filesystem state

---

## Job Fit Analyst Integration

PipelinePilot integrates with the [Job Fit Analyst](https://github.com/jropenshaw1/job-fit-analyst) Claude skill — a separate six-agent system that produces four artifacts per analysis run, all saved directly to the role's folder:

- `fit_analysis.docx` — full Advocate/Auditor narrative for human review
- `fit_analysis.md` — YAML front-matter metadata for PipelinePilot indexing
- `Resume_Company_Role.docx` — tailored resume optimized for the specific role
- `CoverLetter_Company_Role.docx` — tailored cover letter

PipelinePilot parses `fit_analysis.md` to index the score, recommendation, strengths, and gaps. The resume and cover letter are stored in the folder and used directly by the User. The two systems are cleanly separated. Job Fit Analyst owns AI reasoning. PipelinePilot owns lifecycle tracking.

---

## Installation

```bash
git clone https://github.com/jropenshaw1/pipelinepilot.git
cd pipelinepilot
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python pipelinepilot.py
```

Configure your job search root folder on first launch. PipelinePilot creates a `pipelinepilot.config` file in the application directory — no hardcoded paths, no registry entries.

> **Important:** PipelinePilot's filesystem-first architecture means your job search folder *is* your data. A local-only folder is not sufficient — your root folder must be inside a cloud-synced directory such as OneDrive, Google Drive, Dropbox, or equivalent. If the files are lost, no database backup can recover them. This is the one infrastructure requirement the tool cannot enforce for you.

---

## On Building with AI in 2026

The pace of AI innovation is unlike anything I have seen in 28 years in technology. New tools arrive weekly. Functionality morphs daily. Staying relevant as a senior technology leader means more than reading about AI: it means building with it.

Leading in the AI era requires a new management model. AI agents are a new type of employee: they require clear requirements, defined scope, quality oversight, and disciplined direction.

This project is built on that model. I did not write the implementation code. I engineered the solution: requirements, architecture, design decisions, validation, and quality control.

Senior leaders add the most value not by writing features, but by engineering systems and leading from the front. My role is to create the conditions where great engineering happens: clear direction, sound architecture, disciplined decision-making, and a high quality bar. Implementation is a team sport. In 2026, one of those teammates is AI.

---

## Status

🟡 **Pre-implementation** — documentation set complete, implementation in progress.

---

*Jonathan Openshaw · [LinkedIn](https://linkedin.com/in/jonathan-openshaw) · [Job Fit Analyst](https://github.com/jropenshaw1/job-fit-analyst)*
