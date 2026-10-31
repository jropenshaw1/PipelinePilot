# database.py — PipelinePilot SQLite database layer
# Schema derived from Data Dictionary v1.0 §5
# NFR-05: Filesystem is truth — SQLite is a derived, rebuildable index

import logging
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import config
import filesystem
from filesystem import ArchiveError
from models import (
    DB_FILENAME,
    DEFAULT_STATUS,
    DONE_STATUSES,
    RETIRED_STATUS_MAP,
    STATUS_VALUES,
)

logger = logging.getLogger(__name__)

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
    posting_status_log      TEXT,
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


def migrate_add_posting_status_log(conn: sqlite3.Connection) -> None:
    """Idempotently add the posting lifecycle log to existing databases."""
    try:
        conn.execute("SELECT posting_status_log FROM opportunities LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute(
            "ALTER TABLE opportunities ADD COLUMN posting_status_log TEXT"
        )


def get_db_path(job_search_root: str) -> Path:
    return Path(job_search_root) / DB_FILENAME


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def backup_database(db_path: Path, dest: Path) -> Path:
    """
    Consistent copy of the database using SQLite's online backup API.

    PipelinePilot runs in WAL mode, so recent commits can live in the
    -wal side file until a checkpoint. A plain file copy of the main
    database can miss them; the backup API reads through SQLite and
    includes them.
    """
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest


def initialize_database(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(SCHEMA)
        migrate_add_interviews_table(conn)
        migrate_add_posting_status_log(conn)
        migrate_add_quick_fit_log(conn)
        migrate_map_retired_statuses(conn)
        conn.commit()


def migrate_map_retired_statuses(conn: sqlite3.Connection) -> None:
    """ADR-014: map any retired status (New, Capturing, In Review) to its
    replacement. Idempotent; logs each record changed. Covers a restored older
    backup or an older writer."""
    for old, new in RETIRED_STATUS_MAP.items():
        rows = conn.execute(
            "SELECT folder_name FROM opportunities WHERE status = ?", (old,)
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE opportunities SET status = ?, date_modified = ? "
                "WHERE folder_name = ?",
                (new, date.today().isoformat(), row[0]),
            )
            logger.warning(
                "Retired status mapped (ADR-014): %s: %s -> %s", row[0], old, new
            )


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
    # Migration 004: drop trg_auto_promote (must run AFTER 001 recreates it)
    migration_004 = Path(__file__).parent / "migrations" / "004_drop_auto_promote_trigger.sql"
    if migration_004.exists():
        conn.executescript(migration_004.read_text())

    # Migration 006: pursuit tracker columns (cl_reviewed, resume_reviewed, jfa_completed)
    for col_name in ("cl_reviewed", "resume_reviewed", "jfa_completed"):
        try:
            conn.execute(f"SELECT {col_name} FROM opportunities LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute(
                f"ALTER TABLE opportunities ADD COLUMN {col_name} INTEGER NOT NULL DEFAULT 0"
            )
    
    # Migration 007: add archived column to quick_fit_log (idempotent — check before ALTER)
    try:
        conn.execute("SELECT archived FROM quick_fit_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute(
            "ALTER TABLE quick_fit_log ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
        )

    # Migration 008: add Sr. Manager to role_level enum, company-site to source_channel
    # Idempotent: check if CHECK constraint already includes 'Sr. Manager'
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='quick_fit_log'"
    ).fetchone()
    if table_sql and "Sr. Manager" not in (table_sql[0] or ""):
        migration_008 = Path(__file__).parent / "migrations" / "008_add_sr_manager_role_level.sql"
        if migration_008.exists():
            conn.executescript(migration_008.read_text())

    # Migration 010: add job_url to quick_fit_log (ADR-012).
    # Must run AFTER 008 — 008's table rebuild copies an explicit column list
    # and would drop job_url on a fresh install if it were added earlier.
    try:
        conn.execute("SELECT job_url FROM quick_fit_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE quick_fit_log ADD COLUMN job_url TEXT")


def create_opportunity(db_path: Path, record: dict) -> None:
    """FR-06: Create record simultaneously with folder creation."""
    today = date.today().isoformat()
    record = dict(record)
    record.setdefault("date_discovered", today)
    record.setdefault("date_created", today)
    record.setdefault("date_modified", today)
    record.setdefault("status", DEFAULT_STATUS)
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
    status_filter: str | list[str] | None = None,
    sort_by: str | None = None,
) -> list[dict]:
    """FR-07: Return all opportunity records, optionally filtered and sorted."""
    conditions = []
    params = []
    if not include_archived:
        conditions.append("archived = 0")
    if status_filter:
        if isinstance(status_filter, str):
            status_filter = [status_filter]
        placeholders = ", ".join(["?" for _ in status_filter])
        conditions.append(f"status IN ({placeholders})")
        params.extend(status_filter)
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


