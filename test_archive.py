"""ADR-014: archive on Done, lock, path checks, consistency repairs, name reuse.

Runs against a scratch job search root and archive root (see conftest.py)."""
import json
import os
import time
from datetime import date

import pytest

import database
import filesystem
from filesystem import ArchiveError


@pytest.fixture
def roots(tmp_path):
    job = tmp_path / "00_JobSearch"
    job.mkdir()
    db = database.get_db_path(str(job))
    database.initialize_database(db)
    return job, tmp_path / "001_ArchiveJobSearch", db


def _opp(db, job, name="Acme_DirectorIT", status="Applied", folder=True):
    if folder:
        (job / name).mkdir()
        (job / name / f"JD_{name}.txt").write_text("jd", encoding="utf-8")
    company, role = name.split("_", 1)
    database.create_opportunity(db, {"folder_name": name, "company_name": company,
                                     "role_title": role, "status": status})
    return name


# ── Archive on Done ──────────────────────────────────────────

def test_done_moves_folder_and_sets_archived(roots):
    job, arc, db = roots
    name = _opp(db, job)
    database.update_opportunity(db, name, {"status": "Ghosted"})
    row = database.get_opportunity(db, name)
    assert (row["status"], row["archived"]) == ("Ghosted", 1)
    assert not (job / name).exists() and (arc / name / f"JD_{name}.txt").exists()
    assert database.get_folder_path(db, row) == arc / name


def test_saving_unchanged_done_status_moves_nothing(roots):
    """Legacy Done records (status set before ADR-014) move only via the
    migration or an explicit archive, not on an ordinary save."""
    job, arc, db = roots
    name = _opp(db, job, status="Passed")
    database.update_opportunity(db, name, {"status": "Passed", "action_items": "note"})
    row = database.get_opportunity(db, name)
    assert (row["archived"], row["action_items"]) == (0, "note") and (job / name).is_dir()
    database.update_opportunity(db, name, {"status": "Ghosted"})  # a change to Done archives
    assert database.get_opportunity(db, name)["archived"] == 1 and (arc / name).is_dir()


def test_move_failure_leaves_status_unchanged(roots, monkeypatch):
    job, arc, db = roots
    name = _opp(db, job)

    def locked(src, dst):
        raise PermissionError("file open in Word")
    monkeypatch.setattr(filesystem.os, "rename", locked)
    with pytest.raises(ArchiveError, match="Could not move"):
        database.update_opportunity(db, name, {"status": "Closed"})
    row = database.get_opportunity(db, name)
    assert (row["status"], row["archived"]) == ("Applied", 0)
    assert (job / name).is_dir()


def test_db_failure_moves_folder_back(roots, monkeypatch):
    job, arc, db = roots
    name = _opp(db, job)
    real_write = database._write_opportunity

    def failing_write(db_path, folder_name, updates):
        if updates.get("archived") == 1:
            raise RuntimeError("disk full")
        real_write(db_path, folder_name, updates)
    monkeypatch.setattr(database, "_write_opportunity", failing_write)
    with pytest.raises(RuntimeError, match="disk full"):
        database.update_opportunity(db, name, {"status": "Passed"})
    assert (job / name).is_dir() and not (arc / name).exists()
    assert database.get_opportunity(db, name)["archived"] == 0


def test_rollback_failure_is_reported_by_consistency_check(roots, monkeypatch):
    job, arc, db = roots
    name = _opp(db, job)
    monkeypatch.setattr(database, "_write_opportunity",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("db gone")))
    real_rename, calls = os.rename, []

    def rename_once(src, dst):  # the archive move works, the move back fails
        calls.append(src)
        if len(calls) > 1:
            raise OSError("onedrive lock")
        real_rename(src, dst)
    monkeypatch.setattr(os, "rename", rename_once)
    with pytest.raises(ArchiveError, match="could not be moved back"):
        database.update_opportunity(db, name, {"status": "Passed"})
    monkeypatch.undo()
    issues = database.check_consistency(db)
    assert [i["folder_name"] for i in issues["archive_only_active"]] == [name]


def test_repeated_done_on_archived_record_moves_nothing(roots):
    job, arc, db = roots
    name = _opp(db, job)
    database.update_opportunity(db, name, {"status": "Passed"})
    database.update_opportunity(db, name, {"status": "Rejected", "action_items": "note"})
    row = database.get_opportunity(db, name)
    assert (row["status"], row["archived"], row["action_items"]) == ("Rejected", 1, "note")
    assert (arc / name).is_dir()


def test_archived_record_refuses_active_status(roots):
    job, arc, db = roots
    name = _opp(db, job)
    database.update_opportunity(db, name, {"status": "Passed"})
    with pytest.raises(ArchiveError, match="Done is final"):
        database.update_opportunity(db, name, {"status": "Applied"})
    database.update_opportunity(db, name, {"contact_name": "Pat"})  # other fields allowed
    assert database.get_opportunity(db, name)["contact_name"] == "Pat"


