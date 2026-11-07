"""Episodic memory for one mission: what was tried, what was rejected, and why.

Keeps the plan loop from retrying a bad site forever ("cluster 7 rejected: no
valid graft patch") and gives the debrief a readable record.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class EpisodicMemory:
    max_attempts_per_recipient: int = 3
    donor_rejections: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    recipient_rejections: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    recipient_attempts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    harvest_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    dislodge_events: int = 0

    def reject_donor(self, cluster_id: str, reason: str) -> None:
        self.donor_rejections[cluster_id].append(reason)

    def reject_recipient(self, cluster_id: str, reason: str) -> None:
        """Permanent: the site is unsuitable."""
        self.recipient_rejections[cluster_id].append(reason)

    def note_recipient_attempt(self, cluster_id: str) -> int:
        self.recipient_attempts[cluster_id] += 1
        return self.recipient_attempts[cluster_id]

    def note_harvest(self, donor_id: str) -> None:
        self.harvest_counts[donor_id] += 1

    def excluded_donors(self) -> set[str]:
        return set(self.donor_rejections)

    def excluded_recipients(self) -> set[str]:
        out = set(self.recipient_rejections)
        out |= {c for c, n in self.recipient_attempts.items() if n >= self.max_attempts_per_recipient}
        return out

    def to_dict(self) -> dict:
        return {
            "donor_rejections": {k: list(v) for k, v in self.donor_rejections.items()},
            "recipient_rejections": {k: list(v) for k, v in self.recipient_rejections.items()},
            "recipient_attempts": dict(self.recipient_attempts),
            "harvest_counts": dict(self.harvest_counts),
            "dislodge_events": self.dislodge_events,
        }
