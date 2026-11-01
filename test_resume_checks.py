"""ADR-015 §3 to §5, Amendment 1 (A1 to A3) and Amendment 2 (length capacity): checks, fallbacks, limits.
Pure functions; the inventory is built by hand (synthetic data only)."""
import copy

import pytest

import fit_analysis_engine as fae


def B(i, text):
    return {"id": i, "index": 0, "text": text}


def inventory():
    return {
        "headline": {"index": 2, "text": "Technology Leader | Platforms and Cost"},
        "subtitle": {"index": 3, "text": "Cloud | FinOps | Operations"},
        "summary_paragraph": {"index": 5, "text": "Leader who builds reliable platforms at Example Corp."},
        "summary_bullets": [B("M:S:0", "Founded two practices from zero."),
                            B("M:S:1", "Owned a $5M budget across 10 teams.")],
        "competencies": [{"index": 9, "label": "Leadership", "terms": ["Strategy", "Team Building"]},
                         {"index": 10, "label": "Finance", "terms": ["FinOps", "Budgeting"]}],
        "roles": [
            {"role_index": 0, "title": "Director, Platform", "company_line": "Example Corp | AZ | 2020 - 2024",
             "bullets": [B("M:0:0", "Built a platform team of 12 engineers on AWS."),
                         B("M:0:1", "Cut cloud spend 20% in one year.")]},
            {"role_index": 1, "title": "Engineer", "company_line": "Old Co | AZ | 1997 - 2015",
             "bullets": [B("M:1:0", "Wrote deployment scripts in PowerShell."),
                         B("M:1:1", "Ran release management.")]},
        ],
    }


def pool(excluded=frozenset()):
    return {"items": [
        {"item_id": "p-cicd", "role_period": "old", "role_index": 1,
         "text": "Built the automated deployment path in Jenkins and PowerShell that cut outages 45%."},
        {"item_id": "p-long", "role_period": "old", "role_index": 1,
         "text": "Led a long and detailed CRM implementation across three offices with 50 sales reps."},
        {"item_id": "p-cmdb", "role_period": "dir", "role_index": 0,
         "text": "Founded the CMDB across ~2,000 servers."},
        {"item_id": "p-cross", "role_period": "cross", "role_index": None,
         "text": "Led teams across two companies."},
    ], "role_map": {}, "summary_excluded_roles": set(excluded)}


def master_echo(inv):
    """A response that repeats the master exactly."""
    return {
        "headline": inv["headline"]["text"], "subtitle": inv["subtitle"]["text"],
        "summary_paragraph": inv["summary_paragraph"]["text"],
        "summary_bullets": [{"text": b["text"], "source_ids": [b["id"]]} for b in inv["summary_bullets"]],
        "competencies": [list(c["terms"]) for c in inv["competencies"]],
        "roles": [{"role_index": r["role_index"],
                   "bullets": [{"text": b["text"], "source_ids": [b["id"]]} for b in r["bullets"]]}
                  for r in inv["roles"]],
    }


def run(tailored, excluded=frozenset()):
    inv, pl = inventory(), pool(excluded)
    res = fae.validate_tailoring(inv, pl, tailored)
    fae.apply_role_limits(inv, pl, res)
    fae.apply_capacity(inv, res)
    return res


# ── §3.1 tokenization: accept and reject cases ──

@pytest.mark.parametrize("text, source", [
    ("Ran AWS, then left.", "Ran AWS"),
    ("Moved to CI/CD.", "Adopted CI/CD"),
    ("Passed PCI-DSS audits.", "Passed PCI-DSS audits"),
    ("Patched 2000 servers.", "Patched 2,000 servers"),
    ("Patched ~2,000 servers.", "Patched ~2,000 servers"),
    ("Ran AWS workloads.", "Ran AWS-native workloads"),
])
def test_tokenization_accepts(text, source):
    assert fae._lexical_problems(text, [source]) == []


