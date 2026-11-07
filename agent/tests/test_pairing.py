import pytest

from agent.base_station import BaseStation, Rack
from agent.config import PairingWeights
from agent.pairing import best_recipient_for_carried, cost, plan_pairs, species_only_mismatches
from perception.registry import SemanticMapEntry

ROV = (0.0, 0.0, 0.1)


def entry(cid, status, x, y=0.0, score=0.4, species="a", genet=None):
    return SemanticMapEntry(cid, species, status, score, (x, y, 0.1), (0.2, 0.2, 0.2), genet_id=genet)


def bleached(cid, x, genet="g1", species="a"):
    return entry(cid, "BLEACHED", x, species=species, genet=genet)


def station(*racks):
    return BaseStation((0.0, 0.0, 0.1), racks or [Rack("R1", "g1", "a", 3, 0.95)])


def test_cost_terms_match_formula():
    rack = Rack("R1", "g1", "a", 1, 0.8)
    c = cost((0.0, 0.0, 0.1), (3.0, 0.0, 0.1), rack, entry("r", "BLEACHED", 3.0, 4.0), PairingWeights(1.0, 1.5, 2.0))
    assert c.travel == pytest.approx(3.0)
    assert c.transfer == pytest.approx(4.0)
    assert c.J == pytest.approx(1.0 * 3.0 + 1.5 * 4.0 - 2.0 * 0.8)


def test_only_open_bleached_colonies_are_targets():
    done = bleached("done", 0.2)
    done.sampled_or_restored = True
    entries = [bleached("b", 1.0), entry("d", "DEAD", 0.5), entry("l", "LIVE", 0.6), done]
    plan = plan_pairs(entries, ROV, station())
    assert [p.recipient_id for p in plan.pairings] == ["b"]
    assert plan.ignored_dead == ("d",)


def test_dead_colony_with_a_genet_is_still_not_a_target():
    assert plan_pairs([entry("d", "DEAD", 1.0, genet="g1")], ROV, station()).pairings == ()


def test_pairs_with_the_rack_of_the_same_genet():
    racks = [Rack("R1", "g1", "a", 3, 0.95), Rack("R2", "g2", "a", 3, 0.95)]
    best = plan_pairs([bleached("b", 1.0, genet="g2")], ROV, station(*racks)).best
    assert (best.donor_id, best.genet_id) == ("R2", "g2")


def test_no_genet_match_is_skipped_not_guessed():
    plan = plan_pairs([bleached("b", 1.0, genet=None)], ROV, station())
    assert plan.pairings == ()
    assert plan.skipped[0].reason == "no confident UV genet match"


@pytest.mark.parametrize("racks", [[Rack("R1", "g2", "a", 3, 0.95)], [Rack("R1", "g1", "a", 0, 0.95)]])
def test_genet_out_of_stock_is_skipped(racks):
    plan = plan_pairs([bleached("b", 1.0)], ROV, station(*racks))
    assert plan.pairings == () and "not in stock" in plan.skipped[0].reason


def test_sorted_by_J_nearest_first():
    plan = plan_pairs([bleached("far", 5.0), bleached("near", 1.0)], ROV, station())
    assert [p.recipient_id for p in plan.pairings] == ["near", "far"]


def test_exclusions_and_health_threshold():
    entries = [bleached("r", 1.0), bleached("r_skip", 1.2)]
    assert [p.recipient_id for p in plan_pairs(entries, ROV, station(), exclude_recipients={"r_skip"}).pairings] == ["r"]
    rejected = plan_pairs(entries, ROV, station(), exclude_racks={"R1"})
    assert rejected.pairings == () and "rejected" in rejected.skipped[0].reason
    weak = plan_pairs(entries, ROV, station(Rack("R1", "g1", "a", 3, 0.3)), min_donor_health=0.5)
    assert weak.pairings == () and "health_score" in weak.skipped[0].reason


def test_carried_fragment_only_goes_to_its_own_genet():
    entries = [bleached("r1", 2.0), bleached("r2", 1.0), bleached("other", 0.2, genet="g2")]
    rec, dist = best_recipient_for_carried("g1", ROV, entries, exclude={"r2"})
    assert rec.cluster_id == "r1" and dist == pytest.approx(2.0)
    assert best_recipient_for_carried("g9", ROV, entries) is None


def test_species_only_matching_would_pick_the_wrong_genet():
    racks = [Rack("R1", "g1", "a", 3, 0.95), Rack("R2", "g2", "a", 3, 0.95)]
    entries = [bleached("right", 1.0, genet="g1"), bleached("wrong", 2.0, genet="g2")]
    assert species_only_mismatches(entries, station(*racks)) == ["wrong"]
