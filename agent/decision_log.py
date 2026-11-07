"""Shared decision-log format, written by agent/fsm.py, read by dashboard/ and
cloud/debrief.py. Every FSM transition must log the evidence that caused it
(CLAUDE.md section 8).
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DecisionLogEntry:
    timestamp: str
    state: str
    action: str
    evidence: dict[str, Any]
    outcome: str = ""

    @staticmethod
    def now(state: str, action: str, evidence: dict[str, Any], outcome: str = "") -> "DecisionLogEntry":
        return DecisionLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            state=state,
            action=action,
            evidence=evidence,
            outcome=outcome,
        )


@dataclass
class DecisionLog:
    entries: list[DecisionLogEntry] = field(default_factory=list)

    def record(self, state: str, action: str, evidence: dict[str, Any], outcome: str = "") -> None:
        self.entries.append(DecisionLogEntry.now(state, action, evidence, outcome))

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(asdict(e)) for e in self.entries)

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.to_jsonl())

    @staticmethod
    def load(path: str) -> "DecisionLog":
        entries = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entries.append(DecisionLogEntry(**json.loads(line)))
        return DecisionLog(entries=entries)