@pytest.mark.parametrize("text, source", [
    ("Grew 10% a year.", "Led 10 teams; cut spend 20%"),
    ("Ran K8s clusters.", "Ran Kubernetes clusters"),
    ("Managed $15M of spend.", "Managed 15 million of spend"),
    ("Passed DSS-PCI audits.", "Passed PCI-DSS audits"),
])
def test_tokenization_rejects(text, source):
    assert fae._lexical_problems(text, [source])


def test_sentence_initial_capital_is_not_a_named_term():
    assert fae._lexical_problems("Managed vendors. Built teams.", ["managed vendors and built teams"]) == []


# ── §3.2 / §4: verified versus retuned ──

def test_master_echo_is_tailored_and_all_verified():
    res = run(master_echo(inventory()))
    assert fae.tailoring_state(res) == "tailored"
    assert fae.retuned_items(res) == []
    assert res["budget"]["reverts"] == []


def test_light_retune_passes_and_is_marked_retuned():
    t = master_echo(inventory())
    t["roles"][0]["bullets"][0] = {"text": "Built an AWS platform team of 12 engineers.", "source_ids": ["M:0:0"]}
    res = run(t)
    b = res["roles"][0]["bullets"][0]
    assert b["status"] == "retuned" and fae.tailoring_state(res) == "tailored"
    assert [i["field"] for i in fae.retuned_items(res)] == ["role 0 bullet 0"]


def test_number_joined_to_a_word_is_rejected_conservatively():
    """'12-engineer' does not trace to '12 engineers' (§3.1 keeps the token whole)."""
    assert fae._lexical_problems("Built a 12-engineer team.", ["Built a team of 12 engineers."])


def test_meaning_change_passes_lexically_but_is_unverified():
    """§4: the checks cannot prove meaning; such text is published as retuned."""
    t = master_echo(inventory())
    t["roles"][0]["bullets"][1] = {"text": "Cut cloud headcount 20% in one year.", "source_ids": ["M:0:1"]}
    res = run(t)
    assert res["roles"][0]["bullets"][1]["status"] == "retuned"


@pytest.mark.parametrize("bullet, reason", [
    ({"text": "Built a platform team of 15 engineers on AWS.", "source_ids": ["M:0:0"]}, "number '15'"),
    ({"text": "Built a platform team of 12 engineers on Azure.", "source_ids": ["M:0:0"]}, "term 'Azure'"),
    ({"text": "Architected a platform team of 12 engineers on AWS.", "source_ids": ["M:0:0"]}, "leading verb"),
    ({"text": "Built a platform team — 12 engineers on AWS.", "source_ids": ["M:0:0"]}, "em dash"),
    ({"text": "Built a platform team.", "source_ids": []}, "no source_ids"),
    ({"text": "Built a platform team.", "source_ids": ["M:0:0", "M:0:0"]}, "duplicate source_ids"),
    ({"text": "Built a platform team.", "source_ids": ["nope"]}, "unknown source"),
    ({"text": "Wrote deployment scripts in PowerShell.", "source_ids": ["M:1:0"]}, "does not belong"),
    ({"text": "", "source_ids": ["M:0:0"]}, "empty text"),
])
def test_role_bullet_failures_fall_back_to_master(bullet, reason):
    t = master_echo(inventory())
    t["roles"][0]["bullets"][0] = bullet
    res = run(t)
    ev = [e for e in res["events"] if e["field"] == "role 0 bullet 0"]
    assert ev and reason in ev[0]["reason"]
    assert fae.tailoring_state(res) == "partial"
    texts = [b["text"] for b in res["roles"][0]["bullets"]]
    if "M:0:0" in bullet["source_ids"]:
        assert ev[0]["action"] == "replaced" and texts[0] == inventory()["roles"][0]["bullets"][0]["text"]
    else:
        assert ev[0]["action"] == "dropped"


def test_pool_item_swaps_into_its_role():
    t = master_echo(inventory())
    t["roles"][0]["bullets"][0] = {"text": "Founded the CMDB across ~2,000 servers.", "source_ids": ["p-cmdb"]}
    res = run(t)  # within the capacity of the slot it pairs with
    assert res["roles"][0]["bullets"][0]["status"] == "verified"
    assert fae.tailoring_state(res) == "tailored"


