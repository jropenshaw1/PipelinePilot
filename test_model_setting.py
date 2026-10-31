"""ADR-016: JFA model as a setting (fake client, no network)."""
import json
from types import SimpleNamespace as NS

import pytest

import config
import fit_analysis_engine as fae
from models import DEFAULT_JFA_MODEL, JFA_MODEL_KEY

GOOD = {"fit_score": 0.62, "advocate_case": "x", "gaps": [], "alignment": []}


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeClient:
    def __init__(self, message):
        self.message = message
        self.calls = []
        self.messages = self

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return _Stream(self.message)

    def create(self, **kwargs):  # pragma: no cover - must not be used (ADR-016 streaming)
        raise AssertionError("non-streaming create() called")


def msg(*blocks, stop="end_turn"):
    return NS(content=list(blocks), stop_reason=stop)


def text(t):
    return NS(type="text", text=t)


def thinking():
    return NS(type="thinking", thinking="", signature="sig")


def call(client, model="claude-test-1"):
    return fae._call_api(client, "jd", "resume", "Acme", "Director", model=model)


@pytest.mark.parametrize("value", [None, "", "   ", 7])
def test_blank_setting_resolves_to_default(value):
    assert fae.resolve_model(value) == DEFAULT_JFA_MODEL == "claude-opus-5-5"


def test_setting_is_trimmed():
    assert fae.resolve_model("  claude-test-1 ") == "claude-test-1"


def test_config_default_has_model():
    assert config.DEFAULTS[JFA_MODEL_KEY] == DEFAULT_JFA_MODEL


def test_configured_model_and_ceiling_reach_the_call():
    client = FakeClient(msg(text(json.dumps(GOOD))))
    call(client, model="claude-test-1")
    kw = client.calls[0]
    assert kw["model"] == "claude-test-1"
    assert kw["max_tokens"] == fae.MAX_TOKENS == 32000
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in kw
    assert kw["messages"][-1]["role"] == "user"  # no prefilled final assistant turn


def test_thinking_blocks_before_text_parse():
    client = FakeClient(msg(thinking(), thinking(), text(json.dumps(GOOD))))
    assert call(client)["fit_score"] == 0.6  # snapped to 0.05


def test_several_text_blocks_are_joined():
    raw = json.dumps(GOOD)
    client = FakeClient(msg(text(raw[:10]), thinking(), text(raw[10:])))
    assert call(client)["advocate_case"] == "x"


def test_max_tokens_stop_reports_out_of_tokens_not_json():
    client = FakeClient(msg(thinking(), text('{"fit_score": 0.'), stop="max_tokens"))
    with pytest.raises(RuntimeError, match="ran out of output tokens"):
        call(client)


def test_response_without_text_fails_clearly():
    with pytest.raises(RuntimeError, match="contained no text"):
        call(FakeClient(msg(thinking())))


def test_model_recorded_in_fit_analysis_md(tmp_path):
    result = {"fit_score": 0.7, "advocate_case": "", "gaps": [], "alignment": [], "next_steps": [],
              "role_summary": "", "auditor_case": "", "score_justification": ""}
    out = fae.write_fit_analysis_md(tmp_path, "Acme", "Director", None, 0.65, result,
                                    model="claude-test-1").read_text(encoding="utf-8")
    assert "model: claude-test-1" in out
    assert "Model: claude-test-1*" in out


def test_no_module_level_model_constant():
    assert not hasattr(fae, "MODEL")


def test_requests_are_streamed():
    """The SDK refuses non-streaming requests at this max_tokens (seen in the first live run)."""
    client = FakeClient(msg(text(json.dumps(GOOD))))
    call(client)
    assert len(client.calls) == 1  # went through stream(); create() would raise