def next_monday(reference_date: date) -> date:
    """Return the next Monday strictly after reference_date."""
    days_ahead = 7 - reference_date.weekday()
    if days_ahead == 7:
        days_ahead = 7
    return reference_date + timedelta(days=days_ahead)


def initial_follow_up(date_applied: date) -> date:
    """ADR-010: initial follow-up = next_monday(date_applied + offset).

    Every caller that sets a first follow-up date (desktop Mark Applied,
    status-change auto-fill, Save, MCP pipi_mark_applied) uses this one
    function. The offset comes from config.get_follow_up_offset_days(),
    read live, so there is no per-caller default to drift.
    """
    offset = config.get_follow_up_offset_days()
    return next_monday(date_applied + timedelta(days=offset))


def update_opportunity(db_path: Path, folder_name: str, updates: dict) -> None:
    """FR-10: Update fields and auto-set date_modified. FR-18: Auto follow_up_date."""
    updates = dict(updates)
    updates["date_modified"] = date.today().isoformat()

    if updates.get("status") == "Applied" and updates.get("date_applied"):
        if not updates.get("follow_up_date"):
            # Assign, not setdefault: the key may be present with value None
            # (empty field in the detail view), and setdefault would keep it.
            applied = date.fromisoformat(updates["date_applied"])
            updates["follow_up_date"] = initial_follow_up(applied).isoformat()

    # ADR-014: every write path (desktop Save, Mark Applied, MCP update_status,
    # close_opportunity) comes through here, so archive on Done lives here.
    # Archiving happens when the status changes to a Done status; saving a
    # record whose status is already Done moves nothing.
    status = updates.get("status")
    if status is not None:
        current = get_opportunity(db_path, folder_name)
        if (current and status in DONE_STATUSES and status != current["status"]
                and not current["archived"]):
            _archive_and_write(db_path, folder_name, updates)
            return
        if current and current["archived"] and status not in DONE_STATUSES:
            raise ArchiveError(
                f"'{folder_name}' is archived, and Done is final. "
                "A role that comes back is a new opportunity."
            )

    _write_opportunity(db_path, folder_name, updates)


def _write_opportunity(db_path: Path, folder_name: str, updates: dict) -> None:
    """One UPDATE, one transaction."""
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    sql = f"UPDATE opportunities SET {set_clause} WHERE folder_name = ?"
    with _connect(db_path) as conn:
        conn.execute(sql, list(updates.values()) + [folder_name])
        conn.commit()


# ── Archive on Done (ADR-014) ─────────────────────────────

def get_roots(db_path: Path) -> tuple[Path, Path]:
    """Job search root (the database's folder) and the validated archive root."""
    job_root = Path(db_path).parent
    archive_root = config.get_archive_root(job_root)
    filesystem.validate_archive_root(job_root, archive_root)
    return job_root, archive_root


def get_folder_path(db_path: Path, opp: dict) -> Path:
    """Where this opportunity's folder lives: the archive root when archived."""
    job_root = Path(db_path).parent
    return filesystem.resolve_folder_path(
        job_root, config.get_archive_root(job_root), opp["folder_name"], opp.get("archived")
    )


def _archive_and_write(db_path: Path, folder_name: str, updates: dict) -> None:
    """Move the folder to the archive root, then write updates with archived = 1
    in one transaction. If the write fails the folder is moved back."""
    job_root, archive_root = get_roots(db_path)
    with filesystem.fs_lock(f"archive {folder_name}"):
        current = get_opportunity(db_path, folder_name)  # re-read under the lock
        if current is None:
            raise ValueError(f"Opportunity '{folder_name}' not found")
        if current["archived"]:
            _write_opportunity(db_path, folder_name, updates)
            return
        src, dest = job_root / folder_name, archive_root / folder_name
        filesystem.move_folder(src, dest)
        try:
            _write_opportunity(db_path, folder_name, {**updates, "archived": 1})
        except Exception as error:
            try:
                os.rename(dest, src)
            except OSError as back:
                raise ArchiveError(
                    "The status was not saved and the folder could not be moved back. "
                    f"It is at {dest}; the record expects {src}. The startup "
                    f"consistency check will list it.\n{error}\n{back}"
                ) from error
            raise