def test_master_bullet_used_once_per_role():
    t = master_echo(inventory())
    t["roles"][0]["bullets"].append(dict(t["roles"][0]["bullets"][0]))
    res = run(t)
    assert len(res["roles"][0]["bullets"]) == 2
    assert any("already used" in e["reason"] for e in res["events"])


def test_pool_item_identical_to_a_master_bullet_is_not_printed_twice():
    inv, pl = inventory(), pool()
    pl["items"].append({"item_id": "p-dup", "role_period": "dir", "role_index": 0,
                        "text": "Cut cloud spend 20% in one year."})
    t = master_echo(inv)
    t["roles"][0]["bullets"].insert(0, {"text": "Cut cloud spend 20% in one year.", "source_ids": ["p-dup"]})
    res = fae.validate_tailoring(inv, pl, t)
    texts = [b["text"] for b in res["roles"][0]["bullets"]]
    assert texts.count("Cut cloud spend 20% in one year.") == 1
    assert res["roles"][0]["bullets"][0]["master_id"] == "M:0:1"  # counted as that master bullet


def test_role_floor_reverts_to_master_bullets():
    t = master_echo(inventory())
    t["roles"][0]["bullets"] = [{"text": "Invented 99 things on GCP.", "source_ids": ["p-cross"]}]
    res = run(t)
    assert [b["text"] for b in res["roles"][0]["bullets"]] == [b["text"] for b in inventory()["roles"][0]["bullets"]]
    assert any(e["reason"] == "no bullets passed (floor)" for e in res["events"])


def test_missing_role_and_unknown_role_index():
    t = master_echo(inventory())
    t["roles"] = [t["roles"][0], {"role_index": 7, "bullets": []}]
    res = run(t)
    assert [b["text"] for b in res["roles"][1]["bullets"]] == [b["text"] for b in inventory()["roles"][1]["bullets"]]
    assert {e["action"] for e in res["events"]} >= {"ignored", "reverted"}


# ── summary, prose fields and competencies ──

def test_summary_bullet_may_cite_summary_only_item():
    t = master_echo(inventory())
    t["summary_bullets"][1] = {"text": "Led teams across two companies.", "source_ids": ["p-cross"]}
    assert fae.tailoring_state(run(t)) == "tailored"


def test_summary_floor_reverts_to_master():
    t = master_echo(inventory())
    t["summary_bullets"] = [{"text": "Led 400 teams.", "source_ids": ["M:S:0"]}]
    res = run(t)
    assert [b["text"] for b in res["summary_bullets"]] == [b["text"] for b in inventory()["summary_bullets"]]


@pytest.mark.parametrize("key, bad", [
    ("headline", "Technology Leader | Kubernetes"),
    ("subtitle", "Cloud | 40% Savings"),
    ("summary_paragraph", "Leader who builds platforms — reliably."),
])
def test_prose_field_reverts_on_failure(key, bad):
    t = master_echo(inventory())
    t[key] = bad
    res = run(t)
    assert res[key]["text"] == inventory()[key]["text"]
    assert any(e["field"] == key and e["action"] == "reverted" for e in res["events"])


def test_prose_field_retune_drawing_on_corpus_passes():
    t = master_echo(inventory())
    t["headline"] = "Platform Leader | FinOps and Cost"
    res = run(t)
    assert res["headline"]["text"] == "Platform Leader | FinOps and Cost"
    assert res["headline"]["status"] == "retuned"


def test_competency_term_dropped_and_line_count_mismatch():
    t = master_echo(inventory())
    # "Terraform" alone is sentence-initial and so not treated as a named term (§3.1);
    # before Amendment 2 this test passed only because the §6 budget reverted the line.
    t["competencies"][0] = ["Strategy", "Cloud Terraform", "Team Building"]
    res = run(t)
    assert res["competencies"][0]["terms"] == ["Strategy", "Team Building"]
    t["competencies"] = [["Strategy"]]
    res = run(t)
    assert [c["terms"] for c in res["competencies"]] == [c["terms"] for c in inventory()["competencies"]]


