"""Donor-recipient pairing (pure, no robot, no I/O).

    J(i, j) = w1*|x_rov - x_i| + w2*|x_i - x_j| - w3*H_i

For each unvisited DEAD recipient j, choose the same-species LIVE donor i that
minimises J. The FSM executes the lowest-J pairing first and re-plans after
every transplant, so registry changes mid-mission change the next choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from agent.config import PairingWeights
from agent.geometry import distance
from perception.registry import SemanticMapEntry


@dataclass(frozen=True)
class CostTerms:
    donor_id: str
    recipient_id: str
    travel: float  # |x_rov - x_i|
    transfer: float  # |x_i - x_j|
    health: float  # H_i
    J: float


@dataclass(frozen=True)
class Pairing:
    donor_id: str
    recipient_id: str
    species_class: str
    cost: CostTerms
    runners_up: tuple[CostTerms, ...] = ()


@dataclass(frozen=True)
class Unrestorable:
    recipient_id: str
    reason: str


@dataclass(frozen=True)
class RestorationPlan:
    pairings: tuple[Pairing, ...]  # sorted by J, best first
    unrestorable: tuple[Unrestorable, ...] = ()
    skipped_donors: tuple[Unrestorable, ...] = ()  # LIVE clusters not usable as donors, with reason
    ignored_bleached: tuple[str, ...] = ()

    @property
    def best(self) -> Optional[Pairing]:
        return self.pairings[0] if self.pairings else None


def cost(
    rov_position: Sequence[float],
    donor: SemanticMapEntry,
    recipient: SemanticMapEntry,
    weights: PairingWeights = PairingWeights(),
) -> CostTerms:
    travel = distance(rov_position, donor.position_world)
    transfer = distance(donor.position_world, recipient.position_world)
    health = float(donor.health_score)
    J = weights.w1 * travel + weights.w2 * transfer - weights.w3 * health
    return CostTerms(donor.cluster_id, recipient.cluster_id, travel, transfer, health, J)


def is_open_recipient(entry: SemanticMapEntry) -> bool:
    return entry.health_status == "DEAD" and not entry.sampled_or_restored


def eligible_donors(
    entries: Iterable[SemanticMapEntry],
    *,
    exclude: Iterable[str] = (),
    min_health: float = 0.0,
    harvest_counts: Optional[dict[str, int]] = None,
    max_harvests: Optional[int] = None,
) -> tuple[list[SemanticMapEntry], list[Unrestorable]]:
    """LIVE donors that pass the abstention rules, plus the ones skipped and why."""
    exclude = set(exclude)
    harvest_counts = harvest_counts or {}
    ok, skipped = [], []
    for e in entries:
        if e.health_status != "LIVE":
            continue
        if e.cluster_id in exclude:
            skipped.append(Unrestorable(e.cluster_id, "rejected earlier this mission"))
        elif e.health_score < min_health:
            skipped.append(Unrestorable(e.cluster_id, f"health_score {e.health_score:.2f} < min {min_health:.2f}"))
        elif max_harvests is not None and harvest_counts.get(e.cluster_id, 0) >= max_harvests:
            skipped.append(Unrestorable(e.cluster_id, f"harvest cap {max_harvests} reached"))
        else:
            ok.append(e)
    return ok, skipped


def best_donor_for(
    recipient: SemanticMapEntry,
    donors: Iterable[SemanticMapEntry],
    rov_position: Sequence[float],
    weights: PairingWeights = PairingWeights(),
    n_runners_up: int = 2,
) -> Optional[Pairing]:
    scored = sorted(
        (cost(rov_position, d, recipient, weights) for d in donors if d.species_class == recipient.species_class),
        key=lambda c: (c.J, c.donor_id),
    )
    if not scored:
        return None
    return Pairing(
        donor_id=scored[0].donor_id,
        recipient_id=recipient.cluster_id,
        species_class=recipient.species_class,
        cost=scored[0],
        runners_up=tuple(scored[1 : 1 + n_runners_up]),
    )


def plan_pairs(
    entries: Iterable[SemanticMapEntry],
    rov_position: Sequence[float],
    weights: PairingWeights = PairingWeights(),
    *,
    exclude_donors: Iterable[str] = (),
    exclude_recipients: Iterable[str] = (),
    min_donor_health: float = 0.0,
    harvest_counts: Optional[dict[str, int]] = None,
    max_harvests_per_donor: Optional[int] = None,
) -> RestorationPlan:
    entries = list(entries)
    exclude_recipients = set(exclude_recipients)
    donors, skipped = eligible_donors(
        entries,
        exclude=exclude_donors,
        min_health=min_donor_health,
        harvest_counts=harvest_counts,
        max_harvests=max_harvests_per_donor,
    )
    pairings, unrestorable = [], []
    for r in entries:
        if not is_open_recipient(r) or r.cluster_id in exclude_recipients:
            continue
        p = best_donor_for(r, donors, rov_position, weights)
        if p is None:
            unrestorable.append(Unrestorable(r.cluster_id, f"no eligible LIVE donor of species {r.species_class}"))
        else:
            pairings.append(p)
    pairings.sort(key=lambda p: (p.cost.J, p.recipient_id))
    bleached = tuple(sorted(e.cluster_id for e in entries if e.health_status == "BLEACHED"))
    return RestorationPlan(tuple(pairings), tuple(unrestorable), tuple(skipped), bleached)


def best_recipient_for_carried(
    species_class: str,
    rov_position: Sequence[float],
    entries: Iterable[SemanticMapEntry],
    *,
    exclude: Iterable[str] = (),
) -> Optional[tuple[SemanticMapEntry, float]]:
    """Carry-aware replan: a fragment is already in the gripper, so the donor
    terms are sunk and only the carry distance matters."""
    exclude = set(exclude)
    options = [
        (e, distance(rov_position, e.position_world))
        for e in entries
        if is_open_recipient(e) and e.species_class == species_class and e.cluster_id not in exclude
    ]
    if not options:
        return None
    return min(options, key=lambda t: (t[1], t[0].cluster_id))


def nearest_donor_baseline(
    entries: Iterable[SemanticMapEntry],
    rov_position: Sequence[float],
) -> list[CostTerms]:
    """Baseline for the root CLAUDE.md section 11 metric: same-species nearest
    donor to each recipient, ignoring health. Scored with default weights so it
    is comparable with plan_pairs."""
    entries = list(entries)
    donors = [e for e in entries if e.health_status == "LIVE"]
    out = []
    for r in entries:
        if not is_open_recipient(r):
            continue
        same = [d for d in donors if d.species_class == r.species_class]
        if same:
            d = min(same, key=lambda d: (distance(d.position_world, r.position_world), d.cluster_id))
            out.append(cost(rov_position, d, r))
    return out
