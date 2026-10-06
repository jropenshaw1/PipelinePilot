-- ============================================================
-- PipelinePilot — Quick-Fit Log
-- Migration 010: Add job_url column (ADR-012)
-- Carries the posting URL from the OB [quick-fit-log] block
-- through import and into the opportunity on promote.
-- Applied inline by database.py (after migration 008, whose
-- table rebuild uses an explicit column list); this file
-- formalizes the migration for history and fresh installs.
-- ============================================================

ALTER TABLE quick_fit_log ADD COLUMN job_url TEXT;
