"""ADR-015 §7 render and trace; Amendment 6 clean document properties and simple
publication (synthetic fixtures only)."""
import re
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from pathlib import Path

from docx import Document

import fit_analysis_engine as fae
from test_resume_sources import make_master

RES, TR = "Resume_Acme_Director.docx", "ResumeTrace_Acme_Director.md"
RUN_ID_RE = re.compile(r"\*\*run_id:\*\* `([0-9TZ]+-[0-9a-f]{8})`")


def tailored_res(inv):
    pool = {"items": [], "summary_excluded_roles": set()}
    t = {
        "headline": "Technology Leader | Cloud",
        "subtitle": inv["subtitle"]["text"],
        "summary_paragraph": inv["summary_paragraph"]["text"],
        "summary_bullets": [{"text": b["text"], "source_ids": [b["id"]]} for b in inv["summary_bullets"]][:1],
        "competencies": [list(c["terms"]) for c in inv["competencies"]],
        "roles": [{"role_index": r["role_index"],
                   "bullets": [{"text": b["text"], "source_ids": [b["id"]]} for b in r["bullets"]][::-1]}
                  for r in inv["roles"]],
    }
    res = fae.validate_tailoring(inv, pool, t)
    excluded = pool.get("summary_excluded_roles", set())
    fae.apply_role_limits(inv, pool, res)
    fae.apply_capacity(inv, res, excluded)
    fae.check_final_invariants(inv, res, excluded)
    return pool, res


def texts(path):
    return [p.text for p in Document(str(path)).paragraphs if p.text.strip()]


# ── §7 render ──

def owned_master(path, author="Un-named", last_modified_by="Pat Example"):
    """A master as Word leaves it: by default a placeholder Author and the owner in
    Last Modified By, plus fields that must not reach an upload file."""
    master = make_master(path)
    doc = Document(str(master))
    cp = doc.core_properties
    cp.author, cp.last_modified_by = author, last_modified_by
    cp.comments, cp.content_status, cp.identifier, cp.version = "a note", "Draft", "id-7", "v3"
    cp.created = cp.modified = datetime(2020, 1, 2, 3, 4, 5)
    cp.revision = 9
    doc.save(str(master))
    return master


def core_xml(path):
    with zipfile.ZipFile(path) as z:
        return z.read("docProps/core.xml").decode("utf-8")


def assert_clean(path, owner):
    cp = Document(str(path)).core_properties
    assert cp.author == owner and cp.last_modified_by == owner
    assert (cp.comments, cp.title, cp.subject, cp.keywords, cp.category,
            cp.content_status, cp.identifier, cp.version) == ("",) * 8
    now = datetime.now(timezone.utc)
    for stamp in (cp.created, cp.modified):                 # not python-docx's 2013 or the master's date
        assert now - timedelta(minutes=5) <= stamp <= now + timedelta(minutes=1)
    assert cp.revision == 1
    xml = core_xml(path)
    assert "run_id" not in xml and "python-docx" not in xml and "PipelinePilot" not in xml
    assert "2013-12-23" not in xml


def test_render_changes_only_editable_text(tmp_path):
    master = make_master(tmp_path / "m.docx")
    inv = fae.parse_master_resume(master)
    _, res = tailored_res(inv)
    out = fae.render_tailored_resume(master, inv, res, tmp_path / "out.docx")
    before, after = texts(master), texts(out)
    assert after[2] == "Technology Leader | Cloud"
    assert after[0:2] == before[0:2]                      # name and contact untouched
    assert "Owned a $5M budget." not in after             # summary trimmed to one bullet
    assert after.index("Cut cloud spend 20% in one year.") < after.index("Built a platform team from zero.")
    assert after[-4:] == before[-4:]                      # portfolio, education untouched


def test_render_keeps_bullet_formatting_and_can_add_bullets(tmp_path):
    master = make_master(tmp_path / "m.docx")
    inv = fae.parse_master_resume(master)
    _, res = tailored_res(inv)
    res["summary_bullets"].append({"text": "A third summary point.", "source_ids": ["M:S:0"], "status": "retuned"})
    res["summary_bullets"].append({"text": "A fourth summary point.", "source_ids": ["M:S:1"], "status": "retuned"})
    out = fae.render_tailored_resume(master, inv, res, tmp_path / "o.docx")
    doc = Document(str(out))
    added = [p for p in doc.paragraphs if p.text in ("A third summary point.", "A fourth summary point.")]
    assert [p.text for p in added] == ["A third summary point.", "A fourth summary point."]
    assert all(p.style.name == "List Paragraph" for p in added)
    reparsed = fae.parse_master_resume(out)              # still a well-formed master shape
    assert len(reparsed["summary_bullets"]) == 3


