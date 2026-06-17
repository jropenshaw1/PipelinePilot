# AGENTS.md — PipelinePilot

## Source of Authority
- This project is governed by the jonathan-ops governance framework, delivered automatically via the `jonathan-governance` Codex skill. Project-specific rules below supplement, never override, the governance framework.
- If this file conflicts with governance, governance wins.
- This is a public repo; the public/private boundary and secrets-by-reference rule from the governance framework apply.

## Project Shape
- PipelinePilot is a single-user Python desktop app for job-search pipeline management.
- Filesystem folders are the source of truth; SQLite is a derived, rebuildable index.
- The main UI is CustomTkinter in `pipelinepilot.py`.
- OpenBrain quick-fit import is optional and one-way through `ob_bridge.py`.
- Embedded fit analysis lives behind the `fit_analysis_engine.py` boundary.

## Architecture Conventions
- Preserve `Company_Role` folder names as the primary key across filesystem and SQLite.
- Do not manually rename opportunity folders or change primary-key semantics.
- Keep SQLite compatibility: no Postgres-only types, UUID defaults, server features, or auth assumptions.
- Store dates as ISO text strings unless an existing column already differs.
- Migrations must be idempotent and safe on existing local databases.
- Do not add, remove, or rename schema fields without explicit approval.
- Keep filesystem creation and DB writes paired; avoid folder-only or DB-only opportunity states.
- PipelinePilot owns lifecycle tracking; AI reasoning artifacts stay in `fit_analysis_engine.py` outputs or imported quick-fit records.

## Public Boundary
- Do not commit live secrets, credential values, Supabase keys, Anthropic keys, local config, SQLite DBs, job-search data, private repo paths, or private personal context.
- `pipelinepilot.config` is local-only and ignored; never inspect or quote secret contents.
- Before publication or commit, check for private paths, job-search posture, personal infrastructure details, and credentials.

## Approval Required
- Do not create, modify, delete, rename, stage, commit, push, or publish files without Jonathan's explicit approval.
- Do not run destructive commands, broad git operations, or SQL writes against a live DB without approval.
- Do not add dependencies, build systems, external services, telemetry, or schema changes without approval.
- Do not finalize or change governance/docs status without Jonathan's final call and any required review gate.

## Commands
- Install: `python -m venv venv`, `venv\Scripts\activate`, `pip install -r requirements.txt`.
- Run desktop app: `python pipelinepilot.py` or `launch.bat`.
- Test parser/import logic: `python -m pytest test_ob_bridge.py -v`.
- Optional quick-fit form: `streamlit run quick_fit_capture.py` only if Streamlit is installed.
- Build: none defined.
- Lint/format: none defined.

## Verification Before Reporting Done
- Confirm intended files only changed; if no approval was given, confirm no files changed.
- Re-read changed code/docs for filesystem-as-truth, SQLite compatibility, schema consistency, and public/private leakage.
- For parser/OpenBrain changes, run `python -m pytest test_ob_bridge.py -v` when dependencies are available.
- For UI/workflow changes, manually launch `python pipelinepilot.py` when safe and report what was exercised.
- For schema/migration changes, verify idempotency against existing DB shape or explain why this was not run.
- Report commands run, checks performed, unavailable checks, and remaining approval/review gates.