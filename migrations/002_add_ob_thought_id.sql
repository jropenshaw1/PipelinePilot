-- ============================================================
-- PipelinePilot — Quick-Fit Log Enhancement
-- Migration 002: Add ob_thought_id for OpenBrain dedup
-- Tracks which OB thoughts have already been imported
-- to prevent duplicate inserts on repeated imports.
-- ============================================================

ALTER TABLE quick_fit_log ADD COLUMN ob_thought_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_qfl_ob_thought_id
    ON quick_fit_log(ob_thought_id);
