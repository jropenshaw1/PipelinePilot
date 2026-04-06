# PipelinePilot

AI-assisted job search pipeline management — built the right way.

PipelinePilot is a filesystem-first job search pipeline manager that tracks opportunities, integrates AI role analysis, and maintains a complete lifecycle record for every application.

---

## The Problem

Active job searching across multiple boards generates a flood of alerts that quickly becomes unmanageable. Roles get missed. Applications go untracked. Follow-ups slip. Documents scatter. There is no system — just inbox entropy.

PipelinePilot solves that. It manages the complete lifecycle of every job opportunity from first alert through final close, integrates with an AI fit analysis skill to score and reason about each role, and keeps everything organized in a durable, filesystem-first structure that survives any database failure.

---

## How This Was Built

Documentation first. Code second. No exceptions.

Every architectural decision, requirement, use case, data field, and process flow was defined, documented, and committed to this repository before a single line of implementation code was written.

This is not a portfolio decoration. It is a production tool I depend on for my own job search — built with the same discipline I would apply to any enterprise system.

The engineering sequence:

1. Requirements interview (BABOK elicitation)
2. Project Charter
3. Use Case Specification
4. Data Dictionary
5. Software Requirements Specification (IEEE 830 / ISO/IEC 29148)
6. Process Flow (BPMN 2.0)
7. Architecture Decision Records
8. Definition of Done
── first commit of implementation code ──

The commit history reflects this. The timestamps are not edited.

---

## Documentation

All pre-code documentation is in `/docs`:

| Document | Standard |
|---|---|
| 01 — Project Charter | BABOK |
| 02 — Use Case Specification | UML / BABOK |
| 03 — Data Dictionary | ISO/IEC 11179 |
| 04 — Software Requirements Specification | IEEE 830 / ISO/IEC 29148 |
| 05 — Process Flow | BPMN 2.0 |
| 06 — Architecture Decision Records | Michael Nygard ADR |
| 07 — Definition of Done | — |

---

## Design Principles

PipelinePilot is built on a small set of engineering principles:

- **Filesystem as source of truth**
- **Deterministic rebuildability**
- **Explicit documentation before implementation**
- **Durable AI artifacts**
- **Separation of reasoning and orchestration**

---

## Architecture at a Glance

**Mantra:** Disciplined simplicity.

**Stack:** Python · CustomTkinter · SQLite · python-docx · pathlib · requests

Filesystem-first ensures the system remains durable, inspectable, and recoverable even if the database layer fails.

**Core design decisions:**

- **Filesystem is truth.** OneDrive folders are the source of record. SQLite is a derived, rebuildable index — losing the database is an inconvenience, not a disaster.
- **Folder name is the primary key.** `Company_Role` convention enforced at creation, previewed before commit, sanitized deterministically.
- **AI artifacts are documents.** Every Job Fit Analyst output is a durable filesystem artifact — inspectable, indexable, auditable. Not a transient API response.
- **Reference and index, never reinterpret.** PipelinePilot indexes fit analysis output. It never generates a competing AI reasoning artifact.
- **Idempotent recovery.** `pipelinepilot rebuild-index` reconstructs the entire SQLite database from the filesystem. Run it once or ten times — same result.
- **AI as capture interface.** Quick-fit triage happens conversationally through AI agents, with structured entries written to OpenBrain and imported into PipelinePilot. No manual form entry required.

Seven Architecture Decision Records document every significant choice, including what was rejected and why. See `/docs/06_architecture_decision_records.md`.

---

## Non-Goals

PipelinePilot intentionally does not attempt to solve every aspect of job searching.

The system is deliberately constrained to preserve simplicity and durability.

Non-goals include:

- **No job board scraping.** PipelinePilot assumes discovery happens elsewhere. It manages opportunities after discovery.
- **No AI reasoning inside PipelinePilot.** AI analysis is owned by the Job Fit Analyst system. PipelinePilot indexes outputs but never generates competing analysis.
- **No cloud service dependency.** The system runs entirely locally. Cloud storage is used only for file synchronization. OpenBrain integration is optional and one-directional (import only).
- **No complex workflow engine.** The lifecycle stages are intentionally simple and human-driven.

These constraints keep the system understandable, recoverable, and durable.

---

## System Capabilities