def test_missing_source_folder_refuses(roots):
    job, arc, db = roots
    name = _opp(db, job, folder=False)
    with pytest.raises(ArchiveError, match="Folder not found"):
        database.update_opportunity(db, name, {"status": "Closed"})
    assert database.get_opportunity(db, name)["status"] == "Applied"


def test_existing_destination_refuses(roots):
    job, arc, db = roots
    name = _opp(db, job)
    (arc / name).mkdir(parents=True)
    with pytest.raises(ArchiveError, match="Destination already exists"):
        database.update_opportunity(db, name, {"status": "Closed"})
    assert (job / name).is_dir()


def test_path_length_refusal(roots):
    job, arc, db = roots
    name = _opp(db, job)
    long_file = "x" * (filesystem.WINDOWS_MAX_PATH - len(str(arc / name)) - 1) + ".msg"
    (job / name / long_file).write_text("m", encoding="utf-8")
    with pytest.raises(ArchiveError, match="Shorten this name"):
        database.update_opportunity(db, name, {"status": "Closed"})
    assert (job / name / long_file).exists()
    assert database.get_opportunity(db, name)["archived"] == 0


def test_archive_opportunity_requires_done(roots):
    job, arc, db = roots
    name = _opp(db, job)
    with pytest.raises(ArchiveError, match="archiving follows"):
        database.archive_opportunity(db, name)
    other = _opp(db, job, "Beta_DirIT", status="Passed")  # Done but never archived
    database.archive_opportunity(db, other)
    assert database.get_opportunity(db, other)["archived"] == 1 and (arc / other).is_dir()


def test_dashboard_counts_archived_done_rows(roots):
    job, arc, db = roots
    name = _opp(db, job)
    database.update_opportunity(db, name, {"status": "Ghosted"})
    metrics = database.get_dashboard_metrics(db)
    assert metrics["by_status"]["Ghosted"] == 1 and metrics["total"] == 0


# ── Archive root validation ─────────────────────────────────

def test_archive_root_validation(tmp_path):
    job = tmp_path / "jobs"
    for bad in (job, job / "Archive", tmp_path):
        with pytest.raises(ArchiveError):
            filesystem.validate_archive_root(job, bad)
    filesystem.validate_archive_root(job, tmp_path / "001_ArchiveJobSearch")


# ── Lock ─────────────────────────────────────────────────────

def test_lock_contention_refuses(roots):
    job, arc, db = roots
    name = _opp(db, job)
    with filesystem.fs_lock("other operation"):
        with pytest.raises(ArchiveError, match="in progress"):
            database.update_opportunity(db, name, {"status": "Closed"})
    assert not (filesystem.lock_dir() / filesystem.LOCK_FILENAME).exists()


def test_stale_lock_is_removed(monkeypatch):
    lock = filesystem.lock_dir() / filesystem.LOCK_FILENAME
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": 999999, "started": time.time() - 3600}), encoding="utf-8")
    monkeypatch.setattr(filesystem, "_process_alive", lambda pid: False)
    with filesystem.fs_lock("after crash"):
        assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_recent_lock_of_dead_process_is_not_stale(monkeypatch):
    lock = filesystem.lock_dir() / filesystem.LOCK_FILENAME
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": 999999, "started": time.time()}), encoding="utf-8")
    monkeypatch.setattr(filesystem, "_process_alive", lambda pid: False)
    with pytest.raises(ArchiveError):
        with filesystem.fs_lock("too soon"):
            pass


# ── Consistency check and repairs ────────────────────────────

def _interrupted_archive(job, arc, db):
    name = _opp(db, job)
    arc.mkdir(exist_ok=True)
    os.rename(job / name, arc / name)  # rename done, commit lost
    return name


def _hand_copied_back(job, arc, db):
    name = _opp(db, job)
    database.update_opportunity(db, name, {"status": "Ghosted"})
    os.rename(arc / name, job / name)
    return name


def test_repair_complete_archive(roots):
    job, arc, db = roots
    name = _interrupted_archive(job, arc, db)
    database.repair_complete_archive(db, name, "Ghosted")
    row = database.get_opportunity(db, name)
    assert (row["status"], row["archived"]) == ("Ghosted", 1)
    assert not any(database.check_consistency(db).values())


def test_repair_restore(roots):
    job, arc, db = roots
    name = _interrupted_archive(job, arc, db)
    database.repair_restore(db, name)
    assert (job / name).is_dir() and database.get_opportunity(db, name)["status"] == "Applied"
    assert not any(database.check_consistency(db).values())


