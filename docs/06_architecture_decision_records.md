# PipelinePilot — Architecture Decision Records (ADRs)

**Version:** 1.1
**Date:** March 12, 2026
**Author:** Jonathan Openshaw
**Standard:** Michael Nygard ADR Format
**Status:** Approved

---

## ADR-001: Filesystem as Source of Truth

**Date:** March 7, 2026
**Status:** Accepted

### Context
PipelinePilot requires both structured data (status, dates, scores) and unstructured artifacts (Word documents, markdown files). Two storage approaches were considered: database-primary (SQLite owns the record) or filesystem-primary (OneDrive folders own the record).

### Decision
The OneDrive filesystem is the source of truth. SQLite is a derived, rebuildable index.

### Rationale
- Files stored on OneDrive are automatically backed up and recoverable
- If the database is lost, it can be rebuilt from the filesystem via `rebuild-index`
- If files are lost, no database can recover them
- The most irreplaceable artifacts (tailored resume, cover letter) are files, not database rows
- When asked "which would you grieve more losing — the database or the files?" the answer was unambiguously the files
- This pattern is used in many AI-native internal tools: filesystem = truth, database = index

### Consequences
- Folder naming convention becomes critical — it is the primary key across both systems
- A folder renamed manually outside PipelinePilot breaks the primary key link
- A `rebuild-index` command is a required feature, not optional
- PipelinePilot must handle gracefully any state where filesystem and database are out of sync

---

## ADR-002: UI Framework — Python + CustomTkinter

**Date:** March 7, 2026
**Status:** Accepted

### Context
The existing tool used Streamlit, which required a background server process, a browser tab as the UI, manual shortcut creation, and icon hunting. This felt like a workaround, not an application.

Alternatives considered:
- **Streamlit** — rejected (background server process, no native Windows integration)
- **Electron** — rejected (overkill, heavy, fails KISS test)
- **React/web** — rejected (overkill, fails KISS test, requires web server)
- **Tkinter (standard)** — considered (too dated visually)
- **CustomTkinter** — selected
- **PyQt6** — considered (more powerful but more complex; fails relative KISS test)

### Decision
Python + CustomTkinter for the GUI layer.

### Rationale
- Launches as a native Windows desktop application — no background process, no browser
- Modern visual appearance compared to standard Tkinter
- Ships as a standard Python package via pip — no system dependencies
- Consistent with Python as the chosen language
- Low learning curve for future contributors
- Passes the KISS test: solves the problem without introducing unnecessary complexity

### Consequences
- Application limited to desktop (no web, no mobile) — acceptable per scope
- CustomTkinter is a third-party dependency — must be pinned in requirements.txt
- UI will not match native Windows 11 design language exactly — acceptable tradeoff

---

## ADR-003: SQLite as the Structured Data Index

**Date:** March 7, 2026
**Status:** Accepted

### Context
Structured data (status, dates, fit scores, contacts) needs a queryable store to support list views, filtering, sorting, and dashboard metrics.

Alternatives considered:
- **JSON files per opportunity** — rejected (no query capability, complex to filter/sort)
- **PostgreSQL / cloud database** — rejected (overkill, requires server, fails KISS test)
- **Supabase (OpenBrain pattern)** — rejected (external dependency, internet required, overkill for single user)
- **SQLite** — selected

### Decision
SQLite via Python's standard library `sqlite3` module.

### Rationale
- Zero server infrastructure — single file on local disk
- Automatically backed up alongside OneDrive documents
- Standard library — no additional dependency
- Sufficient for single-user, up to 500 records, local queries
- Disposable and rebuildable from filesystem (see ADR-001)
- Industry-standard choice for embedded single-user applications

### Consequences
- No concurrent write access — acceptable for single-user tool
- Database file must be stored in a known, configurable location
- All queries must be designed to degrade gracefully if database is absent

---

## ADR-004: Dual Artifact Output from Job Fit Analyst (.docx + .md)

**Date:** March 7, 2026
**Status:** Accepted

### Context
The Job Fit Analyst skill currently outputs `.docx` files. PipelinePilot requires machine-parseable structured metadata to populate the SQLite index. Three approaches were evaluated:
1. Parse the existing `.docx` narrative — brittle, fragile
2. Change Job Fit Analyst to output `.md` only — loses rich document formatting
3. Output both `.docx` and `.md` from a single analyst run — dual artifact pattern

### Decision
Job Fit Analyst shall output two fit analysis artifacts per run:
- `fit_analysis.docx` — human-readable, rich formatting, for review and recruiter demos
- `fit_analysis.md` — markdown with YAML front-matter, for PipelinePilot indexing

### Rationale
- `.docx` preserves the full Advocate/Auditor narrative in a professional format readable by anyone
- `.md` with YAML front-matter is trivial to parse reliably — no brittle prose parsing
- PipelinePilot parses only the YAML header — the narrative body is untouched by the indexer
- One analyst run produces both artifacts — no extra User effort
- Separation of concerns: human interface (.docx) vs. machine interface (.md)
- GitHub renders `.md` files natively — excellent for showcase and demo

### Consequences
- Job Fit Analyst skill requires a code change to output both file types
- YAML front-matter schema must be maintained as a documented contract between the two systems
- `analysis_version` field in the YAML enables future model/version tracking
- PipelinePilot integration module must be updated if the YAML schema changes

---

## ADR-005: No Automated Email Processing

**Date:** March 7, 2026
**Status:** Accepted

### Context
Automating email capture (confirmation emails, employer communications) via Gmail API or IMAP integration was considered to reduce manual effort.

### Decision
No automated email processing. Email content is captured manually via paste-into-text-area.

