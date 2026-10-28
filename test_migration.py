"""ADR-014 §6: one-time archive of existing Done folders (migrations/archive_done_folders.py).

Runs against a scratch job search root, archive root and database copy; the
process check and the backup run are replaced (see the mig fixture)."""
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

import database
import filesystem

_spec = importlib.util.spec_from_file_location(
    "archive_done_folders", Path(__file__).parent / "migrations" / "archive_done_folders.py")
mig_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig_module)


@pytest.fixture
def mig(tmp_path, monkeypatch):
    job = tmp_path / "00_JobSearch"
    job.mkdir()
    db = database.get_db_path(str(job))
    database.initialize_database(db)
    arc = tmp_path / "001_ArchiveJobSearch"
    monkeypatch.setattr(mig_module, "check_processes", lambda: None)
    monkeypatch.setattr(mig_module, "run_backup", lambda: "PP_test")
    monkeypatch.setattr(mig_module, "roots", lambda: (db, job, arc))
    monkeypatch.setattr(mig_module, "LOGS_DIR", tmp_path / "logs")
    return mig_module, job, arc, db


def _opp(db, job, name, status, folder=True):
    if folder:
        (job / name).mkdir()
        (job / name / f"JD_{name}.txt").write_text("jd", encoding="utf-8")
    company, role = name.split("_", 1)
    database.create_opportunity(db, {"folder_name": name, "company_name": company,
                                     "role_title": role, "status": status})


def _archived(db, name):
    return sqlite3.connect(db).execute(
        "SELECT archived FROM opportunities WHERE folder_name = ?", (name,)).fetchone()[0]


def _manifest(tmp_root):
    path = next((tmp_root / "logs").glob("archive_manifest_*.json"))
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_dry_run_lists_done_and_flags_conflicts(mig, capsys):
    m, job, arc, db = mig
    _opp(db, job, "Done_DirIT", "Passed")
    _opp(db, job, "Live_DirIT", "Applied")
    _opp(db, job, "Gone_DirIT", "Ghosted", folder=False)
    _opp(db, job, "Twin_DirIT", "Closed")
    (arc / "Twin_DirIT").mkdir(parents=True)
    _opp(db, job, "Open_DirIT", "Rejected")
    (job / "Open_DirIT" / "~$Resume.docx").write_text("lock", encoding="utf-8")

    assert m.main([]) == 0
    out = capsys.readouterr().out
    assert "Live_DirIT" not in out
    assert "Gone_DirIT (Ghosted)  CONFLICT: source missing" in out
    assert "Twin_DirIT (Closed)  CONFLICT: destination exists" in out
    assert "Open_DirIT (Rejected)  CONFLICT: a file appears to be open" in out
    assert "4 Done folders to archive; 3 with conflicts" in out
    assert (job / "Done_DirIT").is_dir() and _archived(db, "Done_DirIT") == 0


def test_apply_moves_sets_archived_and_skips_conflicts(mig):
    m, job, arc, db = mig
    _opp(db, job, "Done_DirIT", "Passed")
    _opp(db, job, "Gone_DirIT", "Ghosted", folder=False)
    _opp(db, job, "Live_DirIT", "Applied")
    assert m.main(["--apply"]) == 1  # one conflict reported
    assert (arc / "Done_DirIT").is_dir() and not (job / "Done_DirIT").exists()
    assert _archived(db, "Done_DirIT") == 1 and _archived(db, "Gone_DirIT") == 0
    assert (job / "Live_DirIT").is_dir()
    _, manifest = _manifest(job.parent)
    states = {i["folder_name"]: i["state"] for i in manifest["items"]}
    assert states == {"Done_DirIT": "db_done", "Gone_DirIT": "pending"}
    assert manifest["backup_folder"] == "PP_test"


