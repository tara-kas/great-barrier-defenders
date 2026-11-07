import pytest

from agent.config import PairingWeights
from agent.pairing import best_recipient_for_carried, cost, nearest_donor_baseline, plan_pairs
from perception.registry import SemanticMapEntry


def entry(cid, status, x, y=0.0, score=0.9, species="a"):
    return SemanticMapEntry(cid, species, status, score, (x, y, 0.1), (0.2, 0.2, 0.2))


def test_cost_terms_match_formula():
    d, r = entry("d", "LIVE", 3.0, score=0.8), entry("r", "DEAD", 3.0, 4.0, score=0.0)
    c = cost((0.0, 0.0, 0.1), d, r, PairingWeights(1.0, 1.5, 2.0))
    assert c.travel == pytest.approx(3.0)
    assert c.transfer == pytest.approx(4.0)
    assert c.J == pytest.approx(1.0 * 3.0 + 1.5 * 4.0 - 2.0 * 0.8)


def test_healthier_far_donor_beats_weak_near_donor_with_defaults():
    # near: J = 1 + 1.5*1 - 2*0.1 = 2.3 ; far: J = 2 + 1.5*2 - 2*1.0 = 3.0 -> near wins at defaults
    # Raising w3 to 4 flips it: near = 2.5-0.4 = 2.1, far = 5-4 = 1.0
    entries = [
        entry("near", "LIVE", 1.0, score=0.1),
        entry("far", "LIVE", -2.0, score=1.0),
        entry("dead", "DEAD", 0.0, score=0.0),
    ]
    rov = (0.0, 0.0, 0.1)
    assert plan_pairs(entries, rov).best.donor_id == "near"
    assert plan_pairs(entries, rov, PairingWeights(w3=4.0)).best.donor_id == "far"


def test_species_must_match_and_runners_up_recorded():
    entries = [
        entry("wrong_species", "LIVE", 0.1, species="b"),
        entry("d1", "LIVE", 1.0),
        entry("d2", "LIVE", 3.0),
        entry("r", "DEAD", 0.5),
    ]
    best = plan_pairs(entries, (0, 0, 0.1)).best
    assert best.donor_id == "d1"
    assert [c.donor_id for c in best.runners_up] == ["d2"]


def test_sorted_by_J_and_unrestorable_reported():
    entries = [
        entry("d", "LIVE", 0.0),
        entry("r_far", "DEAD", 5.0),
        entry("r_near", "DEAD", 1.0),
        entry("r_orphan", "DEAD", 1.0, species="z"),
        entry("bleached", "BLEACHED", 2.0, score=0.3),
    ]
    plan = plan_pairs(entries, (0, 0, 0.1))
    assert [p.recipient_id for p in plan.pairings] == ["r_near", "r_far"]
    assert [u.recipient_id for u in plan.unrestorable] == ["r_orphan"]
    assert plan.ignored_bleached == ("bleached",)


def test_exclusions_restored_and_health_threshold():
    restored = entry("done", "DEAD", 0.5)
    restored.sampled_or_restored = True
    entries = [
        entry("weak", "LIVE", 0.1, score=0.3),
        entry("bad", "LIVE", 0.2),
        entry("ok", "LIVE", 4.0),
        entry("r", "DEAD", 0.5),
        entry("r_skip", "DEAD", 0.6),
        restored,
    ]
    plan = plan_pairs(entries, (0, 0, 0.1), exclude_donors={"bad"}, exclude_recipients={"r_skip"}, min_donor_health=0.5)
    assert [(p.donor_id, p.recipient_id) for p in plan.pairings] == [("ok", "r")]
    assert {s.recipient_id for s in plan.skipped_donors} == {"weak", "bad"}


def test_harvest_cap():
    entries = [entry("d1", "LIVE", 0.0), entry("d2", "LIVE", 3.0), entry("r", "DEAD", 0.5)]
    plan = plan_pairs(entries, (0, 0, 0.1), harvest_counts={"d1": 2}, max_harvests_per_donor=2)
    assert plan.best.donor_id == "d2"


def test_carry_aware_recipient_and_baseline():
    entries = [
        entry("d", "LIVE", 0.0),
        entry("r1", "DEAD", 2.0),
        entry("r2", "DEAD", 1.0),
        entry("r3", "DEAD", 0.2, species="b"),
    ]
    rec, dist = best_recipient_for_carried("a", (0, 0, 0.1), entries, exclude={"r2"})
    assert rec.cluster_id == "r1" and dist == pytest.approx(2.0)
    assert best_recipient_for_carried("c", (0, 0, 0.1), entries) is None
    assert {c.recipient_id for c in nearest_donor_baseline(entries, (0, 0, 0.1))} == {"r1", "r2"}
