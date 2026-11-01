# PipelinePilot

AI-assisted job search pipeline management -- built the right way.

PipelinePilot is a filesystem-first job search pipeline manager that tracks opportunities, integrates AI role analysis, and maintains a complete lifecycle record for every application.

---

## The Problem

Active job searching across multiple boards generates a flood of alerts that quickly becomes unmanageable. Roles get missed. Applications go untracked. Follow-ups slip. Documents scatter. There is no system -- just inbox entropy.

PipelinePilot solves that. It manages the complete lifecycle of every job opportunity from first alert through final close, integrates with an AI fit analysis skill to score and reason about each role, and keeps everything organized in a durable, filesystem-first structure that survives any database failure.

---

## How This Was Built

Documentation first. Code second. No exceptions.

Every architectural decision, requirement, use case, data field, and process flow was defined, documented, and committed to this repository before a single line of implementation code was written.

This is not a portfolio decoration. It is a production tool I depend on for my own job search -- built with the same discipline I would apply to any enterprise system.

The engineering sequence:

1. Requirements interview (BABOK elicitation)
2. Project Charter
3. Use Case Specification
4. Data Dictionary
5. Software Requirements Specification (IEEE 830 / ISO/IEC 29148)
6. Process Flow (BPMN 2.0)
7. Architecture Decision Records
8. Definition of Done
-- first commit of implementation code --

The commit history reflects this. The timestamps are not edited.

---

## Documentation

All project documentation is in `/docs`. Documents 01–07 were written before the first line of implementation code; 08 specifies the MCP server added later.

| Document | Standard |
|---|---|
| 01 -- Project Charter | BABOK |
| 02 -- Use Case Specification | UML / BABOK |
| 03 -- Data Dictionary | ISO/IEC 11179 |
| 04 -- Software Requirements Specification | IEEE 830 / ISO/IEC 29148 |
| 05 -- Process Flow | BPMN 2.0 |
| 06 -- Architecture Decision Records | Michael Nygard ADR |
| 07 -- Definition of Done | -- |
| 08 -- MCP Server PRD | -- |

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

**Stack:** Python, CustomTkinter, SQLite, python-docx, pathlib, requests

Filesystem-first ensures the system remains durable, inspectable, and recoverable even if the database layer fails.

**Core design decisions:**

- **Filesystem is truth.** OneDrive folders are the source of record. SQLite is a derived, rebuildable index -- losing the database is an inconvenience, not a disaster.
- **Folder name is the primary key.** `Company_Role` convention enforced at creation, previewed before commit, sanitized deterministically.
- **AI artifacts are documents.** Every Job Fit Analyst output is a durable filesystem artifact -- inspectable, indexable, auditable. Not a transient API response.
- **Reference and index, never reinterpret.** PipelinePilot indexes fit analysis output. It never generates a competing AI reasoning artifact.
- **Idempotent recovery.** `pipelinepilot rebuild-index` reconstructs the entire SQLite database from the filesystem. Run it once or ten times -- same result.
- **AI as capture interface.** Quick-fit triage happens conversationally through AI agents, with structured entries written to OpenBrain and imported into PipelinePilot. No manual form entry required.

The Architecture Decision Records document every significant choice, including what was rejected and why. See [`docs/06_ADR_Log_v1.6.md`](docs/06_ADR_Log_v1.6.md).

---

## Non-Goals

PipelinePilot intentionally does not attempt to solve every aspect of job searching.

The system is deliberately constrained to preserve simplicity and durability.

Non-goals include:

- **No job board scraping.** PipelinePilot assumes discovery happens elsewhere. It manages opportunities after discovery.
- **No AI reasoning inside PipelinePilot.** AI analysis is owned by the Job Fit Analyst system. PipelinePilot indexes outputs but never generates competing analysis.
- **No cloud service dependency.** The system runs entirely locally. Cloud storage is used only for file synchronization. OpenBrain integration is optional and one-directional (import only). The MCP server is local stdio only.
- **No complex workflow engine.** The lifecycle stages are intentionally simple and human-driven.

These constraints keep the system understandable, recoverable, and durable.

---

## System Capabilities

