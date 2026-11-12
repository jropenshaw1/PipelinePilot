"""ADR-015 end to end with a fake client (synthetic fixtures, no network)."""
import json
from types import SimpleNamespace as NS

import pytest
from docx import Document

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
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


RES = "resume_Acme.docx"
TRACE = f"{fae.TRACE_DIR}/{fae.TRACE_PREFIX}resume_Acme.md"


def test_tailored_run_publishes_resume_and_trace(env):
    master, folder, pool, inv = env
    out = gen(env, Client(echo(inv)))
    assert out["state"] == "tailored" and out["outcome"] == "published"
    assert files(folder) == [TRACE, RES]
    assert out["trace"] == folder / TRACE and out["warning"] is False
    assert "**run_id:** `" in out["trace"].read_text(encoding="utf-8")   # the run_id lives in the trace only
    assert "run_id" not in (Document(str(out["resume"])).core_properties.comments or "")
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


def test_request_sends_master_length_beside_every_ceiling(env):
    """Amendment 2 F6 (Lexi N-3): the ceiling is not presented as a target."""
    master, folder, pool, inv = env
    c = Client(echo(inv))
    gen(env, c)
    assert "max_characters is a hard ceiling, not a target." in c.calls[0]["system"][0]["text"]
    body = c.calls[0]["messages"][-1]["content"]
    payload = json.loads(body[body.index("{"):body.index("\n\nFIT ANALYSIS")])
    for key in ("headline", "subtitle", "summary_paragraph"):
        assert payload[f"{key}_master_characters"] == len(payload[key]) <= payload[f"{key}_max_characters"]
    paras = payload["summary_bullets"] + [b for r in payload["roles"] for b in r["master_bullets"]]
    assert paras and all(p["master_characters"] == len(p["text"]) <= p["max_characters"] for p in paras)
    for c_ in payload["competencies"]:
        assert c_["master_characters"] == len(c_["label"] + ": " + " | ".join(c_["terms"])) <= c_["max_characters"]
    for r, m in zip(payload["roles"], inv["roles"]):
        assert r["master_total_characters"] == sum(len(b["text"]) for b in m["bullets"])
        assert "master_characters" not in r  # one name, one meaning


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


def test_length_revert_makes_the_run_partial_and_still_publishes(env, monkeypatch):
    """Amendment 2: length alone never produces master-copy."""
    master, folder, pool, inv = env
    real = fae.validate_tailoring

    def lengthen(inventory, pl, tailored):
        res = real(inventory, pl, tailored)
        b = res["roles"][0]["bullets"][0]
        b.update(text=b["text"] + " x" * 200, status="retuned", master_id=None)
        return res

    monkeypatch.setattr(fae, "validate_tailoring", lengthen)
    out = gen(env, Client(echo(inv)))
    assert out["state"] == "partial" and out["outcome"] == "published"
    # Lexi N-5: what was published, not only the state
    exact = inv["roles"][0]["bullets"][0]["text"]
    assert _role_bullets(out["resume"], inv["roles"][0]["company_line"], 2)[0] == exact
    assert "**length capacity:** 1 revert(s)" in out["trace"].read_text(encoding="utf-8")


def test_final_invariant_failure_publishes_master_copy_and_names_it(env, monkeypatch):
    """Amendment 2 F3: a failed final check fails closed and the message says which check."""
    master, folder, pool, inv = env

    def fail(*a, **k):
        raise fae.FinalInvariantError("role 0 bullet 1 over its paired capacity")

    monkeypatch.setattr(fae, "check_final_invariants", fail)
    out = gen(env, Client(echo(inv)))
    assert out["state"] == "master-copy" and out["outcome"] == "published"
    assert "final invariant failed: role 0 bullet 1 over its paired capacity" in out["message"]
    assert "role 0 bullet 1 over its paired capacity" in out["trace"].read_text(encoding="utf-8")  # Lexi NB7e


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
    gen(env, Client(echo(inv)))
    old = (folder / RES).read_bytes(), (folder / TRACE).read_text(encoding="utf-8")

    def denied(src, dst):
        raise OSError("access denied")

    monkeypatch.setattr(fae, "_replace", denied)
    out = gen(env, Client(echo(inv)))
    monkeypatch.undo()
    assert out["outcome"] == "publication-failed" and out["resume"] is None and out["warning"] is True
    assert files(folder) == [TRACE, RES]                 # no .new file left behind
    assert ((folder / RES).read_bytes(), (folder / TRACE).read_text(encoding="utf-8")) == old


def test_trace_write_failure_publishes_resume_and_reports_no_trace(env, monkeypatch):
    master, folder, pool, inv = env
    real = fae._replace

    def trace_fails(src, dst):
        if str(src).endswith(".md.new"):
            raise OSError("disk full")
        real(src, dst)

    monkeypatch.setattr(fae, "_replace", trace_fails)
    out = gen(env, Client(echo(inv)))
    monkeypatch.undo()
    assert out["outcome"] == "published" and out["resume"] == folder / RES and out["trace"] is None
    assert out["warning"] is True and "trace not written" in out["message"]
    assert files(folder) == [RES]


# The SDK tests below take the api_error fixture (conftest.py), which skips only them. A
# module-level importorskip("httpx") here skipped every test in this file wherever httpx
# was missing, as it is under anthropic SDK 1.0 (found 2026-11-01).