def test_competency_reorder_is_retuned():
    t = master_echo(inventory())
    t["competencies"][1] = ["Budgeting", "FinOps"]
    res = run(t)
    assert res["competencies"][1]["status"] == "retuned"


# ── Amendment 1 ──

def test_a1_role_over_cap_drops_lowest_priority():
    t = master_echo(inventory())
    t["roles"][0]["bullets"].insert(0, {"text": "Founded the CMDB across ~2,000 servers.", "source_ids": ["p-cmdb"]})
    res = run(t)
    texts = [b["text"] for b in res["roles"][0]["bullets"]]
    assert len(texts) == 2 and texts[0].startswith("Founded the CMDB")
    assert any("A1" in e["reason"] for e in res["events"])
    assert fae.tailoring_state(res) == "partial"


def test_a2_summary_cannot_cite_excluded_role_master_or_pool():
    for sid, text in (("M:1:0", "Wrote deployment scripts in PowerShell."),
                      ("p-cicd", "Built the automated deployment path in Jenkins and PowerShell that cut outages 45%.")):
        t = master_echo(inventory())
        t["summary_bullets"][0] = {"text": text, "source_ids": [sid]}
        res = run(t, excluded={1})
        assert any("kept out of the summary" in e["reason"] for e in res["events"])
        assert all(text != b["text"] for b in res["summary_bullets"])


def test_a2_does_not_affect_master_summary_or_summary_only_items():
    t = master_echo(inventory())
    t["summary_bullets"][1] = {"text": "Led teams across two companies.", "source_ids": ["p-cross"]}
    assert fae.tailoring_state(run(t, excluded={1})) == "tailored"


def test_a3_swap_within_master_chars_passes():
    t = master_echo(inventory())
    # p-cicd is longer than M:1:1 but the role total still fits when it replaces M:1:0
    t["roles"][1]["bullets"] = [{"text": "Wrote deployment scripts in PowerShell.", "source_ids": ["M:1:0"]},
                                {"text": "Ran release management.", "source_ids": ["M:1:1"]}]
    assert fae.tailoring_state(run(t, excluded={1})) == "tailored"


def test_a3_long_swap_in_excluded_role_is_reverted():
    t = master_echo(inventory())
    t["roles"][1]["bullets"][1] = {"text": "Led a long and detailed CRM implementation across three offices with 50 sales reps.",
                                   "source_ids": ["p-long"]}
    res = run(t, excluded={1})
    assert [b["text"] for b in res["roles"][1]["bullets"]] == [b["text"] for b in inventory()["roles"][1]["bullets"]]
    assert any("A3" in e["reason"] for e in res["events"])


def test_a3_does_not_apply_to_unflagged_role():
    t = master_echo(inventory())
    t["roles"][1]["bullets"][1] = {"text": "Led a long and detailed CRM implementation across three offices with 50 sales reps.",
                                   "source_ids": ["p-long"]}
    res = run(t)  # role 1 not excluded; only length capacity applies
    assert not any("A3" in e["reason"] for e in res["events"])


# ── Amendment 2: length capacity ──

def M(i, n):
    """A master bullet of exactly n characters."""
    return {"id": i, "index": 0, "text": (i + " " + "w" * n)[:n]}


def T(n, sources, master_id=None, ch="t"):
    """A tailored bullet of exactly n characters (not master text)."""
    return {"text": ch * n, "source_ids": list(sources), "status": "retuned", "master_id": master_id}


def reduce(bullets, masters, use_sources=True):
    caps = {m["id"]: fae.slot_capacity(len(m["text"])) for m in masters}
    events, reverts = [], []
    pairs = fae._reduce_group("role 0", bullets, masters, caps, events, reverts, use_sources)
    assert all(len(bullets[i]["text"]) <= caps[sid] for i, sid in pairs)
    return events, reverts


