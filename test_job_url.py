"""
End-to-end tests for job_url carry-through (ADR-012) and WAL-safe backups.
Run: python -m pytest test_job_url.py -v

Covers: fresh-install migration order (010 after 008), OB thought -> import
-> promote -> opportunities.job_url and JD file, pre-ADR entries without a
URL, and backup of WAL-resident data.
"""

import sqlite3
from pathlib import Path

import pytest

import database
import ob_bridge

REPO = Path(__file__).resolve().parent
URL = "https://jobs.example.com/jobs/123?lang=en-us&src=LinkedIn"

QFL_WITH_URL = f"""[quick-fit-log]
source_channel: linkedin
company_name: Example Co
role_title: Director, Cloud Operations
job_url: {URL}
role_level: Director
location_remote_status: remote | United States
opportunity_type: job
quick_fit: strong
decision: pursue
[/quick-fit-log]

[opportunity-artifact]
Example job description text.
[/opportunity-artifact]"""

QFL_NO_URL = QFL_WITH_URL.replace(f"job_url: {URL}\n", "").replace(
    "Example Co", "Older Co"
)


@pytest.fixture
def root(tmp_path):
    database.initialize_database(tmp_path / "pipelinepilot.db")
    return tmp_path


@pytest.fixture
def db(root):
    return root / "pipelinepilot.db"


def _import(db, thoughts):
    records = [ob_bridge.parse_ob_thought(t) for t in thoughts]
    imported, _, errors, _ = ob_bridge.import_to_sqlite(db, records)
    assert not errors
    return imported


def _qfl(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, ob_thought_id, job_url FROM quick_fit_log ORDER BY id"
    ).fetchall()
    conn.close()
    return rows


# ── Migration order ──────────────────────────────────────────

def test_fresh_install_has_job_url_column(db):
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(quick_fit_log)")}
    assert "job_url" in cols
    table_sql = sqlite3.connect(db).execute(
        "SELECT sql FROM sqlite_master WHERE name='quick_fit_log'"
    ).fetchone()[0]
    assert "Sr. Manager" in table_sql  # migration 008 ran, and 010 survived it


def test_initialize_is_idempotent(db):
    database.initialize_database(db)
    database.initialize_database(db)
    cols = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(quick_fit_log)")]
    assert cols.count("job_url") == 1


# ── Import -> promote ────────────────────────────────────────

def test_url_flows_through_import_and_promote(root, db):
    _import(db, [{"id": "t-url", "content": QFL_WITH_URL}])
    row = _qfl(db)[0]
    assert row["job_url"] == URL

    result = database.promote_quick_fit(db, row["id"], str(root))
    opp = database.get_opportunity(db, result["folder_name"])
    assert opp["job_url"] == URL

    jd = next((root / result["folder_name"]).glob("JD_*.txt")).read_text(encoding="utf-8")
    assert f"Job URL: {URL}" in jd


def test_pre_adr_entry_without_url_imports_and_promotes(root, db):
    assert _import(db, [{"id": "t-old", "content": QFL_NO_URL}]) == 1
    row = _qfl(db)[0]
    assert row["job_url"] is None

    result = database.promote_quick_fit(db, row["id"], str(root))
    assert database.get_opportunity(db, result["folder_name"])["job_url"] is None
    jd = next((root / result["folder_name"]).glob("JD_*.txt")).read_text(encoding="utf-8")
    assert "Job URL: \n" in jd


# ── WAL-safe backup ──────────────────────────────────────────

def test_backup_includes_wal_resident_rows(tmp_path):
    src = tmp_path / "wal.db"
    writer = sqlite3.connect(src)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")  # keep the commit in the -wal file
    writer.execute("CREATE TABLE t (v TEXT)")
    writer.execute("INSERT INTO t VALUES ('in-wal')")
    writer.commit()
    assert (tmp_path / "wal.db-wal").stat().st_size > 0

    dest = database.backup_database(src, tmp_path / "copy.db")
    rows = sqlite3.connect(dest).execute("SELECT v FROM t").fetchall()
    writer.close()
    assert rows == [("in-wal",)]
