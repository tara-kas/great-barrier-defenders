#!/usr/bin/env python3
"""Offline verification of the submitted episode and its documentation links.

This checks preserved evidence, not live service availability or model quality.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONT_DOOR = (
    'README.md', 'AGENTS.md', 'CLAUDE.md', 'SETUP.md',
    'docs/README.md', 'docs/ARCHITECTURE.md', 'docs/EVIDENCE.md',
    'docs/IMPLEMENTATION_STATUS.md', 'docs/SCENARIOS.md', 'docs/JUDGING_GUIDE.md',
)


def verify(root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    try:
        raw = (root / 'docs/evidence/live-model-episode.json').read_bytes()
        episode = json.loads(raw)
        summary = json.loads((root / 'sim/pelagic/docs/evidence/live_stack_completed_placement.json').read_text())
        check(hashlib.sha256(raw).hexdigest() == summary['sourceEpisodeSha256'], 'Raw episode SHA-256 differs from the recorded summary')
        check(episode['exportedAt'] == summary['recordedAt'], 'Export timestamp differs from the summary')
        state = episode['episode']
        check(state['controller'] == 'base_station', 'Recorded episode is not using the model-connected controller')
        for field in ('time', 'phase', 'status', 'completed', 'missionGoal', 'metrics'):
            check(state[field] == summary['result'][field], f'Result field differs: {field}')
        check(state['completed'] and state['metrics']['placed'] >= state['missionGoal'], 'Recorded mission did not reach its placement goal')
        perception = state['intelligence']['onboard']['lastPacket']
        planner = state['intelligence']['baseStation']
        check(perception == summary['lastPerception'], 'Last perception differs from summary')
        check(planner == summary['lastPlanner'], 'Last planner differs from summary')
        check(perception['model'] == 'gemma-4-E4B-it' and perception['deployment'] == 'modal', 'Unexpected recorded Gemma identity/hosting')
        check(perception['viabilityKnown'] is False, 'Visual evidence improperly claims known viability')
        check(bool(re.fullmatch(r'[0-9a-f]{64}', perception['inputImageSha256'])), 'Missing/invalid perception image hash')
        check(perception['frameTime'] <= perception['receivedTime'] <= state['time'], 'Perception chronology is inconsistent')
        check(planner['plan']['model'] == 'reef-local-policy-v1', 'Unexpected recorded policy')
        solver = planner['plan']['optimizer']
        check(solver['source'] == 'cuopt' and solver['status'] == 'solved', 'Recorded route lacks solved cuOpt evidence')
        check(solver['requestId'] == planner['plan']['requestId'], 'Solver and planner request IDs differ')
        check(episode['transportActivity'] == summary['transportActivity'], 'Transport records differ from summary')
        check(state['events'] == summary['events'], 'Episode events differ from summary')
        replies = [e['message'] for e in episode['transportActivity'] if e['type'] == 'response']
        check(sum('Gemma gemma-4-E4B-it responded' in m for m in replies) == 5, 'Expected five recorded Gemma replies')
        check(any('Argon assistance gemini-4-argon' in m and 'RESCAN' in m for m in replies), 'Missing recorded Argon rescan')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'Cannot validate evidence: {exc}')

    for name in FRONT_DOOR:
        document = root / name
        try:
            content = document.read_text()
        except OSError as exc:
            errors.append(f'Cannot read {name}: {exc}')
            continue
        # Inline links and reference definitions; ignore web URLs and same-file anchors.
        links = re.findall(r'!?\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)', content)
        links += re.findall(r'^\[[^\]]+\]:\s*(\S+)', content, re.MULTILINE)
        for link in links:
            link = link.strip('<>')
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (document.parent / unquote(parsed.path)).resolve()
            if not target.is_relative_to(root.resolve()):
                errors.append(f'{name}: local link leaves repository: {link}')
            elif not target.exists():
                errors.append(f'{name}: missing local link target: {link}')
    return errors


if __name__ == '__main__':
    failures = verify()
    if failures:
        for failure in failures:
            print(f'FAIL: {failure}', file=sys.stderr)
        sys.exit(1)
    print('PASS: raw episode integrity, summary consistency, model evidence and documentation targets')