- **Opportunity capture** -- creates `Company_Role` folder and blank job description document in one action
- **Quick-fit triage** -- AI-powered rapid JD assessment across six dimensions (level, domain, location, degree/cert, culture, comp) with structured logging via OpenBrain
- **Promote to Pipeline** -- one-click promotion of quick-fit entries to full pipeline opportunities with editable company/role, JD pre-population, and folder creation
- **OpenBrain import** -- one-click import of quick-fit-log entries from Supabase-backed AI memory into SQLite, with server-side filtering, pagination, idempotent dedup, and a diagnostic summary that gives the reason for every rejected entry
- **Quick-fit log viewer** -- color-coded table of triage decisions with decision filtering and summary metrics
- **Fit analysis integration** -- parses YAML front-matter from `fit_analysis.md` to index score, recommendation, strengths, and gaps without duplicating reasoning
- **Application Queue** -- opportunities still to be submitted (Ready first, then Analyzing) with checklist columns for JFA completion, cover letter review, and resume review. Live applications are worked from Follow-ups Due and the Their move filter (ADR-014)
- **Follow-ups due** -- persistent sidebar link with live count badge; drill-down view of overdue follow-ups sorted by date
- **Mark Applied one-click** -- sets status, date applied, and follow-up date in a single action from either the Application Queue or the detail view
- **Monday follow-ups** -- every follow-up date lands on a Monday: the first one after the configured offset (Settings, default 14 days), and the next Monday after each still-posted check. Changing the offset in Settings takes effect immediately everywhere
- **Posting status log** -- machine-maintained record of every "still posted" check and the date a posting disappeared, kept separate from action items
- **MCP server** -- local MCP server that lets Claude Desktop query and update the pipeline directly, for conversational follow-up maintenance. See [`mcp_server/README.md`](mcp_server/README.md)
- **Full lifecycle tracking** -- Discovery to Capture to Fit Analysis to Application to Tracking to Close
- **Employer communication log** -- running dated log per role; confirmation email paste capture
- **Action items and interview management** -- per-role task list, interview date, pre/post notes
- **Opportunity scoring dashboard** -- pipeline metrics by stage, average fit score, follow-ups due
- **Sortable opportunity list** -- sort by newest first or company name; filter by status; search by company or role
- **Rebuild index** -- deterministic, idempotent recovery from filesystem state

---

## Quick-Fit Log & OpenBrain Integration

PipelinePilot includes a lightweight triage layer for rapid JD evaluation. The workflow:

1. **Triage in conversation** -- tell your AI agent "quick fit" with a pasted JD. The agent assesses fit across six dimensions and writes a structured `[quick-fit-log]` entry to OpenBrain.
2. **Import into PipelinePilot** -- click "Import from OB" in the sidebar. PipelinePilot asks Supabase only for thoughts containing a `[quick-fit-log]` block (server-side filter, paginated), so every QFL entry stays reachable no matter how large OpenBrain grows. It then parses the structured blocks, deduplicates by thought ID, and inserts into the `quick_fit_log` SQLite table.
3. **Review in the Quick-Fit Log** -- the "Quick-Fit Log" view shows all triage decisions with color-coded fit scores and decision badges, filterable by decision type.

### Reading the Import Summary

Each import ends with a summary screen:

| Line | Meaning |
|---|---|
| Fetched | Thoughts returned by the QFL filter |
| Parsed | Valid `[quick-fit-log]` blocks |
| Imported | New rows written to `quick_fit_log` |
| Skipped | Already imported (dedup by thought ID) -- expected on re-import |
| Not QFL | Thoughts that mention the QFL tags in prose but contain no block (for example, session handoff notes). Skipped, not counted as failures |
| Parse failures | Real QFL blocks that failed validation. Each shows the thought ID, created date, company / role, the rejection reason (missing field, invalid enum value, `pass` without a pass reason), and a 300-character preview of the raw entry |

The screen lists the first five items per category. The full list, including every preview, is written to the log.

This creates a complete triage-to-pipeline funnel: AI handles the capture, PipelinePilot handles the management. Roles scored as "pursue" can be promoted to the full pipeline for detailed fit analysis, resume optimization, and application tracking.

OpenBrain integration is optional. PipelinePilot functions fully without it -- the quick-fit log table can also be populated through the existing Streamlit capture form (`quick_fit_capture.py`).