def archive_opportunity(db_path: Path, folder_name: str) -> None:
    """ADR-014: archiving follows Done. Moves the folder of a record that is
    already in a Done status; refuses any other status."""
    current = get_opportunity(db_path, folder_name)
    if current is None:
        raise ValueError(f"Opportunity '{folder_name}' not found")
    if current["status"] not in DONE_STATUSES:
        raise ArchiveError(
            f"'{folder_name}' is {current['status']}. Set a Done status "
            f"({', '.join(DONE_STATUSES)}); archiving follows."
        )
    if not current["archived"]:
        _archive_and_write(db_path, folder_name, {"date_modified": date.today().isoformat()})


# Company_Role folder names; rebuild_index() uses the same rule
FOLDER_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_\-]{1,59}$"


def _folder_state(job_root: Path, archive_root: Path, folder_name: str, archived) -> str | None:
    """Consistency case (ADR-014): 'archive_only_active' (a),
    'active_only_archived' (b), 'both_or_neither' (c), or None when consistent."""
    in_job = (job_root / folder_name).is_dir()
    in_archive = (archive_root / folder_name).is_dir()
    if in_job == in_archive:
        return "both_or_neither"
    if in_archive and not archived:
        return "archive_only_active"
    if in_job and archived:
        return "active_only_archived"
    return None


def check_consistency(db_path: Path) -> dict:
    """Report rows whose folder location disagrees with archived (ADR-014),
    Company_Role folders with no record (report only), and resume/trace pairs
    left interrupted or mismatched (ADR-015, report only). Repairs nothing."""
    import re

    job_root, archive_root = get_roots(db_path)
    issues = {"archive_only_active": [], "active_only_archived": [], "both_or_neither": [],
              "folder_no_record": [], "resume_pair": []}
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT folder_name, status, archived FROM opportunities ORDER BY folder_name"
        ).fetchall()
    for row in rows:
        case = _folder_state(job_root, archive_root, row["folder_name"], row["archived"])
        if case:
            issues[case].append({
                "folder_name": row["folder_name"],
                "status": row["status"],
                "archived": row["archived"],
                "job_path": str(job_root / row["folder_name"]),
                "archive_path": str(archive_root / row["folder_name"]),
            })
    import fit_analysis_engine  # local import: the engine imports this module
    for row in rows:
        folder = (archive_root if row["archived"] else job_root) / row["folder_name"]
        for problem in fit_analysis_engine.folder_resume_problems(folder):
            issues["resume_pair"].append({
                "folder_name": row["folder_name"], "status": problem, "archived": row["archived"],
                "job_path": str(job_root / row["folder_name"]),
                "archive_path": str(archive_root / row["folder_name"]),
            })
    keys = {row["folder_name"].lower() for row in rows}
    pattern = re.compile(FOLDER_NAME_PATTERN)
    for root in (job_root, archive_root):
        for name in filesystem.get_existing_folders(str(root)):
            if pattern.match(name) and "_" in name and name.lower() not in keys:
                issues["folder_no_record"].append({
                    "folder_name": name, "status": "no record", "archived": None,
                    "job_path": str(job_root / name), "archive_path": str(archive_root / name),
                })
    return issues


def consistency_lines(issues: dict) -> list[str]:
    """Plain-text lines for a consistency report."""
    labels = {
        "archive_only_active": "Folder in archive, record active",
        "active_only_archived": "Folder in job search root, record archived",
        "both_or_neither": "Folder in both roots or neither",
        "folder_no_record": "Folder with no record",
        "resume_pair": "Resume and trace need attention",
    }
    return [
        f"{labels[case]}: {item['folder_name']} ({item['status']})"
        for case, items in issues.items() for item in items
    ]


def _require_case(db_path: Path, folder_name: str, expected: str) -> tuple[Path, Path, dict]:
    job_root, archive_root = get_roots(db_path)
    current = get_opportunity(db_path, folder_name)
    if current is None:
        raise ValueError(f"Opportunity '{folder_name}' not found")
    if _folder_state(job_root, archive_root, folder_name, current["archived"]) != expected:
        raise ArchiveError(f"'{folder_name}' changed since the check ran; run it again.")
    return job_root, archive_root, current


def repair_complete_archive(db_path: Path, folder_name: str, done_status: str) -> None:
    """Case (a): commit the intended Done status with archived = 1."""
    if done_status not in DONE_STATUSES:
        raise ValueError(f"Choose a Done status: {', '.join(DONE_STATUSES)}")
    with filesystem.fs_lock(f"repair {folder_name}"):
        _require_case(db_path, folder_name, "archive_only_active")
        _write_opportunity(db_path, folder_name, {
            "status": done_status, "archived": 1, "date_modified": date.today().isoformat(),
        })


