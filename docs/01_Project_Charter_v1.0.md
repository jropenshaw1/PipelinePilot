# PipelinePilot — Project Charter

**Version:** 1.0  
**Date:** March 7, 2026  
**Author:** Jonathan Openshaw  
**Status:** Approved

---

## 1. Project Name

**PipelinePilot**

AI-assisted job search orchestration system that aggregates alerts, extracts signal from noise, prioritizes opportunities, and manages the full job search pipeline.

---

## 2. Problem Statement

Active job searching across multiple job boards (LinkedIn, Indeed, Monster, Lensa, Dice, Ladders, and others) generates a high volume of alert emails that quickly becomes unmanageable without a structured system. The specific pain points are:

- No way to determine which incoming leads are appropriate, new, or duplicated across boards
- No structured record of which roles have been applied for, passed on, or are pending a decision
- No reliable way to return to a specific job posting days or weeks after initial discovery
- No centralized place to track employer responses, interview scheduling, or follow-up actions
- No management layer for master and customized resume versions or cover letters
- No per-role action item tracking for research, training, or interview preparation
- Inbox accumulates processed alerts with no systematic cleanup workflow

---

## 3. Project Goals

### Primary Goal — Learning
Build and demonstrate real software engineering discipline in the AI era: proper requirements definition, architecture, design decisions, validation, and quality control — all documented before a single line of code is written. The process is as important as the output.

### Secondary Goal — Personal Utility
Produce a production-grade tool that genuinely optimizes the job search process, reduces friction, and ensures no high-quality opportunity is missed.

### Tertiary Goal — Public Showcase
Publish a clean, documented, well-structured codebase on GitHub and LinkedIn that represents the quality of engineering leadership thinking — not implementation for its own sake, but disciplined problem-solving with AI as an implementation partner.

---

## 4. Target Audience

**Primary user:** Jonathan Openshaw — the tool is designed for and by the person who feels the problem directly.

**GitHub audience (in order of priority):**
1. Recruiter — must stop scrolling within 5 seconds
2. Hiring Manager — senior executive who recognizes engineering discipline
3. Technical Reviewer (CTO / VP Engineering) — doing due diligence on a candidate

The tool is not multi-tenant, does not require authentication, and is not designed for monetization. However, the codebase is structured as if it could be extended — clean separation of concerns, no hardcoded paths buried in logic, configuration-driven where appropriate.

---

## 5. Scope

### In Scope
- Job opportunity lifecycle management from discovery through close
- Filesystem-based artifact storage (OneDrive) with SQLite as a derived, rebuildable index
- Integration with the Job Fit Analyst Claude skill (first-class, separate codebase)
- Automated folder and document creation following the `Company_Role` naming convention
- Per-role tracking: status, contacts, communications, action items, interview notes
- Opportunity scoring dashboard derived from SQLite metrics
- Deterministic index rebuild command (`pipelinepilot rebuild-index`)
- fit_analysis.md with YAML front-matter as the machine-parseable integration artifact
- fit_analysis.docx as the human-readable companion artifact

### Out of Scope
- Multi-user / multi-tenant support
- Cloud hosting or SaaS deployment
- Salary tracking of any kind
- Gmail API integration or automated email processing
- Browser scraping or clipboard automation
- Monetization of any kind

---

## 6. Design Principles

1. **Disciplined simplicity (KISS)** — every technology choice, every feature, every pattern is tested against: *does this add genuine value or is it just interesting?*
2. **Filesystem is truth** — OneDrive folder structure is the source of record. SQLite is a derived index, always rebuildable from the filesystem.
3. **AI artifacts are documents** — every output from Job Fit Analyst is a durable filesystem artifact, not a transient API response.
4. **Reference, don't reinterpret** — PipelinePilot indexes Job Fit Analyst output; it never generates a second parallel reasoning artifact for the same role.
5. **No shiny object engineering** — technology is chosen because it solves the problem, not because it is new or interesting.

---

## 7. Architecture Decisions (Summary)

Full detail in `06_architecture_decision_records.md`.

| Decision | Choice | Rationale |
|---|---|---|
| UI Framework | Python + CustomTkinter | Native Windows desktop app, no background server process, no browser dependency |
| Storage — Documents | OneDrive filesystem | Automatic backup, user-controlled, survives database loss |
| Storage — Structured Data | SQLite | Single-file, serverless, backs up with OneDrive automatically |
| Fit Analysis Integration | YAML front-matter in fit_analysis.md | Machine-parseable header, human-readable narrative body, no duplicate artifacts |
| Source of Truth | Filesystem | Database is derived and rebuildable; filesystem is what you grieve if lost |
| Fit Analysis Output | .docx + .md (both) | .docx for human review and demos; .md for PipelinePilot indexing |

---

## 8. Success Criteria

- [ ] All seven pre-code documentation artifacts completed and committed to GitHub before implementation begins
- [ ] Application lifecycle tracked end-to-end for at least 5 real job applications
- [ ] `pipelinepilot rebuild-index` successfully recreates SQLite from filesystem with no data loss
- [ ] Opportunity scoring dashboard displays accurate pipeline metrics
- [ ] Tool launches as a native Windows desktop application with no manual background process required
- [ ] GitHub README passes the 30-second CTO test: process and discipline visible before features
- [ ] LinkedIn post published with honest narrative about AI-era engineering leadership

---

## 9. Stakeholders

| Role | Person |
|---|---|
| Product Owner / Engineer | Jonathan Openshaw |
| AI Implementation Partner | Claude (Anthropic) / ChatGPT (OpenAI) |
| External Reviewer | GitHub / LinkedIn audience |

---

## 10. LinkedIn Narrative (Approved)

> *"The pace of AI innovation is unlike anything I have seen in 28 years in technology. New tools arrive weekly. Functionality morphs daily. Staying relevant as a senior technology leader in 2026 means more than reading about AI — it means building with it.*
>
> *Leading in the AI era requires a new management model. AI agents are a new type of employee — they require clear requirements, defined scope, quality oversight, and disciplined direction. I don't have a team of sentient engineers at the moment. But I have built a team of AI agents, and they have given me something invaluable: the opportunity to keep evolving my leadership skills in real time.*
>
> *This tool is not a toy project. It is a production tool I depend on. Built the right way: charter first, requirements second, architecture third, code last. Not a single line written before the engineering was done.*
>
> *Senior leaders add the most value not by writing features, but by engineering systems and leading from the front. My role is to create the conditions where great engineering happens — clear direction, sound architecture, disciplined decision-making, and a high quality bar. Implementation is a team sport. In 2026, one of those teammates is AI."*

---

*This charter was produced through a structured requirements interview following BABOK elicitation techniques and IEEE 830 / ISO/IEC 29148 documentation standards.*