def test_apply_refuses_when_backup_fails(mig, monkeypatch):
    m, job, arc, db = mig
    _opp(db, job, "Done_DirIT", "Passed")

    def failed_backup():
        raise SystemExit("REFUSED: backup")
    monkeypatch.setattr(m, "run_backup", failed_backup)
    with pytest.raises(SystemExit):
        m.main(["--apply"])
    assert (job / "Done_DirIT").is_dir() and _archived(db, "Done_DirIT") == 0


def test_refuses_while_pipelinepilot_running(mig, monkeypatch, capsys):
    m, job, arc, db = mig
    _opp(db, job, "Done_DirIT", "Passed")
    monkeypatch.setattr(m, "check_processes", lambda: "Claude Desktop running")
    assert m.main(["--apply"]) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert (job / "Done_DirIT").is_dir()


def test_interrupted_apply_then_resume(mig, monkeypatch):
    m, job, arc, db = mig
    for name in ("A_DirIT", "B_DirIT", "C_DirIT"):
        _opp(db, job, name, "Passed")
    real_set = m._set_archived

    def crash_on_b(db_path, folder_name, value):
        if folder_name == "B_DirIT":
            raise sqlite3.OperationalError("database is locked")
        real_set(db_path, folder_name, value)
    monkeypatch.setattr(m, "_set_archived", crash_on_b)
    assert m.main(["--apply"]) == 1
    path, manifest = _manifest(job.parent)
    states = {i["folder_name"]: i["state"] for i in manifest["items"]}
    assert states == {"A_DirIT": "db_done", "B_DirIT": "moved", "C_DirIT": "db_done"}
    assert (arc / "B_DirIT").is_dir() and _archived(db, "B_DirIT") == 0

    monkeypatch.setattr(m, "_set_archived", real_set)
    assert m.main(["--apply", "--resume", str(path)]) == 0
    assert _archived(db, "B_DirIT") == 1
    _, manifest = _manifest(job.parent)
    assert all(i["state"] == "db_done" for i in manifest["items"])


def test_resume_finishes_an_item_stopped_before_the_rename(mig):
    m, job, arc, db = mig
    _opp(db, job, "A_DirIT", "Passed")
    mpath = filesystem.lock_dir() / "archive_manifest_x.json"
    mpath.parent.mkdir(parents=True, exist_ok=True)
    item = {"folder_name": "A_DirIT", "status": "Passed", "source": str(job / "A_DirIT"),
            "destination": str(arc / "A_DirIT"), "previous_archived": 0, "state": "intent",
            "conflicts": [], "error": None}
    mpath.write_text(json.dumps({"items": [item]}), encoding="utf-8")
    assert m.main(["--apply", "--resume", str(mpath)]) == 0
    assert (arc / "A_DirIT").is_dir() and _archived(db, "A_DirIT") == 1


def test_undo_reverses_and_skips_a_conflicting_item(mig):
    m, job, arc, db = mig
    for name in ("A_DirIT", "B_DirIT"):
        _opp(db, job, name, "Passed")
    assert m.main(["--apply"]) == 0
    path, _ = _manifest(job.parent)
    (job / "B_DirIT").mkdir()  # something now exists at B's source
    assert m.main(["--undo", str(path)]) == 1
    assert (job / "A_DirIT" / "JD_A_DirIT.txt").exists() and _archived(db, "A_DirIT") == 0
    assert (arc / "B_DirIT").is_dir() and _archived(db, "B_DirIT") == 1  # untouched
    (job / "B_DirIT").rmdir()
    assert m.main(["--undo", str(path)]) == 0  # re-run is safe
    assert (job / "B_DirIT").is_dir() and _archived(db, "B_DirIT") == 0


def test_migration_touches_no_other_column(mig):
    m, job, arc, db = mig
    _opp(db, job, "A_DirIT", "Ghosted")
    before = dict(database.get_opportunity(db, "A_DirIT"))
    assert m.main(["--apply"]) == 0
    after = dict(database.get_opportunity(db, "A_DirIT"))
    before["archived"] = 1
    assert after == before
