-- ============================================================
-- PipelinePilot — Quick-Fit Log (ADR-008)
-- Migration 001: Create quick_fit_log table
-- Schema source: OB 8c17b063 (canonical, locked)
-- ============================================================

CREATE TABLE IF NOT EXISTS quick_fit_log (
    -- ── Auto / Defaulted ──────────────────────────────────
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
    promoted_to_pipeline  INTEGER NOT NULL DEFAULT 0,   -- derived: 1 when decision='pursue'

    -- ── User-Entered (8 core + 1 conditional) ─────────────
    source_channel        TEXT    NOT NULL CHECK (source_channel IN (
                            'linkedin','jobright','indeed','ladders',
                            'recruiter-outreach','referral',
                            'go-fractional','nates-network','other')),
    company_name          TEXT    NOT NULL DEFAULT 'Unknown',
    role_title            TEXT    NOT NULL,
    role_level            TEXT    NOT NULL CHECK (role_level IN (
                            'VP','Sr. Director','Director','below-target')),
    location_remote_status TEXT   NOT NULL,              -- e.g. "remote" or "hybrid | Phoenix, AZ"
    opportunity_type      TEXT    NOT NULL DEFAULT 'job' CHECK (opportunity_type IN (
                            'job','fractional','advisory','exploratory')),
    quick_fit             TEXT    NOT NULL CHECK (quick_fit IN (
                            'strong','moderate','weak','no-fit')),
    decision              TEXT    NOT NULL CHECK (decision IN (
                            'pursue','pass','parked')),

    -- Conditional: required when decision='pass', optional when 'parked'
    primary_pass_reason   TEXT    CHECK (primary_pass_reason IS NULL OR primary_pass_reason IN (
                            'wrong-level','degree-required','cert-required',
                            'wrong-domain','location-mismatch','compensation-signal',
                            'culture-signal','overqualified','underqualified',
                            'timing','other')),
    pass_reason_note      TEXT,                          -- required when primary_pass_reason='other'

    -- Full opportunity text — governed, immutable, captured at evaluation
    opportunity_artifact  TEXT,

    -- ── Ideal-Version Fields (captured when time permits) ─
    decision_confidence   TEXT    CHECK (decision_confidence IS NULL OR decision_confidence IN (
                            'high','medium','low')),
    role_attractiveness   TEXT    CHECK (role_attractiveness IS NULL OR role_attractiveness IN (
                            'high','medium','low')),
    comp_signal           TEXT    CHECK (comp_signal IS NULL OR comp_signal IN (
                            'above','in-range','below','unknown')),
    secondary_pass_reason TEXT    CHECK (secondary_pass_reason IS NULL OR secondary_pass_reason IN (
                            'wrong-level','degree-required','cert-required',
                            'wrong-domain','location-mismatch','compensation-signal',
                            'culture-signal','overqualified','underqualified',
                            'timing','other')),
    parked_type           TEXT    CHECK (parked_type IS NULL OR parked_type IN (
                            'timing','dependency','relationship','market-watch')),
    revisit_type          TEXT    CHECK (revisit_type IS NULL OR revisit_type IN (
                            'date','event')),
    revisit_value         TEXT,                          -- date or condition string
    tags                  TEXT,                          -- freeform keywords, comma-separated
    notes                 TEXT,                          -- one-line context
    session_reference     TEXT                           -- link to evaluation session
);

-- ── Triggers ──────────────────────────────────────────────

-- NOTE: trg_auto_promote removed in migration 004. promote_quick_fit() in
-- database.py sets promoted_to_pipeline=1 after the full workflow completes.

-- Enforce: pass_reason required when decision='pass'
CREATE TRIGGER IF NOT EXISTS trg_require_pass_reason
BEFORE INSERT ON quick_fit_log
WHEN NEW.decision = 'pass' AND NEW.primary_pass_reason IS NULL
BEGIN
    SELECT RAISE(ABORT, 'primary_pass_reason is required when decision is pass');
END;

-- Enforce: pass_reason_note required when primary_pass_reason='other'
CREATE TRIGGER IF NOT EXISTS trg_require_pass_note
BEFORE INSERT ON quick_fit_log
WHEN NEW.primary_pass_reason = 'other' AND (NEW.pass_reason_note IS NULL OR NEW.pass_reason_note = '')
BEGIN
    SELECT RAISE(ABORT, 'pass_reason_note is required when primary_pass_reason is other');
END;

-- ── Indexes ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_qfl_decision     ON quick_fit_log(decision);
CREATE INDEX IF NOT EXISTS idx_qfl_quick_fit    ON quick_fit_log(quick_fit);
CREATE INDEX IF NOT EXISTS idx_qfl_source       ON quick_fit_log(source_channel);
CREATE INDEX IF NOT EXISTS idx_qfl_company      ON quick_fit_log(company_name);
CREATE INDEX IF NOT EXISTS idx_qfl_timestamp    ON quick_fit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_qfl_opp_type     ON quick_fit_log(opportunity_type);
