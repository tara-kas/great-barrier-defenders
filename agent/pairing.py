"""Pairs bleached colonies with same-genet fragments from the base station (pure).

    J(i, j) = w1*|x_rov - x_i| + w2*|x_i - x_j| - w3*H_i

i is a base station rack and j an open BLEACHED colony. Symbiont transfer needs
contact with the same genet, and mixed-genet contact harms the recipient, so a
colony without a confident in-stock genet match is skipped, never approximated.
DEAD colonies are never targets. The FSM executes the lowest-J pairing first and
re-plans after every placement, so registry changes alter the next choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from agent.base_station import BaseStation, Rack
from agent.config import PairingWeights
from agent.geometry import distance
from perception.registry import SemanticMapEntry


@dataclass(frozen=True)
class CostTerms:
    donor_id: str  # rack slot
    recipient_id: str
    travel: float  # |x_rov - x_i|
    transfer: float  # |x_i - x_j|
    health: float  # H_i
    J: float


@dataclass(frozen=True)
class Pairing:
    donor_id: str  # rack slot
    genet_id: str
    recipient_id: str
    species_class: str
    cost: CostTerms


@dataclass(frozen=True)
class Skipped:
    recipient_id: str
    reason: str


@dataclass(frozen=True)
class RestorationPlan:
    pairings: tuple[Pairing, ...]  # sorted by J, best first
    skipped: tuple[Skipped, ...] = ()
    ignored_dead: tuple[str, ...] = ()

    @property
    def best(self) -> Optional[Pairing]:
        return self.pairings[0] if self.pairings else None


def cost(
    rov_position: Sequence[float],
    station_position: Sequence[float],
    rack: Rack,
    recipient: SemanticMapEntry,
    weights: PairingWeights = PairingWeights(),
) -> CostTerms:
    travel = distance(rov_position, station_position)
    transfer = distance(station_position, recipient.position_world)
    health = float(rack.health_score)
    J = weights.w1 * travel + weights.w2 * transfer - weights.w3 * health
    return CostTerms(rack.slot, recipient.cluster_id, travel, transfer, health, J)


def is_open_recipient(entry: SemanticMapEntry) -> bool:
    return entry.health_status == "BLEACHED" and not entry.sampled_or_restored


def _skip_reason(
    recipient: SemanticMapEntry,
    station: BaseStation,
    exclude_racks: set[str],
    min_donor_health: float,
) -> Optional[str]:
    if recipient.genet_id is None:
        return "no confident UV genet match"
    sources = [r for r in station.sources_for(recipient.genet_id) if r.fragments_available > 0]
    if not sources:
        return f"genet {recipient.genet_id} not in stock"
    sources = [r for r in sources if r.species_class == recipient.species_class]
    if not sources:
        return "same-genet donor species does not match recipient"
    eligible = [r for r in sources if r.slot not in exclude_racks]
    if not eligible:
        return "rack sources rejected earlier this mission"
    if not any(r.health_score >= min_donor_health for r in eligible):
        return f"rack health_score below min {min_donor_health:.2f}"
    return None


def plan_pairs(
    entries: Iterable[SemanticMapEntry],
    rov_position: Sequence[float],
    station: BaseStation,
    weights: PairingWeights = PairingWeights(),
    *,
    exclude_racks: Iterable[str] = (),
    exclude_recipients: Iterable[str] = (),
    min_donor_health: float = 0.0,
) -> RestorationPlan:
    entries = list(entries)
    exclude_racks, exclude_recipients = set(exclude_racks), set(exclude_recipients)
    pairings, skipped = [], []
    for r in entries:
        if not is_open_recipient(r) or r.cluster_id in exclude_recipients:
            continue
        reason = _skip_reason(r, station, exclude_racks, min_donor_health)
        if reason:
            skipped.append(Skipped(r.cluster_id, reason))
            continue
        for rack in station.sources_for(r.genet_id):
            if (rack.fragments_available <= 0 or rack.slot in exclude_racks
                    or rack.health_score < min_donor_health or rack.species_class != r.species_class):
                continue
            terms = cost(rov_position, station.position_for(rack), rack, r, weights)
            pairings.append(Pairing(rack.slot, rack.genet_id, r.cluster_id, r.species_class, terms))
    pairings.sort(key=lambda p: (p.cost.J, p.recipient_id, p.donor_id))
    dead = tuple(sorted(e.cluster_id for e in entries if e.health_status == "DEAD"))
    return RestorationPlan(tuple(pairings), tuple(skipped), dead)


def best_recipient_for_carried(
    genet_id: str,
    rov_position: Sequence[float],
    entries: Iterable[SemanticMapEntry],
    *,
    exclude: Iterable[str] = (),
    species_class: Optional[str] = None,
) -> Optional[tuple[SemanticMapEntry, float]]:
    """Carry-aware replan: a fragment is already in the gripper, so only the
    carry distance matters, and it can only go to its own genet."""
    exclude = set(exclude)
    options = [
        (e, distance(rov_position, e.position_world))
        for e in entries
        if is_open_recipient(e) and e.genet_id == genet_id and e.cluster_id not in exclude
        and (species_class is None or e.species_class == species_class)
    ]
    if not options:
        return None
    return min(options, key=lambda t: (t[1], t[0].cluster_id))


def species_only_mismatches(entries: Iterable[SemanticMapEntry], station: BaseStation) -> list[str]:
    """Baseline metric: colonies a species-only match would give the wrong genet.

    Takes the first rack of the right species, as a matcher without genet data must.
    """
    racks = sorted((r for g in station.stock() for r in station.sources_for(g)), key=lambda r: r.slot)
    wrong = []
    for e in entries:
        if not is_open_recipient(e) or e.genet_id is None:
            continue
        rack = next((r for r in racks if r.species_class == e.species_class), None)
        if rack is not None and rack.genet_id != e.genet_id:
            wrong.append(e.cluster_id)
    return wrong