- **Opportunity capture** — creates `Company_Role` folder and blank job description document in one action
- **Quick-fit triage** — AI-powered rapid JD assessment across six dimensions (level, domain, location, degree/cert, culture, comp) with structured logging via OpenBrain
- **OpenBrain import** — one-click import of quick-fit-log entries from Supabase-backed AI memory into SQLite, with idempotent dedup
- **Quick-fit log viewer** — color-coded table of triage decisions with decision filtering and summary metrics
- **Fit analysis integration** — parses YAML front-matter from `fit_analysis.md` to index score, recommendation, strengths, and gaps without duplicating reasoning
- **Full lifecycle tracking** — Discovery → Capture → Fit Analysis → Application → Tracking → Close
- **Employer communication log** — running dated log per role; confirmation email paste capture
- **Action items and interview management** — per-role task list, interview date, pre/post notes
- **Opportunity scoring dashboard** — pipeline metrics by stage, average fit score, follow-ups due
- **Rebuild index** — deterministic, idempotent recovery from filesystem state

---

## Quick-Fit Log & OpenBrain Integration

PipelinePilot includes a lightweight triage layer for rapid JD evaluation. The workflow:

1. **Triage in conversation** — tell your AI agent "quick fit" with a pasted JD. The agent assesses fit across six dimensions and writes a structured `[quick-fit-log]` entry to OpenBrain.
2. **Import into PipelinePilot** — click "📥 Import from OB" in the sidebar. PipelinePilot fetches entries from Supabase, parses the structured blocks, deduplicates by thought ID, and inserts into the `quick_fit_log` SQLite table.
3. **Review in the Quick-Fit Log** — the "⚡ Quick-Fit Log" view shows all triage decisions with color-coded fit scores and decision badges, filterable by decision type.

This creates a complete triage-to-pipeline funnel: AI handles the capture, PipelinePilot handles the management. Roles scored as "pursue" can be promoted to the full pipeline for detailed fit analysis, resume optimization, and application tracking.

OpenBrain integration is optional. PipelinePilot functions fully without it — the quick-fit log table can also be populated through the existing Streamlit capture form (`quick_fit_capture.py`).

---

## Job Fit Analyst Integration

PipelinePilot integrates with the [Job Fit Analyst](https://github.com/jropenshaw1/job-fit-analyst) Claude skill — a separate six-agent system that produces four artifacts per analysis run, all saved directly to the role's folder:

- `fit_analysis.docx` — full Advocate/Auditor narrative for human review
- `fit_analysis.md` — YAML front-matter metadata for PipelinePilot indexing
- `Resume_Company_Role.docx` — tailored resume optimized for the specific role
- `CoverLetter_Company_Role.docx` — tailored cover letter

PipelinePilot parses `fit_analysis.md` to index the score, recommendation, strengths, and gaps. The resume and cover letter are stored in the folder and used directly by the user.

The two systems are cleanly separated. **Job Fit Analyst owns AI reasoning. PipelinePilot owns lifecycle tracking.**

---

## Installation

```bash
git clone https://github.com/jropenshaw1/pipelinepilot.git
cd pipelinepilot
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python pipelinepilot.py
```

Configure your job search root folder on first launch. PipelinePilot creates a `pipelinepilot.config` file in the application directory — no hardcoded paths, no registry entries.

> **Important:** PipelinePilot's filesystem-first architecture means your job search folder *is* your data. A local-only folder is not sufficient — your root folder must be inside a cloud-synced directory such as OneDrive, Google Drive, Dropbox, or equivalent. If the files are lost, no database backup can recover them. This is the one infrastructure requirement the tool cannot enforce for you.

### OpenBrain Integration (Optional)

To enable quick-fit log import from OpenBrain:

1. In PipelinePilot Settings, enter your Supabase URL and service role key
2. Use the "📥 Import from OB" button to pull quick-fit entries

Requires a [Supabase](https://supabase.com) project with the OpenBrain schema. See the OpenBrain MCP server documentation for setup details.

---

## On Building with AI in 2026

The pace of AI innovation is unlike anything I have seen in 28 years in technology. New tools arrive weekly. Functionality morphs daily. Staying relevant as a senior technology leader means more than reading about AI: it means building with it.

Leading in the AI era requires a new management model. AI agents are a new type of employee: they require clear requirements, defined scope, quality oversight, and disciplined direction. This project is built on that model.

I did not write the implementation code. I engineered the solution: requirements, architecture, design decisions, validation, and quality control. Senior leaders add the most value not by writing features, but by engineering systems and leading from the front.

My role is to create the conditions where great engineering happens: clear direction, sound architecture, disciplined decision-making, and a high quality bar. Implementation is a team sport. In 2026, one of those teammates is AI.

---

## Status

🟢 **v0.2.0** — Desktop application operational. Quick-fit triage pipeline live. OpenBrain import functional.

---

[Jonathan Openshaw](https://www.linkedin.com/in/jonathan-openshaw) · [Job Fit Analyst](https://github.com/jropenshaw1/job-fit-analyst)