def repair_restore(db_path: Path, folder_name: str) -> None:
    """Case (a): move the folder back to the job search root; status unchanged."""
    with filesystem.fs_lock(f"repair {folder_name}"):
        job_root, archive_root, _ = _require_case(db_path, folder_name, "archive_only_active")
        filesystem.move_folder(archive_root / folder_name, job_root / folder_name)


def repair_return_to_archive(db_path: Path, folder_name: str) -> None:
    """Case (b): move the folder back into the archive; Done status unchanged."""
    with filesystem.fs_lock(f"repair {folder_name}"):
        job_root, archive_root, _ = _require_case(db_path, folder_name, "active_only_archived")
        filesystem.move_folder(job_root / folder_name, archive_root / folder_name)


def repair_reactivate(db_path: Path, folder_name: str, status: str) -> None:
    """Case (b): commit the chosen active status with archived = 0."""
    if status not in STATUS_VALUES or status in DONE_STATUSES:
        raise ValueError("Choose an active status.")
    with filesystem.fs_lock(f"repair {folder_name}"):
        _require_case(db_path, folder_name, "active_only_archived")
        _write_opportunity(db_path, folder_name, {
            "status": status, "archived": 0, "date_modified": date.today().isoformat(),
        })


def _taken_folder_names(db_path: Path, job_root: Path, archive_root: Path) -> set[str]:
    with _connect(db_path) as conn:
        keys = {row[0] for row in conn.execute("SELECT folder_name FROM opportunities")}
    return (
        keys
        | set(filesystem.get_existing_folders(str(job_root)))
        | set(filesystem.get_existing_folders(str(archive_root)))
    )


def preview_folder_name(db_path: Path, company_name: str, role_title: str) -> str:
    """The name creation would use right now (suffixed if the base is in use)."""
    job_root, archive_root = get_roots(db_path)
    return filesystem.unique_folder_name(
        filesystem.generate_folder_name(company_name, role_title),
        _taken_folder_names(db_path, job_root, archive_root),
        date.today(),
    )


def create_opportunity_with_folder(db_path: Path, record: dict, create_folder) -> str:
    """ADR-014: choose a free Company_Role name, create the folder
    (create_folder(job_root, folder_name)) and insert the record, all while
    holding the lock. Returns the folder name used."""
    job_root, archive_root = get_roots(db_path)
    with filesystem.fs_lock("create opportunity"):
        folder_name = filesystem.unique_folder_name(
            filesystem.generate_folder_name(record["company_name"], record["role_title"]),
            _taken_folder_names(db_path, job_root, archive_root),
            date.today(),
        )
        create_folder(job_root, folder_name)
        create_opportunity(db_path, {**record, "folder_name": folder_name})
    return folder_name


def get_dashboard_metrics(db_path: Path) -> dict:
    """FR-23, FR-24: Compute pipeline metrics from the SQLite index."""
    today = date.today().isoformat()
    with _connect(db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE archived = 0"
        ).fetchone()[0]

        by_status = {}
        # Counts archived rows too, so Done history stays visible (ADR-014)
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM opportunities GROUP BY status"
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
            "AND status NOT IN ('Passed','Offer','Closed','Ghosted','Rejected')",
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


_FOLLOWUPS_DUE_WHERE = (
    "follow_up_date IS NOT NULL "
    "AND follow_up_date <= ? "
    "AND archived = 0 "
    "AND status NOT IN ('Passed','Offer','Closed','Ghosted','Rejected')"
)


def get_followups_due_count(db_path: Path) -> int:
    """Return count of opportunities with follow-up dates on or before today."""
    today = date.today().isoformat()
    with _connect(db_path) as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM opportunities WHERE {_FOLLOWUPS_DUE_WHERE}",
            (today,),
        ).fetchone()[0]


def get_followups_due(db_path: Path) -> list[dict]:
    """Return opportunities with follow-up dates on or before today, sorted oldest first."""
    today = date.today().isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM opportunities WHERE {_FOLLOWUPS_DUE_WHERE} "
            "ORDER BY follow_up_date ASC",
            (today,),
        ).fetchall()
    return [dict(r) for r in rows]


def rebuild_index(db_path: Path, job_search_root: str, fit_threshold: float = 0.65) -> dict:
    """
    FR-25 through FR-29: Reconstruct database entirely from filesystem.
    Deterministic, idempotent. Uses INSERT OR REPLACE.
    Non-conforming folders logged as warnings, not errors.
    """
    root = Path(job_search_root)
    report = {
        "folders_scanned": 0,
        "records_indexed": 0,
        "warnings": [],
        "failures": [],
    }

    initialize_database(db_path)
    with filesystem.fs_lock("rebuild index"):
        _rebuild_scan(db_path, root, fit_threshold, report)
    return report


