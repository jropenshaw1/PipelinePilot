-- ============================================================
-- PipelinePilot — Quick-Fit Log
-- Migration 008: Add Sr. Manager to role_level enum,
--                add company-site to source_channel enum
-- ============================================================

-- SQLite does not support ALTER CHECK — must rebuild table.

CREATE TABLE quick_fit_log_new (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
    promoted_to_pipeline  INTEGER NOT NULL DEFAULT 0,

    source_channel        TEXT    NOT NULL CHECK (source_channel IN (
                            'linkedin','jobright','indeed','ladders',
                            'dice','jobgether','ziprecruiter',
                            'recruiter-outreach','referral',
                            'go-fractional','nates-network','company-site','other')),
    company_name          TEXT    NOT NULL DEFAULT 'Unknown',
    role_title            TEXT    NOT NULL,
    role_level            TEXT    NOT NULL CHECK (role_level IN (
                            'VP','Sr. Director','Director','Sr. Manager','below-target')),
    location_remote_status TEXT   NOT NULL,
    opportunity_type      TEXT    NOT NULL DEFAULT 'job' CHECK (opportunity_type IN (
                            'job','fractional','advisory','exploratory')),
    quick_fit             TEXT    NOT NULL CHECK (quick_fit IN (
                            'strong','moderate','weak','no-fit')),
    decision              TEXT    NOT NULL CHECK (decision IN (
                            'pursue','pass','parked')),

    primary_pass_reason   TEXT    CHECK (primary_pass_reason IS NULL OR primary_pass_reason IN (
                            'wrong-level','degree-required','cert-required',
                            'wrong-domain','location-mismatch','compensation-signal',
                            'culture-signal','overqualified','underqualified',
                            'timing','other')),
    pass_reason_note      TEXT,

    opportunity_artifact  TEXT,

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
    revisit_value         TEXT,
    tags                  TEXT,
    notes                 TEXT,
    session_reference     TEXT,

    -- Added in migration 002
    ob_thought_id         TEXT,
    -- Added in migration 003
    promoted_folder_name  TEXT,
    -- Added in migration 007
    archived              INTEGER NOT NULL DEFAULT 0
);

-- Copy existing data
INSERT INTO quick_fit_log_new (
    id, timestamp, promoted_to_pipeline,
    source_channel, company_name, role_title, role_level,
    location_remote_status, opportunity_type, quick_fit, decision,
    primary_pass_reason, pass_reason_note, opportunity_artifact,
    decision_confidence, role_attractiveness, comp_signal,
    secondary_pass_reason, parked_type, revisit_type, revisit_value,
    tags, notes, session_reference,
    ob_thought_id, promoted_folder_name, archived
)
SELECT
    id, timestamp, promoted_to_pipeline,
    source_channel, company_name, role_title, role_level,
    location_remote_status, opportunity_type, quick_fit, decision,
    primary_pass_reason, pass_reason_note, opportunity_artifact,
    decision_confidence, role_attractiveness, comp_signal,
    secondary_pass_reason, parked_type, revisit_type, revisit_value,
    tags, notes, session_reference,
    ob_thought_id, promoted_folder_name, archived
FROM quick_fit_log;

-- Swap tables
DROP TABLE quick_fit_log;
ALTER TABLE quick_fit_log_new RENAME TO quick_fit_log;

-- Rebuild indexes
CREATE INDEX IF NOT EXISTS idx_qfl_decision     ON quick_fit_log(decision);
CREATE INDEX IF NOT EXISTS idx_qfl_quick_fit    ON quick_fit_log(quick_fit);
CREATE INDEX IF NOT EXISTS idx_qfl_source       ON quick_fit_log(source_channel);
CREATE INDEX IF NOT EXISTS idx_qfl_company      ON quick_fit_log(company_name);
CREATE INDEX IF NOT EXISTS idx_qfl_timestamp    ON quick_fit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_qfl_opp_type     ON quick_fit_log(opportunity_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_qfl_ob_thought_id ON quick_fit_log(ob_thought_id);

-- Rebuild triggers
CREATE TRIGGER IF NOT EXISTS trg_require_pass_reason
BEFORE INSERT ON quick_fit_log
WHEN NEW.decision = 'pass' AND NEW.primary_pass_reason IS NULL
BEGIN
    SELECT RAISE(ABORT, 'primary_pass_reason is required when decision is pass');
END;

CREATE TRIGGER IF NOT EXISTS trg_require_pass_note
BEFORE INSERT ON quick_fit_log
WHEN NEW.primary_pass_reason = 'other' AND (NEW.pass_reason_note IS NULL OR NEW.pass_reason_note = '')
BEGIN
    SELECT RAISE(ABORT, 'pass_reason_note is required when primary_pass_reason is other');
END;
