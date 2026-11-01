"""ADR-015 Amendment 2 F10: invariant helper, seeded randomized test and named cases
for the combined length step (capacity plus A3). Synthetic data only.

The helper re-implements the rules independently of fit_analysis_engine's own
check_final_invariants(), so the engine is not grading itself. It also carries
Lexi's five round-1 tests, asserted on every capacity call that goes through it:
(1) every bullet ends at or under its paired capacity; (2) sorted pairing holds;
(3) bullet counts are unchanged by capacity; (4) a restored bullet is the exact
master bullet; (5) a bullet never touched is the original object.
"""
import copy
import os
import random

import fit_analysis_engine as fae


def _key(text):
    return " ".join(text.split()).casefold()


def _master_dict(m):
    return {"text": m["text"], "source_ids": [m["id"]], "status": "verified", "master_id": m["id"]}


def _fixed(bullets, i, masters):
    mid = bullets[i].get("master_id")
    return (mid in masters and bullets[i]["text"] == masters[mid]["text"]
            and sum(1 for b in bullets if b.get("master_id") == mid) == 1)


def group_problems(field, before, after, master_bullets, caps, ceiling=None):
    """Every violation of the F3 group rules and Lexi's five, for one bullet group.
    before: the group's list as it was handed to the length step (same objects)."""
    masters = {m["id"]: m for m in master_bullets}
    bad = []
    if len(after) != len(before):                                                    # (3)
        bad.append(f"{field}: {len(after)} bullets after, {len(before)} before")
    lengths = sorted((len(b["text"]) for b in after), reverse=True)
    slots = sorted((caps[m["id"]] for m in master_bullets), reverse=True)
    if len(lengths) > len(slots):
        bad.append(f"{field}: more bullets than slots")
    for n, (l, c) in enumerate(zip(lengths, slots)):                                 # (1), (2)
        if l > c:
            bad.append(f"{field}: {n + 1}th longest bullet ({l}) over the {n + 1}th largest capacity ({c})")
    for i, (b0, b1) in enumerate(zip(before, after)):
        if b1 is b0:                                                                 # (5)
            continue
        if _fixed(before, i, masters):
            bad.append(f"{field} bullet {i}: was fixed but is no longer the original object")
        mid = b1.get("master_id")
        if mid not in masters or b1 != _master_dict(masters[mid]):                   # (4)
            bad.append(f"{field} bullet {i}: changed but not an exact master bullet of this group: {b1!r}")
    seen_ids, seen_text = set(), set()
    for i, b in enumerate(after):                                                    # F3 identity and text
        mid = b.get("master_id")
        if mid is not None:
            if mid not in masters:
                bad.append(f"{field} bullet {i}: {mid} is not a master of this group")
            elif b["text"] != masters[mid]["text"] or b.get("source_ids") != [mid]:
                bad.append(f"{field} bullet {i}: carries {mid} without exact text and source_ids")
            if mid in seen_ids:
                bad.append(f"{field}: {mid} repeated")
            seen_ids.add(mid)
        elif any(_key(b["text"]) == _key(m["text"]) for m in master_bullets):
            bad.append(f"{field} bullet {i}: matches a master of this group without carrying it")
        if _key(b["text"]) in seen_text:
            bad.append(f"{field} bullet {i}: repeats the text of an earlier bullet")
        seen_text.add(_key(b["text"]))
    if ceiling is not None and sum(len(b["text"]) for b in after) > ceiling:
        bad.append(f"{field}: {sum(len(b['text']) for b in after)} characters over its A3 ceiling {ceiling}")
    return bad


def snapshot(res):
    return {"summary": list(res["summary_bullets"]),
            "roles": [list(r["bullets"]) for r in res["roles"]],
            "prose": {k: res[k] for k in ("headline", "subtitle", "summary_paragraph")},
            "competencies": list(res["competencies"])}


def capacity_problems(inv, before, res, excluded=frozenset()):
    caps = fae.resume_capacities(inv)
    bad = []
    for key, b0 in before["prose"].items():
        b1 = res[key]
        if b1 is not b0 and b1 != {"text": inv[key]["text"], "status": "verified"}:
            bad.append(f"{key}: changed but not the exact master text")
        if len(b1["text"]) > caps[key]:
            bad.append(f"{key}: over its capacity")
    for n, (c0, c1, m) in enumerate(zip(before["competencies"], res["competencies"], inv["competencies"])):
        if c1 is not c0 and c1 != {"label": m["label"], "terms": list(m["terms"]), "status": "verified"}:
            bad.append(f"competency {n}: changed but not the exact master line")
        if len(m["label"] + ": " + " | ".join(c1["terms"])) > caps["competencies"][n]:
            bad.append(f"competency {n}: over its capacity")
    bad += group_problems("summary", before["summary"], res["summary_bullets"],
                          inv["summary_bullets"], caps["summary_bullets"])
    for k, (r, m) in enumerate(zip(res["roles"], inv["roles"])):
        ceiling = sum(len(b["text"]) for b in m["bullets"]) if r["role_index"] in excluded else None
        bad += group_problems(f"role {r['role_index']}", before["roles"][k], r["bullets"],
                              m["bullets"], caps["roles"][k], ceiling)
    return bad


