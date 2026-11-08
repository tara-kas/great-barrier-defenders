#!/usr/bin/env python3
"""Offline verification of the submitted episode and its documentation links.

This checks preserved evidence, not live service availability or model quality.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONT_DOOR = (
    'README.md', 'AGENTS.md', 'CLAUDE.md', 'SETUP.md',
    'docs/README.md', 'docs/ARCHITECTURE.md', 'docs/EVIDENCE.md',
    'docs/IMPLEMENTATION_STATUS.md', 'docs/SCENARIOS.md', 'docs/JUDGING_GUIDE.md',
    'docs/EDGE_DEPLOYMENT.md',
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

    evidence_dir = root / 'docs/evidence'

    def artifact(name: str) -> Path:
        """Resolve manifest entries only within the preserved evidence directory."""
        if not isinstance(name, str) or not name:
            raise ValueError('Evidence artifact name must be nonempty text')
        path = (evidence_dir / name).resolve()
        if not path.is_relative_to(evidence_dir.resolve()):
            raise ValueError(f'Evidence artifact leaves its directory: {name}')
        return path

    def finite_number(value: object, minimum: float = 0) -> bool:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= minimum)

    try:
        index = json.loads(artifact('readiness-run-index.json').read_text())
        check(index['schema'] == 'reef-readiness-runs/v1', 'Unexpected readiness index schema')
        runs = index['runs']
        if not isinstance(runs, list) or not runs:
            raise ValueError('Readiness index must contain recorded runs')
        seen = set()
        for run in runs:
            name = run['path']
            check(name not in seen, f'Duplicate readiness run: {name}')
            seen.add(name)
            raw = artifact(name).read_bytes()
            episode = json.loads(raw)
            check(hashlib.sha256(raw).hexdigest() == run['sha256'], f'Readiness run SHA-256 differs: {name}')
            check(episode['exportedAt'] == run['exportedAt'], f'Readiness export timestamp differs: {name}')
            check(episode['episode']['phase'] == run['phase'], f'Readiness phase differs: {name}')
            check(episode['episode']['metrics'] == run['metrics'], f'Readiness metrics differ: {name}')
            check(episode['episode']['controller'] == 'base_station', f'Readiness controller is not model-connected: {name}')
            if 'siteSourceCommit' in run:
                check(bool(re.fullmatch(r'[0-9a-f]{40}', run['siteSourceCommit'])), f'Invalid recorded Site revision: {name}')
            else:
                source = run['sourceManifest']
                source_raw = artifact(source['path']).read_bytes()
                check(hashlib.sha256(source_raw).hexdigest() == source['sha256'], f'Runtime source manifest SHA-256 differs: {name}')
                manifest = json.loads(source_raw)
                if 'files' in manifest:
                    hashes = manifest['files']
                    check(manifest['remoteVerified'] is True and isinstance(hashes, dict) and bool(hashes)
                          and all(re.fullmatch(r'[0-9a-f]{64}', digest) for digest in hashes.values()),
                          f'Runtime source snapshot was incomplete or mismatched: {name}')
                else:
                    check(manifest['mismatches'] == [] and manifest['fileCount'] == len(manifest['sha256']),
                          f'Runtime source snapshot was incomplete or mismatched: {name}')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(f'Cannot validate readiness runs: {exc}')

    try:
        benchmark = json.loads(artifact('edge_gemma_benchmark.json').read_text())
        metadata = json.loads(artifact('edge_runtime_metadata.json').read_text())
        check(benchmark['schema'] == 'reef-edge-benchmark/v1', 'Unexpected edge benchmark schema')
        check(benchmark['deployment'] == metadata, 'Edge metadata differs from embedded deployment record')
        check(metadata['networkMode'] == 'none', 'Edge benchmark was not recorded with network mode none')
        check(metadata['running'] is True, 'Edge serving container was not recorded as running')
        interfaces = {line.split(':', 1)[0].strip() for line in metadata['networkInterfaces'].splitlines() if ':' in line}
        check(interfaces == {'lo'}, 'Edge network record contains interfaces other than loopback')
        routes = [line for line in metadata['networkRoutes'].splitlines() if line.strip()]
        check(len(routes) == 1 and routes[0].split()[0] == 'Iface', 'Edge network record contains routes or lacks its header')
        limit = metadata['memoryLimitBytes']
        check(type(limit) is int and limit > 0, 'Edge container lacks a positive memory limit')
        check(benchmark['machine'] == metadata['architecture'], 'Edge machine architecture differs from metadata')
        endpoint = urlsplit(benchmark['endpoint'])
        check(endpoint.scheme == 'http' and endpoint.hostname in ('127.0.0.1', 'localhost', '::1')
              and not endpoint.username and not endpoint.password, 'Edge inference endpoint is not unauthenticated loopback HTTP')
        model = benchmark['model']
        check(model == 'gemma-4-E4B-it', 'Unexpected edge Gemma model')
        check(any(item.get('id') == model and item.get('root') == 'google/gemma-4-E4B-it'
                  for item in benchmark['servedModels']['data']), 'Edge served-model record does not identify the requested Gemma weights')
        image = artifact(benchmark['image']['name']).read_bytes()
        check(hashlib.sha256(image).hexdigest() == benchmark['image']['sha256'], 'Edge input image SHA-256 differs')
        check(len(image) == benchmark['image']['bytes'], 'Edge input image byte count differs')
        samples = benchmark['samples']
        check(len(samples) == 5 and benchmark['summary']['completed'] == 5
              and benchmark['summary']['requested'] == 5, 'Expected five completed edge image-inference samples')
        response_ids, latencies = set(), []
        fields = {'targetVisible', 'objectKind', 'appearance', 'confidence', 'visualEvidence',
                  'uncertainty', 'fragmentVisible', 'gripperState'}
        for position, sample in enumerate(samples):
            check(sample['index'] == position, 'Edge sample indexes are not sequential')
            check(finite_number(sample['latencySeconds']) and sample['latencySeconds'] > 0, 'Invalid edge sample latency')
            latencies.append(sample['latencySeconds'])
            response = sample['response']
            check(response['model'] == model, 'Edge response model differs from requested model')
            check(isinstance(response['id'], str) and bool(response['id']) and response['id'] not in response_ids,
                  'Missing or duplicate edge response ID')
            response_ids.add(response['id'])
            choice = response['choices'][0]
            check(choice['finish_reason'] == 'stop', 'Edge response did not finish normally')
            check(choice['message']['role'] == 'assistant', 'Edge response has an unexpected message role')
            parsed = json.loads(choice['message']['content'])
            check(parsed == sample['parsed'], 'Edge parsed output differs from raw model response')
            check(isinstance(parsed, dict) and set(parsed) == fields, 'Edge output does not match the visual schema')
            check(type(parsed['targetVisible']) is bool and type(parsed['fragmentVisible']) is bool, 'Edge visibility fields are not boolean')
            check(parsed['objectKind'] in ('coral_colony', 'coral_fragment', 'other', 'unknown'), 'Invalid edge object kind')
            check(parsed['appearance'] in ('pigmented', 'pale_or_bleached', 'bare_skeleton_or_algae', 'unknown'), 'Invalid edge appearance')
            check(parsed['gripperState'] in ('empty', 'holding', 'unknown'), 'Invalid edge gripper state')
            check(finite_number(parsed['confidence']) and parsed['confidence'] <= 1, 'Invalid edge confidence score')
            check(isinstance(parsed['visualEvidence'], str) and isinstance(parsed['uncertainty'], str), 'Invalid edge visual evidence text')
        for name, value in (('latencyMinSeconds', min(latencies)), ('latencyMedianSeconds', statistics.median(latencies)),
                            ('latencyMaxSeconds', max(latencies))):
            check(math.isclose(value, benchmark['summary'][name], rel_tol=1e-9), f'Edge latency summary differs: {name}')
        resources = benchmark['resourceSamples']
        check(bool(resources), 'Missing edge resource samples')
        check(benchmark['resourceErrors'] == [], 'Edge resource collection reported errors')
        for sample in resources:
            memory = sample['containerMemoryBytes']
            current, peak = memory['memory.current'], memory['memory.peak']
            check(type(current) is int and type(peak) is int and 0 < current <= peak <= limit,
                  'Edge cgroup memory evidence is invalid or exceeds the recorded container limit')
        # Schema-valid observations and cgroup records establish inference and
        # measured resource scope, not classification accuracy or a robot mission.
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError) as exc:
        errors.append(f'Cannot validate edge inference evidence: {exc}')

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
    print('PASS: raw episode integrity, readiness runs, edge inference evidence and documentation targets')
