"""ADR-016 Decision 4: model-unavailable handling. Needs the anthropic SDK
for its real error classes; skipped where it is not installed."""
import pytest

import fit_analysis_engine as fae

anthropic = pytest.importorskip("anthropic")
httpx = pytest.importorskip("httpx")


def _api_error(cls, status, text_):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(text_, response=httpx.Response(status, request=req), body=None)


def test_not_found_gives_model_setting_message():
    e = _api_error(anthropic.NotFoundError, 404, "model: claude-gone-1")
    msg_ = fae._error_message(e, "claude-gone-1")
    assert msg_ == fae.model_unavailable_message("claude-gone-1")
    assert "Settings → JFA Model" in msg_


def test_400_mentioning_model_is_a_request_error():
    e = _api_error(anthropic.BadRequestError, 400,
                   "temperature is not supported for this model: claude-test-1")
    msg_ = fae._error_message(e, "claude-test-1")
    assert "JFA Model" not in msg_
    assert "temperature is not supported" in msg_


def test_other_errors_keep_their_messages():
    assert fae._error_message(RuntimeError("boom"), "m") == "boom"
    e = _api_error(anthropic.RateLimitError, 429, "slow down")
    assert fae._error_message(e, "m").startswith("Rate limit reached")


def test_analysis_stage_not_found_writes_no_artifacts(tmp_path, monkeypatch):
    """Analysis-call unavailability stops before any artifact is generated."""
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    (folder / "JD_Acme_Director.txt").write_text("j" * 300, encoding="utf-8")
    resume = tmp_path / "resume.md"
    resume.write_text("r" * 300, encoding="utf-8")
    before = sorted(p.name for p in folder.iterdir())

    def raise_not_found(*a, **k):
        raise _api_error(anthropic.NotFoundError, 404, "model not found")

    monkeypatch.setattr(fae.vault, "get_secret", lambda *a, **k: "key")
    monkeypatch.setattr(fae.database, "get_opportunity",
                        lambda db, name: {"company_name": "Acme", "role_title": "Director",
                                          "job_url": None, "status": "New"})
    monkeypatch.setattr(fae, "_call_api", raise_not_found)
    errors, done = [], []
    t = fae.run_fit_analysis(tmp_path / "x.db", str(tmp_path), "Acme_Director", str(resume), 0.65,
                             on_success=lambda r, f: done.append(f), on_error=errors.append,
                             model="claude-gone-1")
    t.join(10)
    assert errors == [fae.model_unavailable_message("claude-gone-1")]
    assert not done
    assert sorted(p.name for p in folder.iterdir()) == before
