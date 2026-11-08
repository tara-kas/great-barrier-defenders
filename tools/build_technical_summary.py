#!/usr/bin/env python3
"""Build the two-page submission brief from committed evidence (requires reportlab).

Run from any directory. Numeric observations come from the saved artifacts;
editing prose cannot silently change the measurements or combine episode outcomes.
After rebuilding, render with pdftoppm and inspect both pages before publication.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
from statistics import mean, median
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[1]
INK = colors.HexColor('#183a3c')
TEAL = colors.HexColor('#1b6b66')
MUTED = colors.HexColor('#526b69')
LINE = colors.HexColor('#d6e1dc')
PALE = colors.HexColor('#e9f2ed')
PAPER = colors.HexColor('#fafbf8')
AMBER = colors.HexColor('#f4eddd')
WIDTH = A4[0] - 84
GIB = 1024 ** 3


def load(root, name):
    path = root / 'docs/evidence' / name
    return json.loads(path.read_text()), hashlib.sha256(path.read_bytes()).hexdigest()


def seconds(events, model):
    values = []
    for event in events:
        pattern = rf'^{model} .*?responded in (\d+)ms' if model == 'Gemma' else r'^Argon assistance .*?\((\d+)ms\)'
        match = re.search(pattern, event.get('message', ''))
        if match:
            values.append(int(match.group(1)) / 1000)
    if not values:
        raise ValueError(f'No measured {model} responses in the selected episode')
    return values


def build(root, output):
    live, live_hash = load(root, 'live-model-episode.json')
    edge, edge_hash = load(root, 'edge_gemma_benchmark.json')
    metadata, _ = load(root, 'edge_runtime_metadata.json')
    episode = live['episode']
    metrics = episode['metrics']
    if episode['phase'] != 'complete':
        raise ValueError('The selected completed-episode evidence is not complete')
    gemma = seconds(live['transportActivity'], 'Gemma')
    argon = seconds(live['transportActivity'], 'Argon')
    optimizer = episode['decision']['planning']['optimizer']
    edge_latencies = [sample['latencySeconds'] for sample in edge['samples']]
    resource = edge['resourceSamples']
    peak = max(sample['containerMemoryBytes']['memory.peak'] for sample in resource) / GIB
    current = max(sample['containerMemoryBytes']['memory.current'] for sample in resource) / GIB
    # nvidia-smi CSV columns are name, temperature, power, memory used, memory total.
    power = [float(sample['gpuCsv'].split(',')[2]) for sample in resource]
    cutoff = max(edge['recordedAtUtc'], live['exportedAt'])[:16].replace('T', ' ')

    styles = {
        'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=28, leading=31, textColor=INK, spaceAfter=6),
        'subtitle': ParagraphStyle('subtitle', fontName='Helvetica', fontSize=11, leading=15, textColor=MUTED, spaceAfter=15),
        'section': ParagraphStyle('section', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=TEAL, spaceBefore=11, spaceAfter=7),
        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9.2, leading=13, textColor=INK, spaceAfter=7),
        'small': ParagraphStyle('small', fontName='Helvetica', fontSize=8, leading=10.8, textColor=MUTED, spaceAfter=6),
        'cell': ParagraphStyle('cell', fontName='Helvetica', fontSize=8.5, leading=11.4, textColor=INK),
        'head': ParagraphStyle('head', fontName='Helvetica-Bold', fontSize=8.1, leading=11, textColor=TEAL),
        'metric': ParagraphStyle('metric', fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=TEAL),
    }
    def p(text, style='body'):
        return Paragraph(text, styles[style])
    def section(text):
        return p(text.upper(), 'section')
    def table(rows, widths, header=True):
        values = [[p(value, 'head' if header and i == 0 else 'cell') for value in row] for i, row in enumerate(rows)]
        result = Table(values, colWidths=widths, hAlign='LEFT')
        commands = [('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 9),
                    ('RIGHTPADDING', (0,0), (-1,-1), 9), ('TOPPADDING', (0,0), (-1,-1), 6),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 6), ('LINEBELOW', (0,0), (-1,-1), .4, LINE)]
        if header:
            commands.append(('BACKGROUND', (0,0), (-1,0), PALE))
        result.setStyle(TableStyle(commands))
        return result
    def box(text, fill=PALE):
        result = Table([[p(text)]], colWidths=[WIDTH])
        result.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),fill),('LEFTPADDING',(0,0),(-1,-1),12),
                                   ('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),
                                   ('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        return result

    story = [p('Reef Rescue', 'title'), p('Perception-guided coral handling, with a reviewable evidence trail.', 'subtitle')]
    story += [section('The scenario'), p('For reef-restoration teams, the prototype inspects a registered, already-detached coral fragment, transports it to an eligible bleached recipient and verifies mechanical attachment. Supplied registry facts establish species, lineage and eligibility. The loose-fragment workflow does not cut a healthy colony.')]
    story += [table([
        ['1 / OBSERVE', '2 / DECIDE', '3 / ACT & VERIFY'],
        ['Rendered robot-camera RGB<br/><b>Gemma appearance evidence</b>', 'Fresh evidence + registry<br/><b>Local policy + native cuOpt</b>', 'Browser safety and controller<br/><b>Collect, place, verify</b>'],
    ], [WIDTH/3]*3), Spacer(1,7), p('<b>Uncertainty:</b> hold and ask Argon for <b>rescan, hold or abort</b>. Argon supplies bounded context and visual checks for Gemma’s next fresh image. Registry and local handling gates remain authoritative; Argon receives structured observations.', 'small')]
    story += [section('Models and authority'), table([
        ['Component / exact identifier', 'Execution and responsibility'],
        ['<b>Gemma</b><br/>gemma-4-E4B-it', 'Weights: google/gemma-4-E4B-it. Hosted vLLM on Modal; separately measured on Spark GB10 (page 2). Reports appearance, target visibility and fragment/gripper state.'],
        ['<b>Gemini Argon</b><br/>gemini-4-argon', 'Google Interactions API. Bounded held-issue advice and optional terminal review. No automatic code changes or deployment.'],
        ['<b>NVIDIA cuOpt</b><br/>nvidia-cuopt', f'Native route evaluation on Modal; recorded solver {escape(optimizer["solverVersion"])}. Chooses among supplied alternatives, subject to local validation.'],
        ['<b>Policy / controller</b><br/>reef-local-policy-v1', 'Inspectable Python gateway policy; browser mission controller, reduced physics and safety checks remain authoritative.'],
    ], [170, WIDTH-170])]
    story += [section('Measured hosted episode [1]'), box(f'<b>{metrics["placed"]} verified placement</b> in <b>{episode["time"]:.2f} simulated seconds</b>; {metrics["collisions"]} collisions, {metrics["drops"]} drops and {metrics["recoveries"]} fragment recoveries. {len(gemma)} camera responses, uncertain evidence, Argon-assisted rescan and a sensor-dropout hold precede successful placement.')]
    story += [Spacer(1,6), table([
        ['Measurement', 'Observed value', 'Scope'],
        ['Gemma request latency', f'{min(gemma):.3f}-{max(gemma):.3f} s; n={len(gemma)}', 'Browser round trip'],
        ['Argon assistance latency', f'{argon[0]:.3f} s; n={len(argon)}', 'Browser round trip'],
        ['cuOpt solve time', f'{optimizer["solveTimeMs"]/1000:.3f} s; n=1', 'Native solver duration'],
    ], [180,140,WIDTH-320])]
    story += [Spacer(1,7), p('<b>Run the pipeline.</b> Configure Gemma, native cuOpt and Argon on the gateway. Load the compact scene through Environment builder, select Robot + base, wait for service readiness and start the mission. Export captures, provider receipts and outcome counters together. [3]', 'small')]
    story += [section('Reproduce and audit'), p('Run <font name="Courier">python3 sim/pelagic/scripts/run_lab.py</font>; configure actual services using SETUP.md. Verify with <font name="Courier">python3 tools/verify_submission.py</font> and the documented test suites.', 'small')]
    story += [p(f'[1] docs/evidence/live-model-episode.json - {live["exportedAt"][:19].replace("T"," ")} UTC; SHA-256 {live_hash[:16]}...<br/>[2] docs/EDGE_DEPLOYMENT.md and docs/evidence/edge_gemma_benchmark.json - SHA-256 {edge_hash[:16]}...<br/>[3] SETUP.md and docs/IMPLEMENTATION_STATUS.md. Artifact format and hashes: docs/EVIDENCE.md; rubric: docs/JUDGING_GUIDE.md.', 'small')]
    story += [PageBreak(), p('Measured edge operation', 'title'), p('Pinned Gemma inference and native route services on NVIDIA GB10.', 'subtitle')]
    story += [box(f'<b>{edge["summary"]["completed"]}/{edge["summary"]["requested"]} valid structured image responses on NVIDIA GB10.</b> The Spark container used Docker network mode <b>{escape(metadata["networkMode"])}</b>, with only loopback and no network routes. Model weights were downloaded beforehand. [2]')]
    story += [section('Observed resource budget [2]'), table([
        ['Measurement', 'Result and interpretation'],
        ['Image request latency', f'Median {median(edge_latencies):.3f} s; range {min(edge_latencies):.3f}-{max(edge_latencies):.3f} s. {len(edge_latencies)} repeats of one saved Isaac-rendered image; first-use compilation and warm caches affect timing.'],
        ['Container memory', f'Lifetime cgroup peak {peak:.3f} GiB; peak sampled memory.current {current:.3f} GiB. These are not total unified CPU + GPU memory.'],
        ['Configured limits', f'{metadata["memoryLimitBytes"]/GIB:.0f} GiB memory, {metadata["nanoCpusLimit"]/1e9:g} CPU cores, BF16, one request sequence, 4,096-token context, eager execution. Limits are not measurements.'],
        ['Shared GPU power', f'{min(power):.2f}-{max(power):.2f} W; sample mean {mean(power):.3f} W across {len(resource)} samples. Isaac and other processes shared the GPU; this is not isolated Gemma power or vehicle energy.'],
        ['Pinned model / runtime', f'google/gemma-4-E4B-it; revision {escape(metadata["command"][metadata["command"].index("--revision")+1][:12])}...<br/>vLLM {escape(edge["runtimeVersions"]["vllm"])}; Transformers {escape(edge["runtimeVersions"]["transformers"])}. Full image digest and metadata: [2].'],
    ], [139,WIDTH-139])]
    story += [Spacer(1,7), p('The five image requests used the same recorded input and returned an <b>unknown gripper state</b>. The controller requires a matching visible fragment and gripper state before pickup. The browser gateway connects local Gemma and cuOpt with online Argon assistance.', 'small')]
    story += [section('Judging criteria: evidence a reviewer can inspect'), table([
        ['Criterion', 'Implementation and evidence'],
        ['25% / Perception-driven action', 'Image hashes, capture/target IDs and freshness gates connect Gemma observations to action. Appearance cannot establish viability or genotype.'],
        ['25% / Adaptation to change', 'Actual uncertain-view rescan and sensor-dropout hold in [1]. Current-induced loss and same-ID recovery are covered by controller/model-double regression tests.'],
        ['15% / Operational autonomy', 'Local safety continues during remote waits; assistance retains a 90-second overall hold and three-attempt limit. Disconnected Gemma image inference is measured in [2].'],
        ['20% / Relevance and impact', 'Registered fragment handling targets a concrete restoration workflow. Identity, damage and attachment checks are inspectable; ecological benefit and survival are not established.'],
        ['15% / Technical quality', 'Native cuOpt, explicit model provenance, cross-language contract tests, bounded memory and telemetry. Independent Isaac RTX feed is read-only; browser physics is separate.'],
    ], [165,WIDTH-165])]
    story += [Spacer(1,8), box('<b>Review and operation:</b> docs/CODE_MAP.md explains the files and entry points. SETUP.md provides service configuration and test commands. docs/EVIDENCE.md explains episode fields and source hashes; docs/IMPLEMENTATION_STATUS.md describes mission execution and service behavior.', AMBER)]

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(PAPER)
        canvas.rect(0,0,*A4,fill=1,stroke=0)
        canvas.setFillColor(TEAL)
        canvas.setFont('Helvetica-Bold',8)
        canvas.drawString(42,A4[1]-29,'REEF RESCUE  /  TECHNICAL SUMMARY  /  ENGINEERING PROTOTYPE')
        canvas.setStrokeColor(LINE)
        canvas.line(42,35,A4[0]-42,35)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica',7)
        canvas.drawString(42,23,f'Evidence cutoff: {cutoff} UTC  |  Great Barrier Defenders')
        canvas.drawRightString(A4[0]-42,23,f'{doc.page} / 2')
        canvas.restoreState()

    # Keep the previous deliverable intact when revised content overflows.
    buffer = io.BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=48,bottomMargin=45,
        title='Reef Rescue - Technical Summary',author='Great Barrier Defenders',pageCompression=1)
    doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
    if doc.page != 2:
        raise ValueError(f'Expected two pages; rendered {doc.page}. Adjust layout and inspect before publication.')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(buffer.getvalue())
    print(json.dumps({'output':str(output),'pages':doc.page,'live_episode_sha256':live_hash,'edge_sha256':edge_hash}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/submission/technical-summary-current.pdf')
    args=parser.parse_args()
    build(args.root.resolve(),args.output.resolve())
