-- ============================================================
-- PipelinePilot — Quick-Fit Log Bug Fix
-- Migration 004: Drop trg_auto_promote trigger
--
-- Root cause: trg_auto_promote fires on INSERT when decision='pursue'
-- and sets promoted_to_pipeline=1, but does NOT execute the full
-- promote workflow (folder creation, opportunity record). This
-- leaves entries stuck in a "promoted" display state with no
-- actual pipeline artifacts created.
--
-- Fix: Remove the trigger. The promote_quick_fit() function in
-- database.py handles setting promoted_to_pipeline=1 AFTER the
-- real work (folder + opportunity record) is done.
-- ============================================================

DROP TRIGGER IF EXISTS trg_auto_promote;
