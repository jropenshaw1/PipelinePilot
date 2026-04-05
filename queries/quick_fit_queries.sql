-- ============================================================
-- PipelinePilot — Quick-Fit Log Reporting Queries
-- Use after ~50 entries for meaningful patterns.
-- ============================================================


-- ── 1. Source Channel Quality ─────────────────────────────
-- Which channels produce the highest quick-fit scores?
-- Numeric mapping: strong=0.8, moderate=0.6, weak=0.4, no-fit=0.2

SELECT
    source_channel,
    COUNT(*)                                          AS total,
    ROUND(AVG(CASE quick_fit
        WHEN 'strong'   THEN 0.8
        WHEN 'moderate' THEN 0.6
        WHEN 'weak'     THEN 0.4
        WHEN 'no-fit'   THEN 0.2
    END), 2)                                          AS avg_fit_score,
    SUM(CASE WHEN decision = 'pursue' THEN 1 ELSE 0 END) AS pursues,
    ROUND(100.0 * SUM(CASE WHEN decision = 'pursue' THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                      AS pursue_rate_pct
FROM quick_fit_log
GROUP BY source_channel
ORDER BY avg_fit_score DESC;


-- ── 2. Top Pass Reasons by Volume ─────────────────────────
-- Pre-filter automation spec: what kills opportunities?

SELECT
    primary_pass_reason,
    COUNT(*)                          AS count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM quick_fit_log WHERE decision = 'pass'), 1)
                                      AS pct_of_passes
FROM quick_fit_log
WHERE decision = 'pass' AND primary_pass_reason IS NOT NULL
GROUP BY primary_pass_reason
ORDER BY count DESC;


-- ── 3. "Other" Pass Reasons — Graduation Candidates ──────
-- Any pattern appearing 3+ times should graduate to its own enum code.

SELECT
    pass_reason_note,
    COUNT(*) AS count
FROM quick_fit_log
WHERE primary_pass_reason = 'other' AND pass_reason_note IS NOT NULL
GROUP BY pass_reason_note
ORDER BY count DESC;


-- ── 4. Pursue-to-Pipeline Conversion Rate ─────────────────

SELECT
    COUNT(*)                                                AS total_entries,
    SUM(CASE WHEN decision = 'pursue' THEN 1 ELSE 0 END)   AS pursued,
    SUM(CASE WHEN promoted_to_pipeline = 1 THEN 1 ELSE 0 END) AS in_pipeline,
    ROUND(100.0 * SUM(CASE WHEN decision = 'pursue' THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                            AS pursue_rate_pct
FROM quick_fit_log;


-- ── 5. Decision Distribution ──────────────────────────────

SELECT
    decision,
    COUNT(*)  AS count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM quick_fit_log), 1) AS pct
FROM quick_fit_log
GROUP BY decision
ORDER BY count DESC;


-- ── 6. Geographic & Level Mismatch by Channel ─────────────

SELECT
    source_channel,
    SUM(CASE WHEN primary_pass_reason = 'location-mismatch' THEN 1 ELSE 0 END) AS location_mismatches,
    SUM(CASE WHEN primary_pass_reason = 'wrong-level' THEN 1 ELSE 0 END)       AS level_mismatches,
    COUNT(*) AS total
FROM quick_fit_log
WHERE decision = 'pass'
GROUP BY source_channel
ORDER BY location_mismatches + level_mismatches DESC;


-- ── 7. Company Watch List Candidates ──────────────────────
-- High attractiveness + parked/timing = worth tracking.

SELECT
    company_name,
    role_title,
    quick_fit,
    decision,
    primary_pass_reason,
    role_attractiveness,
    parked_type,
    revisit_value,
    timestamp
FROM quick_fit_log
WHERE role_attractiveness = 'high'
  AND (decision = 'parked' OR (decision = 'pass' AND primary_pass_reason = 'timing'))
ORDER BY timestamp DESC;


-- ── 8. Confidence Correlation ─────────────────────────────
-- Are low-confidence passes masking opportunities?

SELECT
    decision_confidence,
    decision,
    COUNT(*) AS count,
    ROUND(AVG(CASE quick_fit
        WHEN 'strong'   THEN 0.8
        WHEN 'moderate' THEN 0.6
        WHEN 'weak'     THEN 0.4
        WHEN 'no-fit'   THEN 0.2
    END), 2) AS avg_fit
FROM quick_fit_log
WHERE decision_confidence IS NOT NULL
GROUP BY decision_confidence, decision
ORDER BY decision_confidence, decision;


-- ── 9. Opportunity Type Breakdown ─────────────────────────
-- Fractional/network signal-to-noise ratio.

SELECT
    opportunity_type,
    COUNT(*) AS total,
    SUM(CASE WHEN quick_fit IN ('strong','moderate') THEN 1 ELSE 0 END) AS viable,
    ROUND(100.0 * SUM(CASE WHEN quick_fit IN ('strong','moderate') THEN 1 ELSE 0 END) / COUNT(*), 1)
        AS viable_rate_pct,
    SUM(CASE WHEN decision = 'pursue' THEN 1 ELSE 0 END) AS pursued
FROM quick_fit_log
GROUP BY opportunity_type
ORDER BY viable_rate_pct DESC;


-- ── 10. Weekly Activity Summary ───────────────────────────

SELECT
    strftime('%Y-W%W', timestamp) AS week,
    COUNT(*)                                                AS logged,
    SUM(CASE WHEN decision = 'pursue' THEN 1 ELSE 0 END)   AS pursued,
    SUM(CASE WHEN decision = 'pass'   THEN 1 ELSE 0 END)   AS passed,
    SUM(CASE WHEN decision = 'parked' THEN 1 ELSE 0 END)   AS parked
FROM quick_fit_log
GROUP BY week
ORDER BY week DESC
LIMIT 12;


-- ── 11. Role Title Clustering ─────────────────────────────
-- What function/domain patterns emerge?

SELECT
    role_title,
    COUNT(*) AS appearances,
    GROUP_CONCAT(DISTINCT company_name) AS companies
FROM quick_fit_log
GROUP BY role_title
HAVING COUNT(*) > 1
ORDER BY appearances DESC;


-- ── 12. Parked Entries Without Revisit (Dead Weight) ──────
-- Flag in quarterly review.

SELECT
    id, company_name, role_title, parked_type, timestamp
FROM quick_fit_log
WHERE decision = 'parked'
  AND revisit_value IS NULL
ORDER BY timestamp ASC;


-- ── 13. Repost Detection Candidates ──────────────────────
-- Same company + similar role appearing multiple times.

SELECT
    company_name,
    role_title,
    COUNT(*) AS times_seen,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM quick_fit_log
WHERE opportunity_artifact IS NOT NULL
GROUP BY company_name, role_title
HAVING COUNT(*) > 1
ORDER BY times_seen DESC;


-- ── 14. Tag Frequency ─────────────────────────────────────
-- NOTE: requires splitting comma-separated tags. This is a
-- simplified version that works for exact tag matching.
-- For proper tag decomposition, handle in Python/Streamlit.

SELECT
    tags,
    COUNT(*) AS count
FROM quick_fit_log
WHERE tags IS NOT NULL
GROUP BY tags
ORDER BY count DESC;
