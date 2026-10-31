"""ADR-015 §3 to §6 and Amendment 1 (A1 to A3): checks, fallbacks, limits, budget.
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
    fae.apply_budget(inv, res)
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
    assert res["budget"]["fits"] and res["budget"]["share"] == 1.0


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
    res = run(t)  # replaces the longer M:0:0, so the budget still fits
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
    t["competencies"][0] = ["Strategy", "Terraform", "Team Building"]
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
    res = run(t)  # role 1 not excluded; only the overall budget applies
    assert not any("A3" in e["reason"] for e in res["events"])


# ── §6 budget ──

def test_budget_reverts_paragraph_first():
    t = master_echo(inventory())
    t["roles"][0]["bullets"][1] = {"text": "Founded the CMDB across ~2,000 servers.", "source_ids": ["p-cmdb"]}
    t["summary_paragraph"] = "Leader who builds reliable platforms at Example Corp for FinOps, Cloud and Operations teams."
    res = run(t)
    assert res["budget"]["fits"]
    assert res["summary_paragraph"]["text"] == inventory()["summary_paragraph"]["text"]
    assert any(e["reason"] == "summary paragraph reverted to master" for e in res["events"])


def test_budget_drops_role_bullets_but_never_below_one():
    inv = inventory()
    res = fae.validate_tailoring(inv, pool(), master_echo(inv))
    res["roles"][0]["bullets"][0]["text"] += " x" * 200  # force overflow without checks
    fae.apply_budget(inv, res)
    assert all(len(r["bullets"]) >= 1 for r in res["roles"])
    assert len(res["summary_bullets"]) >= 1


def test_budget_failure_reports_not_fitting():
    inv = inventory()
    res = fae.validate_tailoring(inv, pool(), master_echo(inv))
    res["headline"]["text"] += " x" * 400
    fae.apply_budget(inv, res)
    assert res["budget"]["fits"] is False


def test_budget_warns_near_limit():
    inv = inventory()
    res = fae.validate_tailoring(inv, pool(), master_echo(inv))
    fae.apply_budget(inv, res)
    assert res["budget"]["warn"] is True  # master echo uses 100% of the budget


def test_garbage_response_reverts_everything_safely():
    res = run({"roles": "nonsense", "summary_bullets": None})
    inv = inventory()
    assert [b["text"] for b in res["summary_bullets"]] == [b["text"] for b in inv["summary_bullets"]]
    assert all(len(r["bullets"]) == 2 for r in res["roles"])
    assert res["budget"]["fits"]