def test_capacity_rule():
    assert fae.slot_capacity(38, "headline") == 38 and fae.slot_capacity(27, "subtitle") == 27
    assert fae.slot_capacity(50) == 92        # slack on a one-line paragraph
    assert fae.slot_capacity(111) == 111      # a full line has no slack
    assert fae.slot_capacity(112) == 184 and fae.slot_capacity(180) == 184
    assert fae.slot_capacity(280) == 280      # 92 x 3 = 276 < 280
    caps = [fae.slot_capacity(n) for n in range(0, 1200)]
    assert all(a <= b for a, b in zip(caps, caps[1:])) and all(c >= n for n, c in enumerate(caps))


def test_master_echo_has_zero_reverts_and_reports_full_slots():
    res = run(master_echo(inventory()))
    assert res["budget"]["reverts"] == [] and fae.tailoring_state(res) == "tailored"
    assert {x["slot"] for x in res["budget"]["full"]} >= {"headline", "subtitle"}


@pytest.mark.parametrize("key, longer", [
    ("headline", "Technology Leader | Platforms and Cost | FinOps"),
    ("subtitle", "Cloud | FinOps | Operations | Budgeting"),
])
def test_headline_or_subtitle_over_capacity_reverts_alone(key, longer):
    t = master_echo(inventory())
    t[key] = longer
    t["roles"][0]["bullets"][0] = {"text": "Built an AWS platform team of 12 engineers.", "source_ids": ["M:0:0"]}
    res = run(t)
    assert res[key]["text"] == inventory()[key]["text"]
    assert [r["field"] for r in res["budget"]["reverts"]] == [key]
    assert res["roles"][0]["bullets"][0]["text"] == "Built an AWS platform team of 12 engineers."
    assert fae.tailoring_state(res) == "partial"


def test_bullet_within_capacity_passes_untouched():
    t = master_echo(inventory())
    t["roles"][0]["bullets"][0] = {"text": "Built an AWS platform team of 12 engineers.", "source_ids": ["M:0:0"]}
    res = run(t)
    assert res["roles"][0]["bullets"][0]["status"] == "retuned" and res["budget"]["reverts"] == []


def test_reordering_within_a_role_passes():
    t = master_echo(inventory())
    t["roles"][0]["bullets"].reverse()
    res = run(t)
    assert res["budget"]["reverts"] == [] and fae.tailoring_state(res) == "tailored"


def test_group_with_fewer_bullets_pairs_with_the_largest_capacities():
    masters = [M("M:0:0", 180), M("M:0:1", 90)]
    caps = {m["id"]: fae.slot_capacity(len(m["text"])) for m in masters}
    assert fae._pair_group([T(150, ["M:0:1"])], masters, caps) == [(0, "M:0:0")]


def test_bullet_over_capacity_reverts_alone_and_role_keeps_its_tailoring():
    inv = inventory()
    t = master_echo(inv)
    t["roles"][0]["bullets"][0] = {"text": "Built an AWS platform team of 12 engineers.", "source_ids": ["M:0:0"]}
    res = fae.validate_tailoring(inv, pool(), t)
    b = res["roles"][0]["bullets"][1]
    b.update(text=b["text"] + " x" * 60, status="retuned", master_id=None)  # bypasses the checks
    fae.apply_capacity(inv, res)
    assert res["roles"][0]["bullets"][0]["text"] == "Built an AWS platform team of 12 engineers."
    assert res["roles"][0]["bullets"][1] == fae._master_bullet(inv["roles"][0]["bullets"][1])
    assert res["roles"][0]["bullets"][1]["status"] == "verified"
    assert len(res["budget"]["reverts"]) == 1 and fae.tailoring_state(res) == "partial"


def test_round2_counterexample_reverts_only_the_long_bullet():
    """Gee round 2: capacities 184 and 92, tailored 130 and 220."""
    masters = [M("M:0:0", 180), M("M:0:1", 90)]
    bullets = [T(130, ["M:0:0"]), T(220, ["M:0:1"], ch="u")]
    events, reverts = reduce(bullets, masters)
    assert len(reverts) == 1 and reverts[0]["master_id"] == "M:0:1"
    assert len(bullets[0]["text"]) == 130 and bullets[1]["text"] == masters[1]["text"]
    assert len(bullets) == 2