def capacity(inv, res, excluded=frozenset()):
    """apply_capacity() with the F10 helper asserted on its result."""
    before = snapshot(res)
    fae.apply_capacity(inv, res, excluded)
    bad = capacity_problems(inv, before, res, excluded)
    assert not bad, "; ".join(bad)
    return res


# ── seeded randomized test (standard library only) ──

SEED = int(os.environ.get("PP_CAPACITY_SEED", "20261101"))
CASES = int(os.environ.get("PP_CAPACITY_CASES", "2000"))
_HI, _LO = fae.RESUME_LINE_MAX_CHARS, fae.RESUME_LINE_MIN_CHARS
# Capacity discontinuities of LO x ceil(n / HI) and the lengths where it equals n.
_EDGES = sorted({e + d for j in range(1, 5) for e in (_HI * j, _LO * j) for d in (-1, 0, 1)})


def _master_len(rng):
    return rng.choice(_EDGES) if rng.random() < 0.6 else rng.randint(1, 450)


def _random_group(rng):
    n = rng.choice([1, 1, 2, 3, 3, 4, 5])
    lens = []
    for _ in range(n):
        lens.append(lens[-1] if lens and rng.random() < 0.2 else _master_len(rng))   # equal masters
    masters = [{"id": f"M:0:{j}", "index": 0, "text": chr(ord("A") + j) * L} for j, L in enumerate(lens)]
    caps = {m["id"]: fae.slot_capacity(len(m["text"])) for m in masters}
    if n > 1 and rng.random() < 0.4:
        return _r2_group(rng, n)
    k = n if rng.random() < 0.5 else rng.randint(1, n)                               # k < n too
    free = [m["id"] for m in masters]
    rng.shuffle(free)
    bullets = []
    for pos in range(k):
        kind = rng.random()
        if kind < 0.25 and free:
            mid = free.pop()
            bullets.append(_master_dict(next(m for m in masters if m["id"] == mid)))
            continue
        cited = rng.choice(masters)
        shape = rng.random()
        if shape < 0.6:
            L = rng.choice(list(caps.values())) + rng.choice([-1, 0, 1])
        else:
            L = rng.randint(1, 500)
        L = max(1, L)
        sources = [cited["id"]] if kind < 0.8 else ["p-x"]
        bullets.append({"text": chr(ord("n") + pos) * L, "source_ids": sources,
                        "status": "retuned", "master_id": None})
    return masters, caps, bullets


def _r2_group(rng, n):
    """Gee's R2 geometry: one long master and short masters with slack (capacity well
    above length). The long master's rewrite is shortened, one short rewrite is just over
    capacity and the rest fill their slack, so the role starts under its master total and
    capacity restorations can lift it over."""
    lens = [rng.randint(150, 300)] + [rng.randint(30, 105) for _ in range(n - 1)]
    rng.shuffle(lens)
    masters = [{"id": f"M:0:{j}", "index": 0, "text": chr(ord("A") + j) * L} for j, L in enumerate(lens)]
    caps = {m["id"]: fae.slot_capacity(len(m["text"])) for m in masters}
    longest = max(range(n), key=lambda j: lens[j])
    over = rng.choice([j for j in range(n) if j != longest])
    bullets = []
    for pos, m in enumerate(masters):
        cap = caps[m["id"]]
        L = (round(lens[pos] * rng.uniform(0.55, 0.85)) if pos == longest
             else cap + rng.choice([1, 2, 5]) if pos == over
             else cap - rng.choice([0, 0, 1, 10]))
        bullets.append({"text": chr(ord("n") + pos) * max(1, L), "source_ids": [m["id"]],
                        "status": "retuned", "master_id": None})
    return masters, caps, bullets


def _run_group(masters, caps, bullets, excluded):
    bullets = copy.deepcopy(bullets)
    before = list(bullets)
    ceiling = sum(len(m["text"]) for m in masters) if excluded else None
    events, reverts = [], []
    fae._reduce_role("role 0", bullets, masters, caps, ceiling, events, reverts)
    return before, bullets, ceiling, events, reverts


