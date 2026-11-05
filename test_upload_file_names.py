"""ADR-015 Amendment 5 (2026-11-04): short upload-ready resume and cover letter names,
and trace pairing for both the short names and the older Resume_{Company}_{Role} names."""
import pytest

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
    assert fae.upload_file_name("coverletter", company, "openshaw") == "openshaw_coverletter_Jobgetherunnamedpart.docx"
    assert len(fae.upload_file_name("coverletter", "x" * 80, "openshaw")) == 21 + fae.COMPANY_NAME_CAP + 5


def test_owner_is_capped_read_as_text_and_may_sanitize_to_blank():
    longest = fae.upload_file_name("coverletter", "x" * 80, "Jonathan Openshaw Smith")
    assert longest == "jonathanopen_coverletter_" + "x" * 20 + ".docx"
    assert len(longest) == fae.OWNER_NAME_CAP + 1 + 11 + 1 + fae.COMPANY_NAME_CAP + 5 == 50
    assert fae.upload_file_name("resume", "Acme", 123) == "123_resume_Acme.docx"
    assert fae.upload_file_name("resume", "Acme", "!!!") == "resume_Acme.docx"
    assert fae.upload_file_name("resume", "Acme", None) == "resume_Acme.docx"


def test_file_owner_setting_defaults_blank():
    assert config.DEFAULTS[FILE_OWNER_KEY] == ""


def test_cover_letter_is_written_under_the_short_name(tmp_path):
    pytest.importorskip("docx")
    out = fae.generate_cover_letter({"cover_letter": "Dear team,\nBody.\nSincerely,"}, "GE Aerospace",
                                    "Director, Infrastructure and Platform", tmp_path, "openshaw")
    assert out == tmp_path / "openshaw_coverletter_GEAerospace.docx" and out.exists()


def _trace(folder, prefix, stem, run_id):
    (folder / fae.TRACE_DIR).mkdir(exist_ok=True)
    (folder / fae.TRACE_DIR / f"{prefix}{stem}.md").write_text(f"**run_id:** `{run_id}`\n", encoding="utf-8")


@pytest.fixture
def folder_and_master(tmp_path):
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    return folder, make_master(tmp_path / "m.docx")


def test_prefixes_cannot_collide():
    assert fae.TRACE_PREFIX != fae.LEGACY_TRACE_PREFIX
    assert not fae.TRACE_PREFIX.startswith(fae.LEGACY_TRACE_PREFIX)
    assert not fae.LEGACY_TRACE_PREFIX.startswith(fae.TRACE_PREFIX)


def test_short_name_pair_is_checked(folder_and_master):
    folder, master = folder_and_master
    _trace(folder, fae.TRACE_PREFIX, "openshaw_resume_Acme", A)
    assert fae.folder_resume_problems(folder) == ["resume trace without its resume"]
    fae.master_copy_resume(master, folder / "openshaw_resume_Acme.docx", B)
    assert fae.folder_resume_problems(folder) == ["resume and trace from different runs"]
    fae.master_copy_resume(master, folder / "openshaw_resume_Acme.docx", A)
    assert fae.folder_resume_problems(folder) == []


def test_blank_owner_short_name_pair_is_checked(folder_and_master):
    folder, master = folder_and_master
    _trace(folder, fae.TRACE_PREFIX, "resume_Acme", A)
    fae.master_copy_resume(master, folder / "resume_Acme.docx", A)
    assert fae.folder_resume_problems(folder) == []


def test_older_trace_still_pairs_with_older_resume_name(folder_and_master):
    folder, master = folder_and_master
    _trace(folder, fae.LEGACY_TRACE_PREFIX, "Acme_Director", A)
    fae.master_copy_resume(master, folder / "Resume_Acme_Director.docx", A)
    assert fae.folder_resume_problems(folder) == []
    # An older resume renamed by hand at upload time is still reported until renamed back.
    (folder / "Resume_Acme_Director.docx").rename(folder / "Resume_Acme_Dir.docx")
    assert fae.folder_resume_problems(folder) == ["resume trace without its resume"]


def test_older_pair_for_a_company_named_resume_is_not_misread(folder_and_master):
    """Review finding F1 (Gee, Grok): the earlier name-shape test read this as a short name."""
    folder, master = folder_and_master
    _trace(folder, fae.LEGACY_TRACE_PREFIX, "Resume_DirectorIT", A)
    fae.master_copy_resume(master, folder / "Resume_Resume_DirectorIT.docx", A)
    assert fae.folder_resume_problems(folder) == []


def test_short_and_older_pairs_coexist_in_one_folder(folder_and_master):
    """Review finding F1 (Gee): blank owner, company Resume, role Resume. The new
    trace name differs from the older one even ignoring case, so neither overwrites
    the other on Windows, and each pairs with its own resume."""
    folder, master = folder_and_master
    new = fae.TRACE_PREFIX + "resume_Resume.md"
    old = fae.LEGACY_TRACE_PREFIX + "Resume_Resume.md"
    assert new.lower() != old.lower()
    _trace(folder, fae.LEGACY_TRACE_PREFIX, "Resume_Resume", A)
    fae.master_copy_resume(master, folder / "Resume_Resume_Resume.docx", A)
    _trace(folder, fae.TRACE_PREFIX, "resume_Resume", B)
    fae.master_copy_resume(master, folder / "resume_Resume.docx", B)
    assert fae.folder_resume_problems(folder) == []
