"""ADR-015 amendment (2026-11-04): short upload-ready resume and cover letter names,
and trace pairing for both the short names and the older Resume_{Company}_{Role} names."""
import config
import fit_analysis_engine as fae
from models import FILE_OWNER_KEY
from test_resume_sources import make_master

A, B = "20261030T000000Z-0000000a", "20261031T000000Z-0000000b"


def test_names_with_and_without_owner():
    assert fae.upload_file_name("resume", "GE Aerospace", "Openshaw") == "openshaw_resume_GEAerospace.docx"
    assert fae.upload_file_name("coverletter", "GE Aerospace", "openshaw") == "openshaw_coverletter_GEAerospace.docx"
    assert fae.upload_file_name("resume", "GE Aerospace") == "resume_GEAerospace.docx"
    assert fae.upload_file_name("resume", "GE Aerospace", "  ") == "resume_GEAerospace.docx"


def test_company_part_is_capped():
    company = "Jobgether (unnamed partner company)"
    name = fae.upload_file_name("coverletter", company, "openshaw")
    assert name == "openshaw_coverletter_Jobgetherunnamedpart.docx"
    assert len(fae.upload_file_name("coverletter", "x" * 80, "openshaw")) == 21 + fae.COMPANY_NAME_CAP + 5


def test_file_owner_setting_defaults_blank():
    assert config.DEFAULTS[FILE_OWNER_KEY] == ""


def _trace(folder, stem, run_id):
    (folder / fae.TRACE_DIR).mkdir(exist_ok=True)
    (folder / fae.TRACE_DIR / f"{fae.TRACE_PREFIX}{stem}.md").write_text(f"**run_id:** `{run_id}`\n", encoding="utf-8")


def test_short_name_pair_is_checked(tmp_path):
    master = make_master(tmp_path / "m.docx")
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    _trace(folder, "openshaw_resume_Acme", A)
    assert fae.folder_resume_problems(folder) == ["resume trace without its resume"]
    fae.master_copy_resume(master, folder / "openshaw_resume_Acme.docx", B)
    assert fae.folder_resume_problems(folder) == ["resume and trace from different runs"]
    fae.master_copy_resume(master, folder / "openshaw_resume_Acme.docx", A)
    assert fae.folder_resume_problems(folder) == []


def test_blank_owner_short_name_pair_is_checked(tmp_path):
    master = make_master(tmp_path / "m.docx")
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    _trace(folder, "resume_Acme", A)
    fae.master_copy_resume(master, folder / "resume_Acme.docx", A)
    assert fae.folder_resume_problems(folder) == []


def test_older_trace_still_pairs_with_older_resume_name(tmp_path):
    master = make_master(tmp_path / "m.docx")
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    _trace(folder, "Acme_Director", A)
    fae.master_copy_resume(master, folder / "Resume_Acme_Director.docx", A)
    assert fae.folder_resume_problems(folder) == []
    # An older resume renamed by hand at upload time is still reported until renamed back.
    (folder / "Resume_Acme_Director.docx").rename(folder / "Resume_Acme_Dir.docx")
    assert fae.folder_resume_problems(folder) == ["resume trace without its resume"]
