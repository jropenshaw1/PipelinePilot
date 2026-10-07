"""
End-to-end tests for job_url carry-through (ADR-012) and WAL-safe backups.
Run: python -m pytest test_job_url.py -v

Covers: fresh-install migration order (010 after 008), OB thought -> import
-> promote -> opportunities.job_url and JD file, pre-ADR entries without a
URL, and the one-time backfill (dry run writes nothing, apply fills only
empty values, a manual URL always wins, backup includes WAL-resident data).
"""

import importlib.util
import sqlite3
import sys
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


def _load_backfill():
    path = REPO / "migrations" / "backfill_job_url_from_ob.py"
    spec = importlib.util.spec_from_file_location("backfill_job_url_from_ob", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


# ── Backfill ─────────────────────────────────────────────────

@pytest.fixture
def backfill(root, db, monkeypatch):
    module = _load_backfill()
    thoughts = [
        {"id": "t-url", "content": QFL_WITH_URL},
        {"id": "t-old", "content": QFL_NO_URL},
    ]
    monkeypatch.setattr(module.config, "load_config", lambda: {
        "job_search_root": str(root),
        "ob_supabase_url": "https://example.invalid",
        "ob_supabase_key": "test-key",
    })
    monkeypatch.setattr(module.ob_bridge, "fetch_qfl_thoughts", lambda url, key: thoughts)

    def run(*flags):
        monkeypatch.setattr(sys, "argv", ["backfill", *flags])
        return module.main()
    return run


@pytest.fixture
def promoted_without_url(root, db):
    """A promoted entry whose URL was lost before ADR-012."""
    _import(db, [{"id": "t-url", "content": QFL_WITH_URL}])
    qfl_id = _qfl(db)[0]["id"]
    folder = database.promote_quick_fit(db, qfl_id, str(root))["folder_name"]
    conn = sqlite3.connect(db)
    conn.execute("UPDATE quick_fit_log SET job_url = NULL")
    conn.execute("UPDATE opportunities SET job_url = NULL")
    conn.commit()
    conn.close()
    return folder


def test_extract_job_url():
    module = _load_backfill()
    assert module.extract_job_url(QFL_WITH_URL) == URL
    assert module.extract_job_url(QFL_NO_URL) is None
    assert module.extract_job_url("no block here") is None


def test_backfill_dry_run_writes_nothing(backfill, db, root, promoted_without_url):
    assert backfill() == 0
    assert _qfl(db)[0]["job_url"] is None
    assert database.get_opportunity(db, promoted_without_url)["job_url"] is None
    assert not list(root.glob("*.backup_*"))


def test_backfill_apply_fills_only_empty(backfill, db, root, promoted_without_url):
    assert backfill("--apply") == 0
    assert _qfl(db)[0]["job_url"] == URL
    assert database.get_opportunity(db, promoted_without_url)["job_url"] == URL
    assert len(list(root.glob("*.backup_*"))) == 1


def test_backfill_never_overwrites_manual_url(backfill, db, promoted_without_url):
    database.update_opportunity(db, promoted_without_url, {"job_url": "MANUAL"})
    assert backfill("--apply") == 0
    assert database.get_opportunity(db, promoted_without_url)["job_url"] == "MANUAL"


def test_backfill_skips_missing_opportunity_record(backfill, db, promoted_without_url):
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM opportunities WHERE folder_name = ?", (promoted_without_url,))
    conn.commit()
    conn.close()
    assert backfill("--apply") == 0
    assert _qfl(db)[0]["job_url"] == URL  # QFL row still filled


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