def test_master_copy_is_unchanged(tmp_path):
    master = make_master(tmp_path / "m.docx")
    out = fae.master_copy_resume(master, tmp_path / "c.docx")
    assert texts(out) == texts(master)


# ── Amendment 6 E1: clean document properties ──

def test_tailored_resume_carries_owner_and_no_tool_trace(tmp_path):
    master = owned_master(tmp_path / "m.docx")
    inv = fae.parse_master_resume(master)
    _, res = tailored_res(inv)
    assert_clean(fae.render_tailored_resume(master, inv, res, tmp_path / "out.docx"), "Pat Example")


def test_master_copy_carries_owner_and_no_tool_trace(tmp_path):
    master = owned_master(tmp_path / "m.docx")
    assert_clean(fae.master_copy_resume(master, tmp_path / "c.docx"), "Pat Example")


def test_cover_letter_carries_owner_and_no_tool_trace(tmp_path):
    out = fae.generate_cover_letter({"cover_letter": "Dear team,\nBody.\nSincerely,"}, "Acme",
                                    "Director", tmp_path, "pat", author="Pat Example")
    assert_clean(out, "Pat Example")


def test_fit_summary_and_interview_guide_carry_owner(tmp_path):
    result = {"fit_score": 0.7, "advocate_case": "a", "auditor_case": "b", "gaps": [], "alignment": [],
              "next_steps": [], "role_summary": "", "score_justification": "", "interview_guide": []}
    for gen in (fae.generate_fit_summary, fae.generate_interview_guide):
        assert_clean(gen(result, "Acme", "Director", tmp_path, author="Pat Example"), "Pat Example")


@pytest.mark.parametrize("author, last_modified_by, owner", [
    ("Pat Example", "Resume Coach", "Pat Example"),   # Author, set by the owner, wins
    ("Un-named", "Pat Example", "Pat Example"),       # placeholder Author: Last Modified By
    ("", "Pat Example", "Pat Example"),
    ("Un-named", "", ""),                             # only a placeholder: blank, never "Un-named"
    ("UNKNOWN", "user", ""),                          # placeholders in any case
])
def test_owner_is_author_then_last_modified_by_skipping_placeholders(tmp_path, author, last_modified_by, owner):
    master = owned_master(tmp_path / "m.docx", author, last_modified_by)
    assert fae.document_author(str(master)) == owner


def test_python_docx_default_author_is_never_the_owner(tmp_path):
    master = make_master(tmp_path / "m.docx")            # python-docx defaults: Author "python-docx"
    assert fae.document_author(str(master)) == ""
    assert_clean(fae.master_copy_resume(master, tmp_path / "c.docx"), "")


def test_document_author_is_blank_when_the_master_cannot_be_read(tmp_path):
    assert fae.document_author(str(tmp_path / "missing.docx")) == ""


# ── trace ──

def test_trace_lists_retuned_items_first_with_sources(tmp_path):
    master = make_master(tmp_path / "m.docx")
    inv = fae.parse_master_resume(master)
    pool, res = tailored_res(inv)
    tr = fae.write_resume_trace(tmp_path / TR, run_id="20261031T000000Z-0123abcd", state="tailored",
                                company="Acme", role="Director", model="claude-test-1",
                                inventory=inv, pool=pool, res=res).read_text(encoding="utf-8")
    assert RUN_ID_RE.search(tr).group(1) == "20261031T000000Z-0123abcd"
    assert tr.index("## Retuned items") < tr.index("## Changes the checks made") < tr.index("## Published resume")
    assert "### headline" in tr and "- master: Technology Leader | Platforms" in tr
    assert "**retuned items:** 1" in tr


