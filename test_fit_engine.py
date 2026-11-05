"""ADR-015 §9 and §10: input caps, sentence splitting, voice ban #6 removal."""
import pytest
import yaml

import fit_analysis_engine as fae


def test_split_keeps_decimals_whole():
    text = "Achieved 98.8% allocation accuracy across a $15M portfolio. Built three practices from zero."
    assert fae._split_sentences(text) == [
        "Achieved 98.8% allocation accuracy across a $15M portfolio.",
        "Built three practices from zero.",
    ]


def test_split_handles_empty_and_none():
    assert fae._split_sentences("") == []
    assert fae._split_sentences(None) == []


def test_top_strengths_filters_short_and_caps_at_three():
    adv = ("Short one. Reached 92.5% forecast accuracy on cloud spend. "
           "Led the datacenter exit across many teams. Founded a vendor management practice. "
           "Owned a large cost center for years.")
    out = fae._top_strengths({"advocate_case": adv})
    assert out == [
        "Reached 92.5% forecast accuracy on cloud spend",
        "Led the datacenter exit across many teams",
        "Founded a vendor management practice",
    ]


def test_resume_over_cap_fails_and_is_not_truncated():
    with pytest.raises(fae.InputLimitError, match="never truncated"):
        fae._apply_input_caps("x" * 500, "r" * (fae.RESUME_MAX_CHARS + 1))


def test_resume_at_cap_passes_whole():
    resume = "r" * fae.RESUME_MAX_CHARS
    _, out = fae._apply_input_caps("x" * 500, resume)
    assert out == resume


def test_jd_over_cap_stops_and_is_not_truncated():
    """The message format is asserted on purpose: the phrase "never truncated",
    the actual size and the limit. A boundary regression shows up here first."""
    with pytest.raises(fae.InputLimitError, match="never truncated") as e:
        fae._apply_input_caps("j" * (fae.JD_MAX_CHARS + 1), "resume")
    assert "40,001 characters; the limit is 40,000" in str(e.value)
    assert "run the assessment with Claude directly" in str(e.value)


def test_jd_at_cap_passes_whole():
    jd, _ = fae._apply_input_caps("j" * fae.JD_MAX_CHARS, "resume")
    assert jd == "j" * fae.JD_MAX_CHARS


def test_long_jd_passes_whole():
    """A 21,474-character JD was cut at 12,000 before ADR-015 Amendment 3."""
    jd, _ = fae._apply_input_caps("j" * 21474, "resume")
    assert len(jd) == 21474


def test_voice_ban_6_and_roster_removed():
    assert "Audio/Visual & Telecom" not in fae.SYSTEM_PROMPT
    assert "full parenthetical list" not in fae.SYSTEM_PROMPT
    assert "bans 1-5" in fae.SYSTEM_PROMPT and "bans 1-6" not in fae.SYSTEM_PROMPT


def _result(adv):
    return {"fit_score": 0.7, "advocate_case": adv, "gaps": [], "alignment": [],
            "next_steps": [], "role_summary": "", "auditor_case": "",
            "score_justification": ""}


def test_fit_analysis_md_keeps_decimal(tmp_path):
    adv = "Achieved 98.8% allocation accuracy across the portfolio. Built three practices from zero."
    out = fae.write_fit_analysis_md(tmp_path, "Acme", "Director", None, 0.65,
                                    _result(adv), model="claude-test-1")
    text = out.read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---")[1])
    assert front["top_strengths"][0] == "Achieved 98.8% allocation accuracy across the portfolio"
    assert "Input warning" not in text


def test_over_limit_jd_stops_run_with_no_api_call_and_no_file_changes(tmp_path, monkeypatch):
    """ADR-015 Amendment 3: the whole workflow, not only the helper."""
    pytest.importorskip("anthropic")
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    (folder / "JD_Acme_Director.txt").write_text("j" * (fae.JD_MAX_CHARS + 1), encoding="utf-8")
    (folder / "Resume_Acme_Director.docx").write_bytes(b"previous resume")
    (folder / "fit_analysis.md").write_text("previous analysis", encoding="utf-8")
    resume = tmp_path / "resume.md"
    resume.write_text("r" * 300, encoding="utf-8")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    calls = []
    monkeypatch.setattr(fae.vault, "get_secret", lambda *a, **k: calls.append("vault") or "key")
    monkeypatch.setattr(fae.database, "get_opportunity",
                        lambda db, name: {"company_name": "Acme", "role_title": "Director",
                                          "job_url": None, "status": "New"})
    monkeypatch.setattr(fae, "_call_api", lambda *a, **k: calls.append("analysis"))
    monkeypatch.setattr(fae, "tailor_resume", lambda *a, **k: calls.append("tailor"))
    errors, done = [], []
    t = fae.run_fit_analysis(tmp_path / "x.db", str(tmp_path), "Acme_Director", str(resume), 0.65,
                             on_success=lambda r, f: done.append(f), on_error=errors.append,
                             model="claude-test-1")
    t.join(10)
    assert calls == [] and not done  # no vault call, no analysis call, no tailoring call
    assert len(errors) == 1 and "40,001 characters; the limit is 40,000" in errors[0]
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()} == before