### Rationale
- Gmail API integration introduces OAuth complexity, token management, and an external dependency
- The value gained (saving ~30 seconds of paste effort) does not justify the complexity introduced
- KISS: the User copies and pastes — this is a 10-second operation that requires no infrastructure
- Reduces attack surface and eliminates credential management concerns
- Consistent with the principle: every dependency must justify its inclusion

### Consequences
- User must manually paste confirmation email text into PipelinePilot
- No automatic detection of new employer communications
- Future enhancement path exists if User finds manual capture too burdensome

---

## ADR-006: Reference and Index, Not Reinterpret

**Date:** March 7, 2026
**Status:** Superseded by ADR-008

### Context
When integrating with Job Fit Analyst output, two approaches were considered:
1. PipelinePilot generates its own fit summary by re-calling an AI model
2. PipelinePilot indexes the existing Job Fit Analyst artifact without generating new AI content

### Decision
PipelinePilot shall never generate its own AI reasoning content. It shall only index what Job Fit Analyst produces.

### Rationale
- Two AI reasoning artifacts for the same role creates drift — they may disagree
- Job Fit Analyst already produces high-quality Advocate/Auditor analysis — reinterpreting it adds no value
- The fit document doubles as an explainability and audit artifact — a second artifact undermines this
- Clean boundary between systems: Job Fit Analyst owns reasoning; PipelinePilot owns lifecycle tracking
- For enterprise AI governance audiences: one traceable artifact per decision is stronger than two competing ones

### Consequences
- PipelinePilot has no AI API dependency — it is a pure management tool
- All AI quality improvements flow through the Job Fit Analyst skill, not PipelinePilot
- `fit_analysis.md` is the single explainability record for every opportunity

*Superseded by ADR-008, March 12, 2026. The core principle (one authoritative AI artifact per role) remains in force. The constraint (no AI in PipelinePilot) is lifted.*

---

## ADR-007: Deterministic, Idempotent Rebuild Index

**Date:** March 7, 2026
**Status:** Accepted

### Context
Given that the filesystem is the source of truth and the database is derived, a recovery mechanism is required. The design of this mechanism is a deliberate architectural signal.

### Decision
`pipelinepilot rebuild-index` shall be deterministic and idempotent. It shall use UPSERT operations (INSERT OR REPLACE) so it can be run any number of times with identical results.

### Rationale
- Idempotency is a hallmark of resilient, production-grade system design
- A deterministic rebuild means the system is always recoverable from first principles
- UPSERT pattern eliminates the need for "was this already indexed?" bookkeeping
- Senior engineers and CTOs recognize idempotent rebuild as a maturity signal
- Supports development, testing, and production recovery with the same command

### Consequences
- All INSERT operations in the rebuild path must use INSERT OR REPLACE, not INSERT
- Rebuild must be tested against: empty database, partially populated database, fully populated database — all must produce identical results
- Summary report (scanned / indexed / warnings / failures) is required output for observability

---

## ADR-008: Embedded Fit Analysis Engine (Supersedes ADR-006)

**Date:** March 12, 2026
**Status:** Accepted

### Context

ADR-006 established that PipelinePilot would never generate its own AI reasoning content. The original design called for fit analysis to be produced exclusively by the Job Fit Analyst Claude skill, invoked externally, with PipelinePilot only indexing the resulting filesystem artifacts.

This decision rested on two assumptions:

1. Clean separation of concerns required a hard boundary — Job Fit Analyst owns reasoning, PipelinePilot owns lifecycle management
2. PipelinePilot was intended for free distribution as a standalone tool with no dependency on Job Fit Analyst, minimizing setup friction for end users

After several days of production use, reality challenged both assumptions. The external invocation model created real friction: switching to Claude.ai to run Job Fit Analyst and then returning to PipelinePilot interrupted the job search workflow at exactly the wrong moment. The tool was demonstrably more useful than anticipated. Optimizing for that usefulness outweighed the original simplicity goal.

Critically: both PipelinePilot and Job Fit Analyst are independently developed, freely distributed, open-source projects by the same author. The dependency is not proprietary. End users who want integrated fit analysis are asked to clone two public repos and configure one API key — a real but manageable cost.

### Decision

Embed `fit_analysis_engine.py` directly into PipelinePilot as a first-class integrated module. Fit analysis is initiated from within the PipelinePilot UI in a single action, requiring only a locally configured Anthropic API key.

The core architectural principle from ADR-006 is preserved: one authoritative AI reasoning artifact per role, no competing or duplicate analysis. The constraint it imposed (no AI API calls inside PipelinePilot) is lifted.

### Rationale

- Production use demonstrated the tool was valuable enough to optimize. Friction removed is value delivered.
- Both components are freely distributed — the dependency is transparent and the cost to end users is documented explicitly
- `fit_analysis_engine.py` is a distinct, isolated module with a documented interface. The boundary is maintained even though the invocation mechanism changed.
- The principle that matters (one authoritative artifact per role, no drift between competing reasoning sources) is fully preserved
- The original free-distribution intent is unchanged — installation now requires both repos and an API key, clearly documented in the README

### Consequences

- End users who want integrated fit analysis must: clone both repositories, install dependencies for both, and configure a valid Anthropic API key locally
- Users who want PipelinePilot as a standalone lifecycle tracker without AI analysis can still use it that way — fit analysis is an optional feature, not a requirement
- `requirements.txt` must include the `anthropic` library
- ADR-006 is superseded. The principle it protected remains. The constraint it imposed is lifted.
- Future changes to fit analysis logic require changes only in `fit_analysis_engine.py` — the module boundary is documented and maintained

---

*ADRs 001–007 produced from a structured requirements interview and cross-platform AI design session (Claude + ChatGPT) conducted March 7, 2026.*
*ADR-008 added March 12, 2026, following several days of production use. All decisions captured in OpenBrain with [source:claude] tags.*
