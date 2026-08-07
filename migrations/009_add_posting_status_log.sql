-- Migration 009: Add posting_status_log column (ADR-009)
-- The idempotent existence check is implemented in database.py.

ALTER TABLE opportunities ADD COLUMN posting_status_log TEXT;