def test_trace_lists_retuned_items_by_growth_with_their_baseline(tmp_path):
    """Amendment 2 F6: largest growth first, each with its growth and baseline."""
    inv = fae.parse_master_resume(make_master(tmp_path / "m.docx"))
    pool, res = tailored_res(inv)  # headline retuned shorter than the master
    longer = "Built a platform team from zero in one year."
    b = res["roles"][0]["bullets"][0]
    b.update(text=longer, source_ids=["M:0:0"], status="retuned", master_id=None)
    tr = fae.write_resume_trace(tmp_path / TR, run_id="20261031T000000Z-0123abcd", state="tailored",
                                company="Acme", role="Director", model="m",
                                inventory=inv, pool=pool, res=res).read_text(encoding="utf-8")
    assert tr.index("### role 0 bullet 0") < tr.index("### headline")
    grow = len(longer) - len(inv["roles"][0]["bullets"][0]["text"])
    assert f"- growth: +{grow} characters (" in tr and "against source M:0:0" in tr
    shrink = len(res["headline"]["text"]) - len(inv["headline"]["text"])
    assert f"- growth: {shrink} characters (" in tr and "against master paragraph" in tr


def test_master_copy_trace_names_the_reason(tmp_path):
    fae.write_resume_trace(tmp_path / TR, run_id="20261031T000000Z-0123abcd", state="master-copy",
                           company="Acme", role="Director", model="m", inventory=None, pool=None,
                           res=None, reason="role_map.yaml not found")
    tr = (tmp_path / TR).read_text(encoding="utf-8")
    assert "**state:** master-copy" in tr and "role_map.yaml not found" in tr


def test_new_run_id_format():
    rid = fae.new_run_id()
    assert re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}", rid)


# ── Amendment 6 E2: publication, resume first ──

@pytest.fixture
def setup(tmp_path):
    master = make_master(tmp_path / "m.docx")
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    return master, folder


def stage(folder, master, label):
    """A prepared .new pair; label distinguishes runs."""
    r = fae.master_copy_resume(master, folder / (RES + ".new"))
    doc = Document(str(r))
    doc.add_paragraph(label)
    doc.save(str(r))
    t = folder / (TR + ".new")
    t.write_text(f"# trace\n\n{label}\n", encoding="utf-8")
    return r, t


def publish(folder, master, label):
    r, t = stage(folder, master, label)
    return fae.publish_resume(folder, RES, TR, r, t)


def labels(folder):
    """Which run's resume and trace are on disk, and every file name."""
    resume = texts(folder / RES)[-1] if (folder / RES).exists() else None
    trace = (folder / TR).read_text(encoding="utf-8").strip().splitlines()[-1] if (folder / TR).exists() else None
    return {p.name for p in folder.iterdir()}, resume, trace


def test_first_run_publishes_cleanly(setup):
    master, folder = setup
    assert publish(folder, master, "new") == {"outcome": "published", "detail": ""}
    assert labels(folder) == ({RES, TR}, "new", "new")


def test_rerun_replaces_both_files(setup):
    master, folder = setup
    publish(folder, master, "old")
    assert publish(folder, master, "new")["outcome"] == "published"
    assert labels(folder) == ({RES, TR}, "new", "new")


def test_first_run_resume_failure_says_no_resume_was_written(setup, monkeypatch):
    master, folder = setup
    r, t = stage(folder, master, "new")
    monkeypatch.setattr(fae, "_replace", lambda src, dst: (_ for _ in ()).throw(OSError("access denied")))
    out = fae.publish_resume(folder, RES, TR, r, t)
    assert out["outcome"] == "publication-failed" and "no resume written" in out["detail"]
    assert "previous resume kept" not in out["detail"] and not any(folder.iterdir())


def test_staging_file_that_cannot_be_removed_is_named(setup, monkeypatch):
    master, folder = setup
    r, t = stage(folder, master, "new")
    monkeypatch.setattr(fae, "_replace", lambda src, dst: (_ for _ in ()).throw(OSError("locked")))
    monkeypatch.setattr(fae, "_unlink", lambda p: (_ for _ in ()).throw(OSError("in use")))
    out = fae.publish_resume(folder, RES, TR, r, t)
    assert f"staging file left: {RES}.new, {TR}.new" in out["detail"]