### Setting Up the Quick-Fit Skill

The quick-fit triage is powered by a Claude skill that runs conversationally. No UI, no form, no context switching. You paste a JD, get a verdict, and the structured entry lands in OpenBrain ready for PipelinePilot import.

**Installation:**

1. Copy the `quick-fit` folder into your Claude skills directory (typically `~/.claude/skills/` or your MCP skills path).
2. The skill file (`SKILL.md`) contains the trigger logic, the six-dimension assessment rubric, the structured output schema, and the OpenBrain write instructions.
3. Ensure your Claude environment has access to the OpenBrain MCP server for `capture_thought` writes.

**Trigger phrases:** "quick fit", "fit check", "qf this", "quick take on this", "quick read on this", "is this worth pursuing", or "run a quick fit."

**What happens:** When triggered, the skill parses the JD, assesses fit across six dimensions (level alignment, domain match, location/remote, degree/cert requirements, culture/industry signals, and compensation signals), renders a brief conversational verdict, writes a schema-compliant `[quick-fit-log]` entry to OpenBrain, and confirms the write with a thought ID.

**Assessment output:**

- **Fit scores:** strong, moderate, weak, or no-fit
- **Decisions:** pursue, pass, or parked
- **Pass reasons:** Structured enum vocabulary (wrong-level, degree-required, location-mismatch, etc.) for downstream filtering

The schema is the contract between the quick-fit skill and PipelinePilot's import parser. The skill enforces the format. PipelinePilot trusts it.

### Relationship Between Quick-Fit and Job Fit Analyst

Quick-fit is the 30-second upstream screen. Job Fit Analyst is the full deep dive. They are complementary, not competing:

- **Quick-fit** answers: "Is this worth my time?" Runs in seconds. One OB write. Done.
- **Job Fit Analyst** answers: "How exactly do I position myself for this role?" Runs six agents. Produces cover letter, optimized resume, and interview guide.

A typical workflow: quick-fit 10 roles in a morning scan, pursue 2-3, run Job Fit Analyst on the ones worth the full treatment.

---

## Job Fit Analyst Integration

