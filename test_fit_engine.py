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
    with pytest.raises(RuntimeError, match="never truncated"):
        fae._apply_input_caps("x" * 500, "r" * (fae.RESUME_MAX_CHARS + 1))


def test_resume_at_cap_passes_whole():
    resume = "r" * fae.RESUME_MAX_CHARS
    _, out, _ = fae._apply_input_caps("x" * 500, resume)
    assert out == resume


def test_jd_over_cap_truncates_with_note():
    jd, _, note = fae._apply_input_caps("j" * (fae.JD_MAX_CHARS + 50), "resume")
    assert len(jd) == fae.JD_MAX_CHARS
    assert "12,000 of 12,050" in note


def test_jd_within_cap_has_no_note():
    jd, _, note = fae._apply_input_caps("j" * 100, "resume")
    assert jd == "j" * 100 and note == ""


def test_voice_ban_6_and_roster_removed():
    assert "Audio/Visual & Telecom" not in fae.SYSTEM_PROMPT
    assert "full parenthetical list" not in fae.SYSTEM_PROMPT
    assert "bans 1-5" in fae.SYSTEM_PROMPT and "bans 1-6" not in fae.SYSTEM_PROMPT


def _result(adv):
    return {"fit_score": 0.7, "advocate_case": adv, "gaps": [], "alignment": [],
            "next_steps": [], "role_summary": "", "auditor_case": "",
            "score_justification": ""}


def test_fit_analysis_md_keeps_decimal_and_writes_jd_note(tmp_path):
    adv = "Achieved 98.8% allocation accuracy across the portfolio. Built three practices from zero."
    out = fae.write_fit_analysis_md(tmp_path, "Acme", "Director", None, 0.65,
                                    _result(adv), jd_note="Job description truncated.",
                                    model="claude-test-1")
    text = out.read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---")[1])
    assert front["top_strengths"][0] == "Achieved 98.8% allocation accuracy across the portfolio"
    assert "**Input warning:** Job description truncated." in text


def test_fit_analysis_md_without_note_has_no_warning(tmp_path):
    out = fae.write_fit_analysis_md(tmp_path, "Acme", "Director", None, 0.65, _result(""),
                                    model="claude-test-1")
    assert "Input warning" not in out.read_text(encoding="utf-8")
