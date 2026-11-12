"""ADR-015 Amendment 6 E3: the startup check reports a trace whose resume is missing (report only)."""
import database
import fit_analysis_engine as fae
from test_archive import _opp, roots  # noqa: F401  (fixture)
from test_resume_sources import make_master

RES = "Resume_Acme_DirectorIT.docx"
TR = f"{fae.TRACE_DIR}/{fae.LEGACY_TRACE_PREFIX}Acme_DirectorIT.md"
A = "20261030T000000Z-0000000a"


def trace(folder):
    (folder / fae.TRACE_DIR).mkdir(exist_ok=True)
    (folder / TR).write_text(f"**run_id:** `{A}`\n", encoding="utf-8")


def test_pair_and_pre_adr015_folder_are_not_reported(roots, tmp_path):
    job, arc, db = roots
    name = _opp(db, job)
    master = make_master(tmp_path / "m.docx")
    fae.master_copy_resume(master, job / name / RES)          # resume only: older run
    assert database.check_consistency(db)["resume_pair"] == []
    trace(job / name)
    assert not any(database.check_consistency(db).values())


def test_missing_resume_is_reported_with_the_report_line(roots):
    job, arc, db = roots
    name = _opp(db, job)
    trace(job / name)
    items = database.check_consistency(db)["resume_pair"]
    assert [(i["folder_name"], i["status"]) for i in items] == [(name, "resume trace without its resume")]
    assert "Resume and trace need attention" in database.consistency_lines(database.check_consistency(db))[0]


def test_archived_folder_is_checked_in_the_archive(roots):
    job, arc, db = roots
    name = _opp(db, job)
    trace(job / name)
    database.update_opportunity(db, name, {"status": "Passed"})   # archives the folder
    assert (arc / name / TR).exists()
    assert [i["folder_name"] for i in database.check_consistency(db)["resume_pair"]] == [name]


def test_trace_without_resume_is_reported(roots):
    job, arc, db = roots
    name = _opp(db, job)
    (job / name / fae.TRACE_DIR).mkdir()
    (job / name / TR).write_text(f"**run_id:** `{A}`\n", encoding="utf-8")
    assert [i["status"] for i in database.check_consistency(db)["resume_pair"]] == ["resume trace without its resume"]


def test_pool_path_setting_defaults_blank():
    import config
    from models import RESUME_POOL_PATH_KEY
    assert config.DEFAULTS[RESUME_POOL_PATH_KEY] == ""


def test_old_flat_trace_name_is_not_paired(roots, tmp_path):
    """Traces are found only under TRACE_DIR; a flat ResumeTrace_ file is not read."""
    job, arc, db = roots
    name = _opp(db, job)
    (job / name / "ResumeTrace_Acme_DirectorIT.md").write_text(f"**run_id:** `{A}`\n", encoding="utf-8")
    assert database.check_consistency(db)["resume_pair"] == []