PipelinePilot integrates with the [Job Fit Analyst](https://github.com/jropenshaw1/job-fit-analyst) Claude skill -- a separate six-agent system that produces four artifacts per analysis run, all saved directly to the role's folder:

- `fit_analysis.docx` -- full Advocate/Auditor narrative for human review
- `fit_analysis.md` -- YAML front-matter metadata for PipelinePilot indexing
- `Resume_Company_Role.docx` -- tailored resume optimized for the specific role, with its review trace in `_review/` (see below)
- `CoverLetter_Company_Role.docx` -- tailored cover letter

PipelinePilot parses `fit_analysis.md` to index the score, recommendation, strengths, and gaps. The resume and cover letter are stored in the folder and used directly by the user.

The two systems are cleanly separated. **Job Fit Analyst owns AI reasoning. PipelinePilot owns lifecycle tracking.**

### Resume Tailoring and the Review Trace

A JFA run tailors the resume in a second model call (ADR-015). The model is told to select, order and lightly reword material from the master resume or an optional resume pool. Python then checks every published line and replaces or drops any line that fails, so the rules below are enforced in code, not only requested in the prompt. The checks are narrower than "no new facts": what they cover, and what they do not, is stated next. Read it before relying on a tailored resume.

#### What the checks guarantee

> The Python checks guarantee only that every digit-bearing number (compared after removing a leading `~` and thousands separators) and every capitalized, non-sentence-initial name (compared case-insensitively, including parts of hyphenated words) in a published line also appears in the cited sources (role and summary bullets) or anywhere in the master resume or the loaded pool (headline, subtitle and summary paragraph), and that every competency term is either one of the owner's own competency terms, exactly as written, or appears word for word as a phrase in one master text (headline, subtitle, summary paragraph, a summary bullet, a competency term, a role title or a role bullet; not the pool, company lines or competency labels), not split by punctuation or by the `|` separator, with a one-word term that has a capital letter matching the master's capitalization and other terms compared case-insensitively. A term that fails reverts its whole competency line to the master terms, except that a one-word term differing only in capitalization, or a repeat of an earlier term in the line, is dropped. Passing terms are published without edge punctuation or extra spaces. They do not check meaning, ownership verbs past the first word of a role bullet, any verb in summary bullets, lowercase terms and sentence-initial terms outside competency lines, whether a competency phrase meant the same thing where the master used it, quantities written in words, approximation markers and comparative words (`over`, `nearly`, `up to`), credentials, completion status, causal links between combined sources, or which employer a number belongs to. "Verified" means traceable at the token level, not checked for meaning. Every `retuned` line must be read by the owner against its sources before the resume is sent.

#### How a run works

- **Master and pool.** The master `.docx` (the `.docx` beside the configured resume path) is the source and the template; output keeps its formatting. The optional **Resume Pool Folder** setting (`resume_pool_path`) points to pool items (`*.md`) and a `role_map.yaml` that binds them to master roles. The loader reads each item's `polished_resume_item` and skips it only when it is empty or a placeholder starting with `(`; it has no approval status, so put only items you would stand behind in that folder. Left blank, tailoring uses the master alone. Any problem loading either fails closed: the run publishes an unchanged master copy.
- **Review trace.** Each run writes `_review/TRACE_DO-NOT-UPLOAD_Company_Role.md` in the opportunity folder, listing every reworded line beside its source and every change the checks made. It sits in a subfolder with that name so it cannot be uploaded in place of the resume. The resume and trace are published as a pair with the same `run_id`; an interrupted publication rolls back or forward on the next run. Reworded lines are listed largest growth first, each with its signed growth in characters and percent against a baseline: its longest cited source (bullets), the master paragraph (headline, subtitle, summary paragraph) or the master line (competency lines). "New" means there is no baseline.
- **Run state.** `tailored` (nothing changed by the checks), `partial` (some lines reverted, replaced or dropped) or `master-copy` (tailoring failed; the master was published). The state appears in the progress message, the trace header and the resume's document properties.
- **Length capacity** (ADR-015 Amendment 2). Each editable paragraph may grow only up to a character capacity computed from the master on every run, using two constants in `fit_analysis_engine.py`: `RESUME_LINE_MIN_CHARS = 92` and `RESUME_LINE_MAX_CHARS = 111`, the shortest and longest full lines measured on the owner's template. They are a calibrated heuristic, not a page guarantee: recalibrate them if you change the template's font, size or margins. A line over capacity reverts to master text; length never deletes a bullet. A role kept out of the summary also stays within its master character total (Amendment 1 A3), checked in the same step as capacity. The prompt sends each paragraph's master length beside its capacity and calls the capacity a ceiling, not a target.
- **Final checks.** Before the resume is written, Python confirms that every paragraph fits its capacity, that bullet counts stay within the master's, that each role kept out of the summary stays within its master total, that every bullet carrying a master bullet's ID is that bullet's exact text (and a line matching a master bullet of its own group carries its ID), that the headline, subtitle and summary paragraph are the exact master text when marked verified, and that no bullet group repeats a line (compared after collapsing whitespace and lower-casing). Any failure publishes an unchanged master copy, and the trace names the check that failed.
- **Input limits.** The job description is never truncated: it is sent whole up to 40,000 characters (`JD_MAX_CHARS`), and a longer one stops the run before the credential is retrieved and before any API call or file write (ADR-015 Amendment 3). The master resume is sent whole up to 20,000 characters (`RESUME_MAX_CHARS`).
- **Model.** The **JFA Model** setting (`jfa_model`, default `claude-opus-5-5`) takes an exact Anthropic model ID and is used for both calls (ADR-016). An unavailable model stops the analysis with a message pointing to the setting; there is no silent fallback.
- **Before sending.** Read every retuned line in the trace against its sources, then open the resume in Word and confirm the page count. Both are manual: neither is checked by the code.

#### Known limits

Each limit below is a way a tailored line can pass the checks and still be wrong. Owner review of the trace is the control for all of them.

- **T1.** A name at the start of a sentence is not checked outside competency lines (`Kubernetes migration across teams.` passes as a summary bullet; so does a tool after `e.g.` or as the first word of a role bullet's second sentence). Amendment 4 D2 (pending) addresses it. Competency terms are checked by Amendment 4 D1.
- **T2.** Lowercase tools, practices and scope words are not checked outside competency lines (`terraform`, `showback`, `chargeback`, `global`, `enterprise-wide`).
- **T3.** Meaning can change while every name and number stays the same; ownership verbs are checked only as the first word of a role bullet, and not at all in summary bullets.
- **T4.** A number can move to a different metric (a budget becomes savings).
- **T5.** Two sources can be combined to imply cause, scale or ownership.
- **T6.** Quantities written in words are not checked (`twenty percent`, `multi-million-dollar`, `dozens`, `double-digit`).
- **T7.** The headline, subtitle and summary paragraph are checked against the whole master and pool, so a fact from one employer can attach to another; the trace names no source for them.
- **T8.** Lowercase credential and status words are not checked (`certified`, `licensed`, `board-facing`).
- **T9.** Completion and hedges can be removed (`proposed` becomes `implemented`, `helped reduce` becomes `reduced`).
- **T10.** Firsts, superlatives and exclusivity are not checked (`first`, `sole`, `end-to-end`, `from scratch`).
- **T11.** Dropping a qualifier can invert meaning (`migration away from legacy` becomes `migration of legacy`).
- **T12.** An approximation can become exact (`~2,000` becomes `2000` or `over 2,000`).
- **T13.** Short lines may grow to their capacity, mostly with the unchecked word types above. The prompt calls capacity a ceiling, not a target, and the trace lists the largest growth first.
- **T14.** A role can repeat another role's line word for word when the line traces to its own sources, because duplicate checks run within a role. A fix is planned.
- **T15.** A competency term can be lifted out of its master context (`evaluated Kubernetes; did not deploy` makes `Kubernetes` a valid term).
- **T16.** Case-insensitive matches can change a word's capitalization: a one-word lowercase term (`spark`) and any multi-word term (`Spark Adoption`) pass against master text `spark adoption`.

---

## Personalizing Output with a Companion Context Skill

The Job Fit Analyst produces strong results with just a resume and a job description. But the cover letters, optimized resumes, and interview guides it generates are inherently generic. They sound like a competent AI wrote them, not like you wrote them.

A companion context skill solves this. It is a private skill file you create that carries your personal voice, career narrative, signature proof points, and standing framing decisions. When loaded alongside the Job Fit Analyst, it enriches Agents 4 (Cover Letter), 5 (Resume), and 6 (Interview Guide) with context that makes the output authentically yours.

### What Goes in a Companion Context Skill

A companion skill is a single `SKILL.md` file that you write and maintain. It typically includes:

- **Identity and positioning:** Your career thesis in one sentence. What kind of leader you are. What roles you target.
- **Voice and tone rules:** How your writing should sound. Phrases to use, phrases to ban. Register and formality level.
- **Signature war stories:** Your 4-7 most powerful career proof points, each with specific numbers and a note on when to deploy them.
- **Standing framing decisions:** Rules that apply to every application. How to handle degree equivalency, year counts, scope accuracy, contact information, formatting preferences.
- **Current search posture:** Active applications, target geography, certifications, excluded companies.
- **Agent-specific instructions:** Guidance for each downstream agent on how to use the context. What the cover letter should feel like. What the resume optimizer should preserve. What the interview guide should pull for STAR outlines.

### Setting Up Your Companion Skill

1. Create a folder in your Claude skills directory named after yourself (e.g., `your-name-context/`).
2. Write a `SKILL.md` file following the structure above. Start with the sections that matter most to you and expand over time.
3. In the skill's YAML front matter, set trigger phrases that link it to the Job Fit Analyst workflow (e.g., "write my cover letter", "optimize my resume", "interview guide", "personalize this").
4. The skill loads automatically when triggered alongside the Job Fit Analyst. No code changes required.

### How It Works at Runtime

When you trigger the Job Fit Analyst (e.g., "help me apply for this role"), the companion context skill is available to Agents 4, 5, and 6. They draw from it the same way a ghostwriter would draw from interview notes with their client: the structure and analysis come from the Job Fit Analyst, the voice and specificity come from your companion skill.

The companion skill does not modify the Job Fit Analyst's workflow or analysis logic. The Source Integrity Layer still governs all output. Your war stories are only used where they genuinely map to the JD's requirements. The Advocate/Auditor framework is unchanged. What changes is that the output reads like you wrote it on a good day, not like an AI templated it.

### Why This Matters

Hiring managers and recruiters can spot AI-generated application materials. The tells are consistent: generic enthusiasm, vague transferable-skill language, no personality. A companion context skill is the difference between an application that reads like everyone else's and one that carries your actual voice, your actual numbers, and your actual story.

The Job Fit Analyst is public and free. Your companion skill is private and personal. Together, they produce output that is honest, grounded, and sounds like the person who actually lived the career.

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

Configure your job search root folder on first launch. PipelinePilot creates a `pipelinepilot.config` file in the application directory -- no hardcoded paths, no registry entries.

> **Important:** PipelinePilot's filesystem-first architecture means your job search folder *is* your data. A local-only folder is not sufficient -- your root folder must be inside a cloud-synced directory such as OneDrive, Google Drive, Dropbox, or equivalent. If the files are lost, no database backup can recover them. This is the one infrastructure requirement the tool cannot enforce for you.

### Agent Vault Setup

PipelinePilot retrieves the OpenBrain and Anthropic credentials from a separate Dashlane agent vault at the moment each operation needs them. Secret values do not belong in `pipelinepilot.config`.

1. Install the [Dashlane CLI](https://github.com/Dashlane/dashlane-cli#installation) for Windows and make sure `dcli` is available on `PATH`.
2. Confirm the installed version with `dcli --version`.
3. Run `dcli sync` and complete the account registration, verification, and master-password prompts in the visible terminal window. See Dashlane's [authentication guide](https://github.com/Dashlane/dashlane-cli/blob/master/documentation/pages/personal/authentication.mdx).
4. Find each credential item's ID without printing its password:

   ```powershell
   dcli p title=<unique-title> -o json | ConvertFrom-Json | Select-Object id, title
   ```

   Confirm the exact title before copying the ID; the title filter can match more than one item.

Configure these non-secret fields in PipelinePilot Settings:

- `job_search_root` -- cloud-synced job-search folder
- `ob_supabase_url` -- OpenBrain Supabase project URL
- `agent_vault_account` -- Dashlane agent-vault login
- `ob_key_vault_id` -- Dashlane item ID for the OpenBrain credential
- `anthropic_key_vault_id` -- Dashlane item ID for the Anthropic credential
- `dcli_path` -- optional full path to `dcli.exe`; leave blank to use `PATH`

"Test vault access" reads and displays item titles only. It never displays or stores the credential values.

### OpenBrain Integration (Optional)

To enable quick-fit log import from OpenBrain:

1. Complete Agent Vault Setup and enter the OpenBrain URL and vault item ID in Settings.
2. Use the "Import from OB" button to pull quick-fit entries. If the vault is locked or logged out, PipelinePilot opens a visible terminal for authentication and then retries the operation.

Requires a [Supabase](https://supabase.com) project with the OpenBrain schema. See the OpenBrain MCP server documentation for setup details.

---

## On Building with AI in 2026

The pace of AI innovation is unlike anything I have seen in 28 years in technology. New tools arrive weekly. Functionality morphs daily. Staying relevant as a senior technology leader means more than reading about AI: it means building with it.

Leading in the AI era requires a new management model. AI agents are a new type of employee: they require clear requirements, defined scope, quality oversight, and disciplined direction. This project is built on that model.

I did not write the implementation code. I engineered the solution: requirements, architecture, design decisions, validation, and quality control. Senior leaders add the most value not by writing features, but by engineering systems and leading from the front.

My role is to create the conditions where great engineering happens: clear direction, sound architecture, disciplined decision-making, and a high quality bar. Implementation is a team sport. In 2026, one of those teammates is AI.

---

## Status

🟢 **v0.4.0** -- Desktop application operational. Pursuit tracker live. Follow-ups sidebar badge active. Quick-fit triage pipeline and OpenBrain import functional. MCP server and posting status log in use; see [Unreleased] in the CHANGELOG for changes since 0.4.0.

---

[Jonathan Openshaw](https://www.linkedin.com/in/jonathan-openshaw) | [Job Fit Analyst](https://github.com/jropenshaw1/job-fit-analyst)
