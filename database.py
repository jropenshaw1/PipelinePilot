# database.py — PipelinePilot SQLite database layer
# Schema derived from Data Dictionary v1.0 §5
# NFR-05: Filesystem is truth — SQLite is a derived, rebuildable index

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from models import DB_FILENAME

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    folder_name             TEXT PRIMARY KEY,
    company_name            TEXT NOT NULL,
    role_title              TEXT NOT NULL,
    job_url                 TEXT,
    source                  TEXT,
    source_other            TEXT,
    date_discovered         DATE NOT NULL,
    restrictions            TEXT,
    location_type           TEXT,
    location_city           TEXT,
    fit_score               REAL,
    fit_threshold           REAL DEFAULT 0.65,
    recommendation          TEXT,
    decision_override       INTEGER NOT NULL DEFAULT 0,
    decision_notes          TEXT,
    top_strengths           TEXT,
    top_gaps                TEXT,
    status                  TEXT NOT NULL DEFAULT 'New',
    date_applied            DATE,
    confirmation_email      TEXT,
    contact_name            TEXT,
    contact_email           TEXT,
    last_communication_date DATE,
    last_communication_type TEXT,
    communication_notes     TEXT,
    follow_up_date          DATE,
    action_items            TEXT,
    interview_date          DATE,
    interview_notes         TEXT,
    date_created            DATE NOT NULL,
    date_modified           DATE NOT NULL,
    archived                INTEGER NOT NULL DEFAULT 0
)
"""

INTERVIEWS_SCHEMA = """
CREATE TABLE IF NOT EXISTS interviews (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_folder_name TEXT NOT NULL REFERENCES opportunities(folder_name) ON DELETE CASCADE,
    interview_type          TEXT CHECK (interview_type IN (
        'Phone Screen',
        'Recruiter Screen',
        'Hiring Manager',
        'Technical Interview',
        'Panel Interview',
        'Onsite Interview',
        'Offer Discussion',
        'Other'
    )),
    scheduled_date          TEXT,
    duration_minutes        INTEGER,
    interviewer_name        TEXT,
    interviewer_title       TEXT,
    status                  TEXT NOT NULL DEFAULT 'Scheduled' CHECK (status IN (
        'Scheduled',
        'Completed',
        'No Show',
        'Cancelled'
    )),
    notes                   TEXT,
    feedback                TEXT,
    rating                  INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    date_created            TEXT NOT NULL,
    date_modified           TEXT NOT NULL
);
"""


def migrate_add_interviews_table(conn: sqlite3.Connection) -> None:
    """
    Idempotent migration to add the interviews table.
    Safe to call on existing databases — CREATE TABLE IF NOT EXISTS
    means it will no-op if the table already exists.
    """
    with conn:
        conn.executescript(INTERVIEWS_SCHEMA)


def get_db_path(job_search_root: str) -> Path:
    return Path(job_search_root) / DB_FILENAME


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize_database(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(SCHEMA)
        migrate_add_interviews_table(conn)
        migrate_add_quick_fit_log(conn)
        conn.commit()


def migrate_add_quick_fit_log(conn: sqlite3.Connection) -> None:
    """Idempotent migration: create quick_fit_log table + ob_thought_id column."""
    migration_001 = Path(__file__).parent / "migrations" / "001_create_quick_fit_log.sql"
    if migration_001.exists():
        conn.executescript(migration_001.read_text())
    # Migration 002: add ob_thought_id (idempotent — check before ALTER)
    try:
        conn.execute("SELECT ob_thought_id FROM quick_fit_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE quick_fit_log ADD COLUMN ob_thought_id TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_qfl_ob_thought_id "
            "ON quick_fit_log(ob_thought_id)"
        )
    # Migration 003: add promoted_folder_name (idempotent — check before ALTER)
    try:
        conn.execute("SELECT promoted_folder_name FROM quick_fit_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute(
            "ALTER TABLE quick_fit_log ADD COLUMN promoted_folder_name TEXT"
        )


def create_opportunity(db_path: Path, record: dict) -> None:
    """FR-06: Create record simultaneously with folder creation."""
    today = date.today().isoformat()
    record = dict(record)
    record.setdefault("date_discovered", today)
    record.setdefault("date_created", today)
    record.setdefault("date_modified", today)
    record.setdefault("status", "Capturing")
    record.setdefault("decision_override", 0)
    record.setdefault("archived", 0)
    record.setdefault("fit_threshold", 0.65)

    cols = ", ".join(record.keys())
    placeholders = ", ".join(["?" for _ in record])
    sql = f"INSERT INTO opportunities ({cols}) VALUES ({placeholders})"
    with _connect(db_path) as conn:
        conn.execute(sql, list(record.values()))
        conn.commit()


SORT_OPTIONS = {
    "Newest First": "date_created DESC",
    "Company Name": "company_name COLLATE NOCASE ASC",
}

DEFAULT_SORT = "Newest First"


def get_all_opportunities(
    db_path: Path,
    include_archived: bool = False,
    status_filter: str | None = None,
    sort_by: str | None = None,
) -> list[dict]:
    """FR-07: Return all opportunity records, optionally filtered and sorted."""
    conditions = []
    params = []
    if not include_archived:
        conditions.append("archived = 0")
    if status_filter:
        conditions.append("status = ?")
        params.append(status_filter)
    sql = "SELECT * FROM opportunities"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    order_clause = SORT_OPTIONS.get(sort_by, SORT_OPTIONS[DEFAULT_SORT])
    sql += f" ORDER BY {order_clause}"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_opportunity(db_path: Path, folder_name: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM opportunities WHERE folder_name = ?",
            (folder_name,),
        ).fetchone()
    return dict(row) if row else None


def update_opportunity(db_path: Path, folder_name: str, updates: dict) -> None:
    """FR-10: Update fields and auto-set date_modified. FR-18: Auto follow_up_date."""
    updates = dict(updates)
    updates["date_modified"] = date.today().isoformat()

    if updates.get("status") == "Applied" and updates.get("date_applied"):
        if not updates.get("follow_up_date"):
            applied = date.fromisoformat(updates["date_applied"])
            updates.setdefault(
                "follow_up_date",
                (applied + timedelta(days=14)).isoformat(),
            )

    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    sql = f"UPDATE opportunities SET {set_clause} WHERE folder_name = ?"
    with _connect(db_path) as conn:
        conn.execute(sql, list(updates.values()) + [folder_name])
        conn.commit()


def archive_opportunity(db_path: Path, folder_name: str) -> None:
    """FR-11: Soft delete."""
    update_opportunity(db_path, folder_name, {"archived": 1})


def get_dashboard_metrics(db_path: Path) -> dict:
    """FR-23, FR-24: Compute pipeline metrics from the SQLite index."""
    today = date.today().isoformat()
    with _connect(db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE archived = 0"
        ).fetchone()[0]

        by_status = {}
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM opportunities "
            "WHERE archived = 0 GROUP BY status"
        ).fetchall()
        for row in rows:
            by_status[row["status"]] = row["cnt"]

        analyzed = conn.execute(
            "SELECT COUNT(*) FROM opportunities "
            "WHERE fit_score IS NOT NULL AND archived = 0"
        ).fetchone()[0]

        avg_row = conn.execute(
            "SELECT AVG(fit_score) FROM opportunities "
            "WHERE fit_score IS NOT NULL AND archived = 0"
        ).fetchone()[0]
        avg_fit = round(avg_row, 2) if avg_row is not None else None

        above_threshold = conn.execute(
            "SELECT COUNT(*) FROM opportunities "
            "WHERE fit_score IS NOT NULL AND fit_score >= fit_threshold AND archived = 0"
        ).fetchone()[0]

        follow_ups_due = conn.execute(
            "SELECT COUNT(*) FROM opportunities "
            "WHERE follow_up_date IS NOT NULL "
            "AND follow_up_date <= ? "
            "AND archived = 0 "
            "AND status NOT IN ('Passed','Offer','Closed','Rejected')",
            (today,),
        ).fetchone()[0]

    return {
        "total": total,
        "by_status": by_status,
        "analyzed": analyzed,
        "avg_fit": avg_fit,
        "above_threshold": above_threshold,
        "follow_ups_due": follow_ups_due,
    }


def rebuild_index(db_path: Path, job_search_root: str, fit_threshold: float = 0.65) -> dict:
    """
    FR-25 through FR-29: Reconstruct database entirely from filesystem.
    Deterministic, idempotent. Uses INSERT OR REPLACE.
    Non-conforming folders logged as warnings, not errors.
    """
    import re
    import yaml

    root = Path(job_search_root)
    report = {
        "folders_scanned": 0,
        "records_indexed": 0,
        "warnings": [],
        "failures": [],
    }

    initialize_database(db_path)
    folder_name_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{1,59}$")

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        report["folders_scanned"] += 1
        folder_name = entry.name

        if not folder_name_pattern.match(folder_name) or "_" not in folder_name:
            report["warnings"].append(
                f"Skipped '{folder_name}' — does not match Company_Role convention"
            )
            continue

        fit_data = {}
        fit_file = entry / "fit_analysis.md"
        if fit_file.exists():
            try:
                content = fit_file.read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        fit_data = yaml.safe_load(parts[1]) or {}
            except Exception as e:
                report["warnings"].append(
                    f"YAML parse error in '{folder_name}/fit_analysis.md': {e}"
                )
                fit_data = {}

        record = {
            "folder_name": folder_name,
            "company_name": fit_data.get("company", folder_name.split("_")[0]),
            "role_title": fit_data.get("role", "_".join(folder_name.split("_")[1:])),
            "job_url": fit_data.get("job_url"),
            "date_discovered": date.today().isoformat(),
            "fit_score": fit_data.get("fit_score"),
            "fit_threshold": fit_data.get("fit_threshold", fit_threshold),
            "recommendation": fit_data.get("recommendation"),
            "decision_override": 0,
            "top_strengths": str(fit_data.get("top_strengths", [])) if fit_data.get("top_strengths") else None,
            "top_gaps": str(fit_data.get("top_gaps", [])) if fit_data.get("top_gaps") else None,
            "status": "New",
            "archived": 0,
            "date_created": date.today().isoformat(),
            "date_modified": date.today().isoformat(),
        }

        try:
            with _connect(db_path) as conn:
                existing = conn.execute(
                    "SELECT folder_name FROM opportunities WHERE folder_name = ?",
                    (folder_name,),
                ).fetchone()

                if existing:
                    fs_fields = {
                        "company_name": record["company_name"],
                        "role_title": record["role_title"],
                        "fit_score": record.get("fit_score"),
                        "fit_threshold": record.get("fit_threshold", fit_threshold),
                        "recommendation": record.get("recommendation"),
                        "top_strengths": record.get("top_strengths"),
                        "top_gaps": record.get("top_gaps"),
                        "date_modified": date.today().isoformat(),
                    }
                    set_clause = ", ".join([f"{k} = ?" for k in fs_fields])
                    conn.execute(
                        f"UPDATE opportunities SET {set_clause} WHERE folder_name = ?",
                        list(fs_fields.values()) + [folder_name],
                    )
                else:
                    cols = ", ".join(record.keys())
                    placeholders = ", ".join(["?" for _ in record])
                    conn.execute(
                        f"INSERT INTO opportunities ({cols}) VALUES ({placeholders})",
                        list(record.values()),
                    )
                conn.commit()
            report["records_indexed"] += 1
        except Exception as e:
            report["failures"].append(f"Failed to index '{folder_name}': {e}")

    return report


# ── Quick-Fit Log Queries ──────────────────────────────────

def get_quick_fit_entries(
    db_path: Path,
    decision_filter: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Fetch quick-fit-log entries, optionally filtered by decision."""
    conditions = []
    params = []
    if decision_filter and decision_filter != "All":
        conditions.append("decision = ?")
        params.append(decision_filter)

    sql = "SELECT * FROM quick_fit_log"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY timestamp DESC"
    sql += f" LIMIT {limit}"

    with _connect(db_path) as conn:
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []


