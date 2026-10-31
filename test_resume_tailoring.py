"""ADR-015 end to end with a fake client (synthetic fixtures, no network)."""
import json
from types import SimpleNamespace as NS

import pytest

import fit_analysis_engine as fae
from test_resume_sources import ROLE_MAP, item, make_master, make_pool

RESULT = {"alignment": [{"area": "Cloud", "detail": "x"}], "gaps": [{"area": "K8s", "severity": "minor", "detail": "y"}]}


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class Client:
    def __init__(self, payload=None, exc=None, raw=None):
        self.payload, self.exc, self.raw, self.calls = payload, exc, raw, []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        text = self.raw if self.raw is not None else json.dumps(self.payload)
        return _Stream(NS(content=[NS(type="thinking", thinking="", signature="s"), NS(type="text", text=text)],
                          stop_reason="end_turn"))


def echo(inv):
    return {
        "headline": "Technology Leader | Platforms",
        "subtitle": inv["subtitle"]["text"],
        "summary_paragraph": inv["summary_paragraph"]["text"],
        "summary_bullets": [{"text": b["text"], "source_ids": [b["id"]]} for b in inv["summary_bullets"]],
        "competencies": [list(c["terms"]) for c in inv["competencies"]],
        "roles": [{"role_index": r["role_index"],
                   "bullets": [{"text": b["text"], "source_ids": [b["id"]]} for b in r["bullets"]]}
                  for r in inv["roles"]],
    }


@pytest.fixture
def env(tmp_path):
    master = make_master(tmp_path / "Master.docx")
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    pool = make_pool(tmp_path, {"a.md": item("a-one", "period-a", "Built a platform team from zero.")})
    inv = fae.parse_master_resume(master)
    return master, folder, pool, inv


def gen(env_, client, pool_path=None, model="claude-test-1"):
    master, folder, pool, inv = env_
    return fae.generate_tailored_resume(
        RESULT, "Acme", "Director", folder, str(master), client=client, model=model,
        jd_text="We want platforms.", resume_pool_path=str(pool) if pool_path is None else pool_path)


def files(folder):
    return sorted(p.name for p in folder.iterdir())


def test_tailored_run_publishes_pair_with_matching_run_id(env):
    master, folder, pool, inv = env
    out = gen(env, Client(echo(inv)))
    assert out["state"] == "tailored" and out["outcome"] == "published"
    assert files(folder) == ["ResumeTrace_Acme_Director.md", "Resume_Acme_Director.docx"]
    assert fae.resume_run_id(out["resume"]) == fae.trace_run_id(out["trace"])
    assert "0 retuned items need review; published" in out["message"]


def test_request_carries_model_ceiling_inventory_and_no_prefill(env):
    master, folder, pool, inv = env
    c = Client(echo(inv))
    gen(env, c)
    kw = c.calls[0]
    assert kw["model"] == "claude-test-1" and kw["max_tokens"] == fae.MAX_TOKENS
    assert kw["messages"][-1]["role"] == "user"
    body = kw["messages"][-1]["content"]
    assert '"max_bullets": 2' in body and "a-one" in body and "We want platforms." in body
    assert "temperature" not in kw and "thinking" not in kw


def test_retuned_count_reported(env):
    master, folder, pool, inv = env
    t = echo(inv)
    t["roles"][0]["bullets"][1] = {"text": "Cut cloud costs 20% in one year.", "source_ids": ["M:0:1"]}
    out = gen(env, Client(t))
    assert out["state"] == "tailored" and out["retuned"] == 1
    assert "1 retuned item need review" in out["message"]


@pytest.mark.parametrize("client, why", [
    (Client(raw="not json at all"), "not valid JSON"),
    (Client(raw="[1, 2]"), "not a JSON object"),
    (Client(exc=RuntimeError("socket closed")), "socket closed"),
])
def test_api_or_json_failure_publishes_master_copy(env, client, why):
    master, folder, pool, inv = env
    out = gen(env, client)
    assert out["state"] == "master-copy" and out["outcome"] == "published"
    assert why in out["message"]
    trace = out["trace"].read_text(encoding="utf-8")
    assert "**state:** master-copy" in trace and why in trace