def _rebuild_scan(db_path: Path, root: Path, fit_threshold: float, report: dict) -> None:
    """rebuild_index() body, run while holding the lock (ADR-014)."""
    import re
    import yaml

    report["warnings"].extend(consistency_lines(check_consistency(db_path)))
    with _connect(db_path) as conn:
        archived_names = {
            row[0].lower()
            for row in conn.execute("SELECT folder_name FROM opportunities WHERE archived = 1")
        }
    folder_name_pattern = re.compile(FOLDER_NAME_PATTERN)

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

        if folder_name.lower() in archived_names:
            report["warnings"].append(
                f"Skipped '{folder_name}' — matches an archived record; record left unchanged"
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
            "status": DEFAULT_STATUS,
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


# ── Quick-Fit Log Queries ──────────────────────────────────

def get_quick_fit_entries(
    db_path: Path,
    decision_filter: str | None = None,
    show_archived: bool = False,
    limit: int = 100,
) -> list[dict]:
    """Fetch quick-fit-log entries, optionally filtered by decision and archive status."""
    conditions = []
    params = []
    
    # Archive filter (default: show only active entries)
    if show_archived:
        conditions.append("archived = 1")
    else:
        conditions.append("archived = 0")
    
    # Decision filter
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


def get_quick_fit_entry(db_path: Path, qfl_id: int) -> dict | None:
    """Fetch one quick-fit-log entry by id, regardless of filter, archive or age."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM quick_fit_log WHERE id = ?", (qfl_id,)
        ).fetchone()
    return dict(row) if row else None


def get_quick_fit_metrics(db_path: Path) -> dict:
    """Compute quick-fit-log summary metrics (active entries only)."""
    with _connect(db_path) as conn:
        try:
            total = conn.execute("SELECT COUNT(*) FROM quick_fit_log WHERE archived = 0").fetchone()[0]
            by_decision = {}
            rows = conn.execute(
                "SELECT decision, COUNT(*) as cnt FROM quick_fit_log WHERE archived = 0 GROUP BY decision"
            ).fetchall()
            for row in rows:
                by_decision[row["decision"]] = row["cnt"]

            by_fit = {}
            rows = conn.execute(
                "SELECT quick_fit, COUNT(*) as cnt FROM quick_fit_log WHERE archived = 0 GROUP BY quick_fit"
            ).fetchall()
            for row in rows:
                by_fit[row["quick_fit"]] = row["cnt"]

            return {"total": total, "by_decision": by_decision, "by_fit": by_fit}
        except sqlite3.OperationalError:
            return {"total": 0, "by_decision": {}, "by_fit": {}}


def archive_quick_fit_entry(db_path: Path, qfl_id: int) -> None:
    """Archive a quick-fit-log entry (soft delete)."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE quick_fit_log SET archived = 1 WHERE id = ?",
            (qfl_id,),
        )
        conn.commit()


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


def promote_quick_fit(db_path: Path, qfl_id: int) -> dict:
    """
    Promote a quick-fit-log entry to a full pipeline opportunity, in the
    job search root that holds the database.

    Creates: folder + JD file (pre-populated) + opportunity DB record.
    The folder name gets a _YYYY-MM suffix if the base name is in use (ADR-014).
    Updates: QFL promoted_to_pipeline=1, promoted_folder_name=folder.
    Returns: dict with folder_name and status.
    Raises: ValueError on validation failure.
    """
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

    company = entry.get("company_name", "Unknown")
    role = entry.get("role_title", "UnknownRole")

    # Parse location
    loc_type, loc_city = _parse_location(
        entry.get("location_remote_status", "")
    )

    # Map source channel
    source = SOURCE_CHANNEL_TO_SOURCE.get(
        entry.get("source_channel", "other"), "Other"
    )

    artifact_text = entry.get("opportunity_artifact") or ""
    job_url = entry.get("job_url") or None

    record = {
        "company_name": company,
        "role_title": role,
        "job_url": job_url,
        "source": source,
        "location_type": loc_type,
        "location_city": loc_city,
        "decision_notes": entry.get("notes") or "",
        "status": DEFAULT_STATUS,
    }
    # Folder (with pre-populated JD) and record are created under the lock
    folder_name = create_opportunity_with_folder(
        db_path, record,
        lambda root, name: filesystem.create_opportunity_folder_with_jd(
            str(root), name, company, role, artifact_text, job_url=job_url,
        ),
    )

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