def test_resume_replace_failure_changes_nothing_and_cleans_up(setup, monkeypatch):
    """The resume is open in Word: nothing is replaced and no .new file is left."""
    master, folder = setup
    publish(folder, master, "old")
    r, t = stage(folder, master, "new")

    def locked(src, dst):
        raise PermissionError("file in use")

    monkeypatch.setattr(fae, "_replace", locked)
    out = fae.publish_resume(folder, RES, TR, r, t)
    monkeypatch.undo()
    assert out["outcome"] == "publication-failed"
    assert "previous resume kept" in out["detail"] and "open in Word" in out["detail"]
    assert labels(folder) == ({RES, TR}, "old", "old")


def trace_fails(monkeypatch):
    real = fae._replace

    def replace(src, dst):
        if str(src).endswith(TR + ".new"):
            raise OSError("disk full")
        real(src, dst)

    monkeypatch.setattr(fae, "_replace", replace)


def test_trace_failure_removes_the_earlier_trace_and_says_so(setup, monkeypatch):
    """An earlier run's trace never stays beside the new resume (review round 1, Gee F4/F5)."""
    master, folder = setup
    publish(folder, master, "old")
    r, t = stage(folder, master, "new")
    trace_fails(monkeypatch)
    out = fae.publish_resume(folder, RES, TR, r, t)
    assert out["outcome"] == "published"
    assert "trace not written (disk full)" in out["detail"] and "earlier trace was removed" in out["detail"]
    assert labels(folder) == ({RES}, "new", None)


def test_first_run_trace_failure_does_not_claim_an_earlier_trace(setup, monkeypatch):
    master, folder = setup
    r, t = stage(folder, master, "new")
    trace_fails(monkeypatch)
    out = fae.publish_resume(folder, RES, TR, r, t)
    assert out["detail"] == "trace not written (disk full); no trace for this run"
    assert labels(folder) == ({RES}, "new", None)


def test_earlier_trace_that_cannot_be_removed_is_reported(setup, monkeypatch):
    master, folder = setup
    publish(folder, master, "old")
    r, t = stage(folder, master, "new")
    trace_fails(monkeypatch)
    real_unlink = fae._unlink

    def unlink(p):
        if Path(p) == folder / TR:
            raise OSError("in use")
        real_unlink(p)

    monkeypatch.setattr(fae, "_unlink", unlink)
    out = fae.publish_resume(folder, RES, TR, r, t)
    assert "is from an earlier run and could not be removed" in out["detail"]
    assert labels(folder) == ({RES, TR}, "new", "old")


# ── Amendment 6 E3: startup check pairs by name only ──

def test_pair_problem_is_only_a_trace_without_its_resume(setup):
    master, folder = setup
    assert fae.resume_pair_problem(folder, RES, TR) is None                    # neither file
    fae.master_copy_resume(master, folder / RES)
    assert fae.resume_pair_problem(folder, RES, TR) is None                    # resume, no trace
    (folder / TR).write_text("**run_id:** `20261031T000000Z-00000002`\n", encoding="utf-8")
    assert fae.resume_pair_problem(folder, RES, TR) is None                    # both
    (folder / RES).unlink()
    assert fae.resume_pair_problem(folder, RES, TR) == "resume trace without its resume"


def test_resume_edited_in_word_is_not_reported(setup):
    """The owner sets Author, clears Comments and edits text in Word before submitting."""
    master, folder = setup
    tr = f"{fae.TRACE_DIR}/{fae.TRACE_PREFIX}Acme_Director.md"
    (folder / fae.TRACE_DIR).mkdir()
    (folder / tr).write_text("**run_id:** `20261031T000000Z-00000002`\n", encoding="utf-8")
    resume = fae.master_copy_resume(master, folder / "Acme_Director.docx")
    doc = Document(str(resume))
    doc.core_properties.author = "Pat Example"
    doc.core_properties.comments = "my own note"
    doc.add_paragraph("A line added by hand.")
    doc.save(str(resume))
    assert fae.folder_resume_problems(folder) == []


def test_old_publication_journal_is_ignored(setup):
    """Amendment 6 E4: a journal file left by the removed protocol is not a report."""
    master, folder = setup
    (folder / ".resume_publish.json").write_text("{}", encoding="utf-8")
    assert fae.folder_resume_problems(folder) == []