def test_load_error_publishes_master_copy_without_calling_the_api(env, tmp_path):
    master, folder, pool, inv = env
    (pool / "role_map.yaml").write_text("period-a:\n  title: Nobody\n  company_line: X | 2000\n", encoding="utf-8")
    c = Client(echo(inv))
    out = gen(env, c)
    assert out["state"] == "master-copy" and "tailoring source not loaded" in out["message"]
    assert c.calls == []


def test_blank_pool_path_tailors_from_master_alone(env):
    master, folder, pool, inv = env
    out = gen(env, Client(echo(inv)), pool_path="")
    assert out["state"] == "tailored"


def test_budget_failure_publishes_master_copy(env, monkeypatch):
    master, folder, pool, inv = env
    real = fae.apply_budget

    def overflow(inventory, res):
        real(inventory, res)
        res["budget"]["fits"] = False
        return res

    monkeypatch.setattr(fae, "apply_budget", overflow)
    out = gen(env, Client(echo(inv)))
    assert out["state"] == "master-copy" and "length budget" in out["message"]


def test_render_failure_publishes_master_copy(env, monkeypatch):
    master, folder, pool, inv = env

    def boom(*a, **k):
        raise RuntimeError("paragraph 7 is no longer a single run")

    monkeypatch.setattr(fae, "render_tailored_resume", boom)
    out = gen(env, Client(echo(inv)))
    assert out["state"] == "master-copy" and "single run" in out["message"]
    assert out["outcome"] == "published"


def test_publication_failure_keeps_previous_pair(env, monkeypatch):
    master, folder, pool, inv = env
    first = gen(env, Client(echo(inv)))
    old = fae.resume_run_id(first["resume"])

    def denied(src, dst):
        raise OSError("access denied")

    monkeypatch.setattr(fae, "_replace", denied)
    out = gen(env, Client(echo(inv)))
    monkeypatch.undo()
    assert out["outcome"] == "publication-failed" and out["resume"] is None
    assert files(folder) == ["ResumeTrace_Acme_Director.md", "Resume_Acme_Director.docx"]
    assert fae.resume_run_id(folder / "Resume_Acme_Director.docx") == old


def test_interrupted_publication_is_recovered_first(env):
    master, folder, pool, inv = env
    gen(env, Client(echo(inv)))
    (folder / fae.PUBLISH_JOURNAL).write_text(json.dumps(
        {"run_id": "20261031T000000Z-deadbeef", "phase": "replacing",
         "final": ["Resume_Acme_Director.docx", "ResumeTrace_Acme_Director.md"],
         "new": ["Resume_Acme_Director.docx.new", "ResumeTrace_Acme_Director.md.new"]}), encoding="utf-8")
    out = gen(env, Client(echo(inv)))
    assert out["outcome"] == "published"
    assert not (folder / fae.PUBLISH_JOURNAL).exists()
    assert "Previous resume restored" in out["message"]


anthropic = pytest.importorskip("anthropic")
httpx = pytest.importorskip("httpx")


def test_tailoring_stage_model_not_found_gives_master_copy_with_guidance(env):
    master, folder, pool, inv = env
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    e = anthropic.NotFoundError("model: claude-gone-1", response=httpx.Response(404, request=req), body=None)
    out = gen(env, Client(exc=e), model="claude-gone-1")
    assert out["state"] == "master-copy" and out["outcome"] == "published"
    assert "Settings → JFA Model" in out["message"]


def test_tailoring_stage_not_found_with_failed_publication_keeps_previous_pair(env, monkeypatch):
    master, folder, pool, inv = env
    first = gen(env, Client(echo(inv)))
    old = fae.resume_run_id(first["resume"])
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    e = anthropic.NotFoundError("gone", response=httpx.Response(404, request=req), body=None)

    def denied(src, dst):
        raise OSError("access denied")

    monkeypatch.setattr(fae, "_replace", denied)
    out = gen(env, Client(exc=e), model="claude-gone-1")
    monkeypatch.undo()
    assert out["outcome"] == "publication-failed" and "JFA Model" in out["message"]
    assert fae.resume_run_id(folder / "Resume_Acme_Director.docx") == old