def test_selected_bullet_within_its_paired_capacity_records_zero_overflow():
    """Gee round 3: masters [280, 180, 90], tailored [200, 190, 180] with 180 fixed."""
    masters = [M("M:0:0", 280), M("M:0:1", 180), M("M:0:2", 90)]
    fixed = fae._master_bullet(masters[1])
    bullets = [T(200, ["M:0:0"]), T(190, ["M:0:2"], ch="u"), fixed]
    _, reverts = reduce(bullets, masters)
    assert [r["master_id"] for r in reverts] == ["M:0:0", "M:0:2"]
    assert reverts[0]["overflow"] == 0
    assert reverts[0]["selection"] == "longest non-fixed bullet in failing group"
    assert bullets[2] is fixed and len(bullets) == 3


def test_reworded_bullet_whose_source_is_in_use_takes_first_unused_master():
    masters = [M("M:0:0", 100), M("M:0:1", 50)]
    bullets = [fae._master_bullet(masters[0]), T(200, ["M:0:0"])]
    _, reverts = reduce(bullets, masters)
    assert reverts[0]["master_id"] == "M:0:1"
    assert [b["master_id"] for b in bullets] == ["M:0:0", "M:0:1"]


def test_pool_bullet_over_capacity_takes_first_unused_master():
    masters = [M("M:0:0", 60), M("M:0:1", 70)]
    bullets = [fae._master_bullet(masters[1]), T(150, ["p-x"])]
    _, reverts = reduce(bullets, masters)
    assert reverts[0]["master_id"] == "M:0:0" and len(bullets) == 2


def test_summary_bullet_reverts_to_a_master_summary_bullet_never_a_role_bullet():
    masters = [M("M:S:0", 60), M("M:S:1", 70)]
    bullets = [T(150, ["M:0:0"]), fae._master_bullet(masters[1])]
    _, reverts = reduce(bullets, masters, use_sources=False)
    assert reverts[0]["master_id"] == "M:S:0"
    assert bullets[0]["source_ids"] == ["M:S:0"]


def test_tie_break_is_last_in_document_order():
    masters = [M("M:0:0", 50), M("M:0:1", 50)]
    bullets = [T(100, []), T(100, [], ch="u")]
    _, reverts = reduce(bullets, masters)
    assert [r["field"] for r in reverts] == ["role 0 bullet 1", "role 0 bullet 0"]


def test_summary_verbatim_bullet_carries_master_id():
    res = run(master_echo(inventory()))
    assert [b["master_id"] for b in res["summary_bullets"]] == ["M:S:0", "M:S:1"]


def test_summary_over_master_count_drops_from_the_end():
    t = master_echo(inventory())
    t["summary_bullets"].append({"text": "Led teams across two companies.", "source_ids": ["p-cross"]})
    res = run(t)
    assert len(res["summary_bullets"]) == 2
    assert all(b["text"] != "Led teams across two companies." for b in res["summary_bullets"])
    assert any("B5" in e["reason"] and e["action"] == "dropped" for e in res["events"])
    assert fae.tailoring_state(res) == "partial"


def test_full_slots_reported_against_the_final_pairing():
    masters = [M("M:0:0", 180), M("M:0:1", 90)]
    bullets = [T(92, ["p-x"]), T(184, ["M:0:0"], ch="u")]
    inv = inventory()
    inv["roles"][0]["bullets"] = masters
    res = fae.validate_tailoring(inv, pool(), master_echo(inventory()))
    res["roles"][0]["bullets"] = bullets
    fae.apply_capacity(inv, res)
    full = {(x["slot"], x["paired"]) for x in res["budget"]["full"]}
    assert ("M:0:0", "M:0:0") in full and ("M:0:1", "p-x") in full
    assert res["budget"]["reverts"] == []


def test_garbage_response_reverts_everything_safely():
    res = run({"roles": "nonsense", "summary_bullets": None})
    inv = inventory()
    assert [b["text"] for b in res["summary_bullets"]] == [b["text"] for b in inv["summary_bullets"]]
    assert all(len(r["bullets"]) == 2 for r in res["roles"])
    assert res["budget"]["reverts"] == []