def test_repair_return_to_archive(roots):
    job, arc, db = roots
    name = _hand_copied_back(job, arc, db)
    assert [i["folder_name"] for i in database.check_consistency(db)["active_only_archived"]] == [name]
    database.repair_return_to_archive(db, name)
    assert (arc / name).is_dir() and database.get_opportunity(db, name)["status"] == "Ghosted"
    assert not any(database.check_consistency(db).values())


def test_repair_reactivate(roots):
    job, arc, db = roots
    name = _hand_copied_back(job, arc, db)
    with pytest.raises(ValueError):
        database.repair_reactivate(db, name, "Passed")
    database.repair_reactivate(db, name, "Interviewing")
    row = database.get_opportunity(db, name)
    assert (row["status"], row["archived"]) == ("Interviewing", 0)
    assert not any(database.check_consistency(db).values())


def test_repair_refuses_when_case_changed(roots):
    job, arc, db = roots
    name = _opp(db, job)  # consistent
    with pytest.raises(ArchiveError, match="changed since the check"):
        database.repair_restore(db, name)


def test_both_or_neither_reported(roots):
    job, arc, db = roots
    _opp(db, job, "Gone_DirIT", folder=False)
    both = _opp(db, job, "Twin_DirIT")
    (arc / both).mkdir(parents=True)
    names = [i["folder_name"] for i in database.check_consistency(db)["both_or_neither"]]
    assert names == ["Gone_DirIT", "Twin_DirIT"]


def test_folder_with_no_record_reported(roots):
    job, arc, db = roots
    _opp(db, job)
    (job / "Orphan_DirIT").mkdir()
    (job / "00_Networking Events").mkdir()  # not Company_Role: ignored
    arc.mkdir()
    (arc / "OldOrphan_DirIT").mkdir()
    names = [i["folder_name"] for i in database.check_consistency(db)["folder_no_record"]]
    assert names == ["Orphan_DirIT", "OldOrphan_DirIT"]


# ── rebuild_index ────────────────────────────────────────────

def test_rebuild_skips_archived_name_and_reports_consistency(roots):
    job, arc, db = roots
    name = _hand_copied_back(job, arc, db)
    report = database.rebuild_index(db, str(job))
    assert any("matches an archived record" in w for w in report["warnings"])
    assert any("record archived" in w for w in report["warnings"])
    row = database.get_opportunity(db, name)
    assert (row["status"], row["archived"]) == ("Ghosted", 1)


# ── Folder-name reuse ────────────────────────────────────────

def test_unique_folder_name_suffixes_case_insensitive():
    today = date(2026, 10, 28)
    taken = {"acme_directorit", "Acme_DirectorIT_2026-10"}
    assert filesystem.unique_folder_name("Acme_DirectorIT", taken, today) == "Acme_DirectorIT_2026-10-2"
    assert filesystem.unique_folder_name("New_Role", taken, today) == "New_Role"
    long_base = "A" * 30 + "_" + "B" * 29  # 60 characters
    name = filesystem.unique_folder_name(long_base, {long_base}, today)
    assert len(name) == 60 and name.endswith("_2026-10")


def test_create_reuses_archived_name_with_suffix(roots):
    job, arc, db = roots
    name = _opp(db, job)
    database.update_opportunity(db, name, {"status": "Rejected"})
    new = database.create_opportunity_with_folder(
        db, {"company_name": "Acme", "role_title": "Director IT", "status": "Analyzing"},
        lambda root, n: filesystem.create_opportunity_folder(str(root), n),
    )
    assert new == f"{name}_{date.today():%Y-%m}"
    assert (job / new).is_dir()
    assert database.get_opportunity(db, name)["archived"] == 1  # history kept


def test_promote_never_deletes_archived_history(roots):
    """Regression: promote used to DELETE a row whose folder was missing
    from the job search root, which after archiving is every archived row."""
    job, arc, db = roots
    name = _opp(db, job)
    database.update_opportunity(db, name, {"status": "Ghosted"})
    with database._connect(db) as conn:
        cur = conn.execute(
            "INSERT INTO quick_fit_log (timestamp, source_channel, company_name, role_title, "
            "role_level, location_remote_status, opportunity_type, quick_fit, decision, "
            "primary_pass_reason) VALUES ('2026-10-28T00:00:00Z', 'linkedin', 'Acme', "
            "'Director IT', 'Director', 'remote', 'job', 'strong', 'pursue', NULL)"
        )
        conn.commit()
        qfl_id = cur.lastrowid
    result = database.promote_quick_fit(db, qfl_id)
    assert result["folder_name"] == f"{name}_{date.today():%Y-%m}"
    assert database.get_opportunity(db, name)["status"] == "Ghosted"


def test_process_alive_sees_current_process():
    # On Windows this exercises the OpenProcess / GetExitCodeProcess path
    assert filesystem._process_alive(os.getpid())
    assert not filesystem._process_alive(0)