def test_successful_run_sends_the_identical_full_jd_to_both_calls(tmp_path, monkeypatch):
    """ADR-015 Amendment 3: the analysis call and the tailoring call each
    receive exactly the JD text loaded from the file, with no truncation."""
    pytest.importorskip("anthropic")
    jd = ("Requirements section at the end. " * 700)[:21474]
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    (folder / "JD_Acme_Director.txt").write_text(jd, encoding="utf-8")
    resume = tmp_path / "resume.md"
    resume.write_text("r" * 300, encoding="utf-8")
    (tmp_path / "resume.docx").write_bytes(b"master docx placeholder")
    seen = {}

    def analysis(client, jd_text, *a, **k):
        seen["analysis"] = jd_text
        return _result("Led the datacenter exit across many teams.")

    def tailor(client, inv, pool, jd_text, *a, **k):
        seen["tailor"] = jd_text
        raise RuntimeError("stop after the tailoring boundary")

    monkeypatch.setattr(fae.vault, "get_secret", lambda *a, **k: "key")
    monkeypatch.setattr(fae.database, "get_opportunity",
                        lambda db, name: {"company_name": "Acme", "role_title": "Director",
                                          "job_url": None, "status": "New"})
    monkeypatch.setattr(fae.database, "update_opportunity", lambda *a, **k: None)
    monkeypatch.setattr(fae, "_call_api", analysis)
    monkeypatch.setattr(fae, "tailor_resume", tailor)
    monkeypatch.setattr(fae, "parse_master_resume", lambda path: {})
    monkeypatch.setattr(fae, "master_copy_resume",
                        lambda master, out, run_id: out.write_bytes(b"copy"))
    monkeypatch.setattr(fae, "write_resume_trace",
                        lambda path, **k: path.write_text("trace", encoding="utf-8"))
    for name in ("generate_fit_summary", "generate_cover_letter", "generate_interview_guide"):
        monkeypatch.setattr(fae, name, lambda *a, **k: None)
    errors, done = [], []
    t = fae.run_fit_analysis(tmp_path / "x.db", str(tmp_path), "Acme_Director", str(resume), 0.65,
                             on_success=lambda r, f: done.append(f), on_error=errors.append,
                             model="claude-test-1")
    t.join(10)
    assert errors == [] and len(done) == 1
    assert len(jd) == 21474
    assert seen["analysis"] == jd and seen["tailor"] == jd


def test_run_passes_file_owner_to_cover_letter_and_resume(tmp_path, monkeypatch):
    """ADR-015 Amendment 5: the file_owner setting reaches both upload-file generators."""
    pytest.importorskip("anthropic")
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    (folder / "JD_Acme_Director.txt").write_text("We want platforms. " * 20, encoding="utf-8")
    resume = tmp_path / "resume.md"
    resume.write_text("r" * 300, encoding="utf-8")
    seen = {}

    def cover_letter(result, company, role, folder_path, file_owner=""):
        seen["cover_letter"] = file_owner

    def tailored(*a, file_owner="", **k):
        seen["resume"] = file_owner
        return {"resume": None, "trace": None, "state": "master-copy", "retuned": 0,
                "outcome": "published", "message": "stub"}

    monkeypatch.setattr(fae.vault, "get_secret", lambda *a, **k: "key")
    monkeypatch.setattr(fae.database, "get_opportunity",
                        lambda db, name: {"company_name": "Acme", "role_title": "Director",
                                          "job_url": None, "status": "New"})
    monkeypatch.setattr(fae.database, "update_opportunity", lambda *a, **k: None)
    monkeypatch.setattr(fae, "_call_api", lambda *a, **k: _result("Led the datacenter exit across many teams."))
    monkeypatch.setattr(fae, "generate_cover_letter", cover_letter)
    monkeypatch.setattr(fae, "generate_tailored_resume", tailored)
    for name in ("generate_fit_summary", "generate_interview_guide"):
        monkeypatch.setattr(fae, name, lambda *a, **k: None)
    errors, done = [], []
    t = fae.run_fit_analysis(tmp_path / "x.db", str(tmp_path), "Acme_Director", str(resume), 0.65,
                             on_success=lambda r, f: done.append(f), on_error=errors.append,
                             model="claude-test-1", file_owner="openshaw")
    t.join(10)
    assert errors == [] and len(done) == 1
    assert seen == {"cover_letter": "openshaw", "resume": "openshaw"}