def test_tailoring_stage_model_not_found_gives_master_copy_with_guidance(env, api_error):
    master, folder, pool, inv = env
    e = api_error("NotFoundError", 404, "model: claude-gone-1")
    out = gen(env, Client(exc=e), model="claude-gone-1")
    assert out["state"] == "master-copy" and out["outcome"] == "published"
    assert "Settings → JFA Model" in out["message"]


def test_tailoring_stage_not_found_with_failed_publication_keeps_previous_pair(env, monkeypatch, api_error):
    master, folder, pool, inv = env
    gen(env, Client(echo(inv)))
    old = (folder / RES).read_bytes()
    e = api_error("NotFoundError", 404, "gone")

    def denied(src, dst):
        raise OSError("access denied")

    monkeypatch.setattr(fae, "_replace", denied)
    out = gen(env, Client(exc=e), model="claude-gone-1")
    monkeypatch.undo()
    assert out["outcome"] == "publication-failed" and "JFA Model" in out["message"]
    assert (folder / RES).read_bytes() == old


# ── Amendment 2 F10: the round-2 regressions end to end ──

def _line(n, words):
    """A bullet of exactly n characters: 'Built' and lower-case words, so it carries no
    named term or number and passes the lexical checks against any 'Built' source."""
    s = "Built"
    while len(s) < n:
        s += " " + words[len(s) % len(words)]
    s = s[:n - 1]
    return (s[:-1] + "x" if s.endswith(" ") else s) + "."


def _role_bullets(path, company_line, count):
    from docx import Document
    paras = [p.text for p in Document(str(path)).paragraphs]
    start = paras.index(company_line) + 1
    return paras[start:start + count]


def test_r1_padded_master_echo_publishes_tailored_with_exact_text(env):
    """R1: a master bullet echoed with extra spaces took its master ID and kept the padded
    text; once that text was over capacity, capacity raised with every bullet at master
    text and the run published master-copy. It now publishes the exact master text."""
    master, folder, pool, inv = env
    t = echo(inv)
    exact = inv["roles"][0]["bullets"][0]["text"]
    padded = exact.replace(" ", " " * 30)
    assert len(padded) > fae.slot_capacity(len(exact))  # the R1 condition
    t["roles"][0]["bullets"][0]["text"] = padded
    out = gen(env, Client(t))
    assert out["state"] == "tailored" and out["outcome"] == "published"
    assert _role_bullets(out["resume"], inv["roles"][0]["company_line"], 2)[0] == exact


def test_r2_minimized_role_holds_a3_after_capacity_and_publishes(tmp_path):
    """R2 (Gee): masters 180/90/50 in a role kept out of the summary, rewrites 140/95/80.
    Capacity restorations used to lift the role over its 320-character master total; the
    combined step holds both limits and the run publishes partial, not master-copy."""
    a, b = "the shared platform for every region and team".split(), "our core services across all sites".split()
    masters = [_line(180, a), _line(90, a), _line(50, a)]
    roles = [("Director, Platform Engineering", "Example Corp | Phoenix, AZ | 2020 - 2024", masters),
             ("Manager, Systems", "Sample Inc. | Tempe, AZ | 2015 - 2020", ["Ran release management for two platforms."])]
    master = make_master(tmp_path / "Master.docx", roles=roles)
    folder = tmp_path / "Acme_Director"
    folder.mkdir()
    role_map = ROLE_MAP.replace('  company_line: "Example Corp | Phoenix, AZ | 2020 - 2024"\n',
                                '  company_line: "Example Corp | Phoenix, AZ | 2020 - 2024"\n  in_summary: false\n')
    pool = make_pool(tmp_path, {}, role_map=role_map)
    inv = fae.parse_master_resume(master)
    assert [len(x["text"]) for x in inv["roles"][0]["bullets"]] == [180, 90, 50]
    assert fae.load_resume_pool(pool, inv)["summary_excluded_roles"] == {0}
    t = echo(inv)
    t["roles"][0]["bullets"] = [{"text": _line(n, b), "source_ids": [f"M:0:{j}"]}
                                for j, n in enumerate((140, 95, 80))]
    checked = fae.validate_tailoring(inv, fae.load_resume_pool(pool, inv), t)
    assert [x["status"] for x in checked["roles"][0]["bullets"]] == ["retuned"] * 3  # not rejected upstream
    out = gen((master, folder, pool, inv), Client(t))
    assert out["state"] == "partial" and out["outcome"] == "published"
    published = _role_bullets(out["resume"], roles[0][1], 3)
    assert sum(len(x) for x in published) <= 320
    assert published == masters  # every rewrite was restored by capacity or A3
    trace = out["trace"].read_text(encoding="utf-8")
    assert "A3" in trace and "master-copy" not in trace


def test_owner_prefix_names_resume_and_trace(env):
    """ADR-015 amendment (2026-11-04): short upload names; the trace is named for its resume."""
    master, folder, pool, inv = env
    out = fae.generate_tailored_resume(
        RESULT, "Acme Health & Co.", "Director", folder, str(master), client=Client(echo(inv)),
        model="claude-test-1", jd_text="We want platforms.", resume_pool_path=str(pool),
        file_owner="Openshaw")
    assert out["outcome"] == "published"
    assert files(folder) == ["_review/TRACE_DO-NOT-UPLOAD-openshaw_resume_AcmeHealthCo.md",
                             "openshaw_resume_AcmeHealthCo.docx"]
    assert fae.folder_resume_problems(folder) == []