def get_quick_fit_metrics(db_path: Path) -> dict:
    """Compute quick-fit-log summary metrics."""
    with _connect(db_path) as conn:
        try:
            total = conn.execute("SELECT COUNT(*) FROM quick_fit_log").fetchone()[0]
            by_decision = {}
            rows = conn.execute(
                "SELECT decision, COUNT(*) as cnt FROM quick_fit_log GROUP BY decision"
            ).fetchall()
            for row in rows:
                by_decision[row["decision"]] = row["cnt"]

            by_fit = {}
            rows = conn.execute(
                "SELECT quick_fit, COUNT(*) as cnt FROM quick_fit_log GROUP BY quick_fit"
            ).fetchall()
            for row in rows:
                by_fit[row["quick_fit"]] = row["cnt"]

            return {"total": total, "by_decision": by_decision, "by_fit": by_fit}
        except sqlite3.OperationalError:
            return {"total": 0, "by_decision": {}, "by_fit": {}}


# ── Quick-Fit → Pipeline Promotion ────────────────────────

# Maps QFL source_channel values to opportunity SOURCE_VALUES
SOURCE_CHANNEL_TO_SOURCE = {
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "ladders": "Ladders",
    "recruiter-outreach": "Recruiter",
    "referral": "Other",
    "go-fractional": "Other",
    "nates-network": "Other",
    "jobright": "Other",
    "other": "Other",
}