def test_randomized_combined_length_step():
    rng = random.Random(SEED)
    hits = {"capacity revert": 0, "A3": 0, "A3 after capacity": 0, "capacity after A3": 0, "all master": 0}
    for case in range(CASES):
        masters, caps, bullets = _random_group(rng)
        for excluded in (False, True):                                               # exclusion off and on
            start = sum(len(b["text"]) for b in bullets)
            try:
                before, after, ceiling, events, reverts = _run_group(masters, caps, bullets, excluded)
                bad = group_problems("role 0", before, after, masters, caps, ceiling)
            except Exception as e:  # noqa: BLE001 - any engine error is a failure with the seed attached
                bad = [f"{type(e).__name__}: {e}"]
            assert not bad, (f"seed {SEED} case {case} excluded={excluded}: {'; '.join(bad)}\n"
                             f"masters={[len(m['text']) for m in masters]} "
                             f"bullets={[(len(b['text']), b['source_ids'], b['master_id']) for b in bullets]}")
            a3 = [n for n, e in enumerate(events) if "A3" in e["reason"]]
            cap = [n for n, e in enumerate(events) if "length capacity" in e["reason"]]
            hits["capacity revert"] += bool(cap)
            hits["A3"] += bool(a3)
            hits["A3 after capacity"] += bool(a3 and cap and ceiling is not None and start <= ceiling)
            hits["capacity after A3"] += bool(a3 and cap and max(cap) > min(a3))
            hits["all master"] += all(_fixed(after, i, {m["id"]: m for m in masters}) for i in range(len(after)))
            if not excluded:
                assert not a3, f"seed {SEED} case {case}: A3 fired with the exclusion off"
    # The generator must reach the cases it exists for (Copi NB4, Gee 7): scale with CASES.
    # The outer-loop second pass is rare by nature and also has a named case below.
    floors = {k: CASES // (500 if k == "capacity after A3" else 100) for k in hits}
    assert all(hits[k] >= floors[k] for k in hits), f"seed {SEED}: thin coverage {hits}"


# ── named cases ──

def _group(lens):
    masters = [{"id": f"M:0:{j}", "index": 0, "text": chr(ord("A") + j) * L} for j, L in enumerate(lens)]
    return masters, {m["id"]: fae.slot_capacity(len(m["text"])) for m in masters}


def _rewrite(n, mid, pos):
    return {"text": chr(ord("n") + pos) * n, "source_ids": [mid], "status": "retuned", "master_id": None}


def test_second_pass_after_an_a3_restore():
    """Found by the randomized test: masters [16, 148] (capacities 92, 184), rewrites
    [184, 91] pass capacity but not A3 (275 over 164). The A3 restore of M:0:1 (148) then
    breaks the pairing, so the loop runs capacity again and restores M:0:0."""
    masters, caps = _group([16, 148])
    bullets = [_rewrite(184, "M:0:0", 0), _rewrite(91, "M:0:1", 1)]
    before = list(bullets)
    events, reverts = [], []
    fae._reduce_role("role 0", bullets, masters, caps, 164, events, reverts)
    assert [e["reason"].split(";")[0] for e in events] == [
        "over its master character total (A3)",
        "length capacity: longest non-fixed bullet in failing group (overflow 0)"]
    assert bullets == [_master_dict(masters[0]), _master_dict(masters[1])]
    assert not group_problems("role 0", before, bullets, masters, caps, 164)


def test_every_bullet_can_end_at_master_text():
    masters, caps = _group([50, 60])
    for ceiling in (None, 110):
        bullets = [{"text": "n" * 300, "source_ids": ["p-x"], "status": "retuned", "master_id": None},
                   _rewrite(300, "M:0:0", 1)]
        before = list(bullets)
        fae._reduce_role("role 0", bullets, masters, caps, ceiling, [], [])
        assert all(_fixed(bullets, i, {m["id"]: m for m in masters}) for i in range(2))
        assert bullets[1] == _master_dict(masters[0])  # its own cited master
        assert not group_problems("role 0", before, bullets, masters, caps, ceiling)


def test_helper_tells_an_untouched_bullet_from_an_equal_copy():
    """Copi N6: a fixed bullet replaced by an equal new object is a violation."""
    masters, caps = _group([50, 60])
    fixed = _master_dict(masters[0])
    before = [fixed, _rewrite(40, "M:0:1", 1)]
    assert not group_problems("role 0", before, list(before), masters, caps)
    assert group_problems("role 0", before, [dict(fixed), before[1]], masters, caps) == [
        "role 0 bullet 0: was fixed but is no longer the original object"]


def test_helper_catches_each_rule():
    masters, caps = _group([50, 60])
    t = _rewrite(40, "M:0:1", 1)
    before = [_master_dict(masters[0]), t]
    cases = {
        "1 bullets after": [before[0]],                                                     # (3)
        "over the 1th largest capacity": [before[0], _rewrite(200, "M:0:1", 1)],            # (1)(2)
        "changed but not an exact master bullet": [before[0], dict(t, text="x" * 30)],      # (4)
        "repeats the text": [before[0], dict(_master_dict(masters[0]), master_id=None,
                                             source_ids=["p-x"])],
    }
    for expect, after in cases.items():
        assert any(expect in p for p in group_problems("role 0", before, after, masters, caps)), expect
