-- ============================================================
-- PipelinePilot — Quick-Fit Log
-- Migration 003: Add promoted_folder_name column
-- Tracks which pipeline folder a promoted QFL entry maps to.
-- Applied inline by database.py since v0.1.x; this file
-- formalizes the migration for history and fresh installs.
-- ============================================================

ALTER TABLE quick_fit_log ADD COLUMN promoted_folder_name TEXT;