def _parse_location(location_remote_status: str) -> tuple:
    """Parse QFL location string into (location_type, location_city).

    Examples:
        "remote"                   → ("Remote", None)
        "remote | United States"   → ("Remote", "United States")
        "hybrid | Phoenix, AZ"     → ("Hybrid", "Phoenix, AZ")
        "onsite | Boston, MA"      → ("Onsite", "Boston, MA")
    """
    if not location_remote_status:
        return ("Remote", None)

    parts = [p.strip() for p in location_remote_status.split("|", 1)]
    loc_type_raw = parts[0].lower()

    if "remote" in loc_type_raw:
        loc_type = "Remote"
    elif "hybrid" in loc_type_raw:
        loc_type = "Hybrid"
    elif "onsite" in loc_type_raw or "on-site" in loc_type_raw:
        loc_type = "Onsite"
    else:
        loc_type = "Remote"

    loc_city = parts[1].strip() if len(parts) > 1 else None
    return (loc_type, loc_city)


def promote_quick_fit(db_path: Path, qfl_id: int, job_search_root: str) -> dict:
    """
    Promote a quick-fit-log entry to a full pipeline opportunity.

    Creates: folder + JD file (pre-populated) + opportunity DB record.
    Updates: QFL promoted_to_pipeline=1, promoted_folder_name=folder.
    Returns: dict with folder_name and status.
    Raises: ValueError on validation failure.
    """
    import filesystem

    # Fetch the QFL entry
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM quick_fit_log WHERE id = ?", (qfl_id,)
        ).fetchone()

    if not row:
        raise ValueError(f"Quick-fit entry #{qfl_id} not found")

    entry = dict(row)

    # Guard: already promoted
    if entry.get("promoted_to_pipeline") == 1:
        existing = entry.get("promoted_folder_name", "?")
        raise ValueError(
            f"Entry #{qfl_id} already promoted to '{existing}'"
        )

    # Generate folder name
    company = entry.get("company_name", "Unknown")
    role = entry.get("role_title", "UnknownRole")
    folder_name = filesystem.generate_folder_name(company, role)

    # Check for orphaned states before proceeding
    folder_on_disk = filesystem.folder_exists(job_search_root, folder_name)
    with _connect(db_path) as conn:
        existing_opp = conn.execute(
            "SELECT folder_name FROM opportunities WHERE folder_name = ?",
            (folder_name,),
        ).fetchone()

    if existing_opp and not folder_on_disk:
        # DB orphan: record exists but folder was deleted — clean up the record
        with _connect(db_path) as conn:
            conn.execute(
                "DELETE FROM opportunities WHERE folder_name = ?",
                (folder_name,),
            )
            conn.commit()
        existing_opp = None  # cleared — proceed normally

    if folder_on_disk and not existing_opp:
        # Folder orphan: folder exists but no DB record (e.g. prior promote
        # created folder then crashed before DB insert) — skip folder creation,
        # just create the DB record below
        pass
    elif folder_on_disk and existing_opp:
        # Both exist — genuine duplicate
        raise ValueError(
            f"Folder '{folder_name}' already exists with a pipeline record. "
            "Use the existing opportunity or rename."
        )

    # Parse location
    loc_type, loc_city = _parse_location(
        entry.get("location_remote_status", "")
    )

    # Map source channel
    source = SOURCE_CHANNEL_TO_SOURCE.get(
        entry.get("source_channel", "other"), "Other"
    )

    # Create folder with pre-populated JD (skip if folder already exists)
    artifact_text = entry.get("opportunity_artifact") or ""
    if not folder_on_disk:
        filesystem.create_opportunity_folder_with_jd(
            job_search_root, folder_name, company, role, artifact_text
        )

    # Build and insert opportunity record
    record = {
        "folder_name": folder_name,
        "company_name": company,
        "role_title": role,
        "source": source,
        "location_type": loc_type,
        "location_city": loc_city,
        "decision_notes": entry.get("notes") or "",
        "status": "Capturing",
    }
    create_opportunity(db_path, record)

    # Mark QFL entry as promoted
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE quick_fit_log "
            "SET promoted_to_pipeline = 1, promoted_folder_name = ? "
            "WHERE id = ?",
            (folder_name, qfl_id),
        )
        conn.commit()

    return {"folder_name": folder_name, "status": "promoted"}
