"""ADR-015 §5.1: startup check reports interrupted or mismatched resume/trace pairs (report only)."""
import json

import database
import fit_analysis_engine as fae
from test_archive import _opp, roots  # noqa: F401  (fixture)
from test_resume_sources import make_master

RES, TR = "Resume_Acme_DirectorIT.docx", "ResumeTrace_Acme_DirectorIT.md"
A, B = "20261030T000000Z-0000000a", "20261031T000000Z-0000000b"


def pair(folder, master, resume_id, trace_id):
    fae.master_copy_resume(master, folder / RES, resume_id)
    (folder / TR).write_text(f"**run_id:** `{trace_id}`\n", encoding="utf-8")


def test_clean_pair_and_pre_adr015_folder_are_not_reported(roots, tmp_path):
    job, arc, db = roots
    name = _opp(db, job)
    master = make_master(tmp_path / "m.docx")
    fae.master_copy_resume(master, job / name / RES, A)       # resume only: older run
    assert database.check_consistency(db)["resume_pair"] == []
    pair(job / name, master, A, A)
    assert not any(database.check_consistency(db).values())


def test_mismatched_pair_is_reported(roots, tmp_path):
    job, arc, db = roots
    name = _opp(db, job)
    pair(job / name, make_master(tmp_path / "m.docx"), A, B)
    items = database.check_consistency(db)["resume_pair"]
    assert [(i["folder_name"], i["status"]) for i in items] == [(name, "resume and trace from different runs")]
    assert "Resume and trace need attention" in database.consistency_lines(database.check_consistency(db))[0]


def test_interrupted_publication_is_reported(roots):
    job, arc, db = roots
    name = _opp(db, job)
    (job / name / fae.PUBLISH_JOURNAL).write_text(json.dumps({"run_id": A}), encoding="utf-8")
    items = database.check_consistency(db)["resume_pair"]
    assert [i["status"] for i in items] == ["interrupted resume publication"]


def test_archived_folder_is_checked_in_the_archive(roots, tmp_path):
    job, arc, db = roots
    name = _opp(db, job)
    pair(job / name, make_master(tmp_path / "m.docx"), A, B)
    database.update_opportunity(db, name, {"status": "Passed"})   # archives the folder
    assert (arc / name / TR).exists()
    assert [i["folder_name"] for i in database.check_consistency(db)["resume_pair"]] == [name]


def test_trace_without_resume_is_reported(roots):
    job, arc, db = roots
    name = _opp(db, job)
    (job / name / TR).write_text(f"**run_id:** `{A}`\n", encoding="utf-8")
    assert [i["status"] for i in database.check_consistency(db)["resume_pair"]] == ["resume trace without its resume"]


def test_pool_path_setting_defaults_blank():
    import config
    from models import RESUME_POOL_PATH_KEY
    assert config.DEFAULTS[RESUME_POOL_PATH_KEY] == ""
