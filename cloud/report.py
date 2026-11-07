"""Renders a debrief and its decision log as one self-contained HTML page.

Everything from the log or from Argon goes through _e(), so neither can inject
markup. No scripts and no external assets, so the file opens anywhere offline.
"""

import json
import re
from html import escape
from pathlib import Path
from typing import Any, Optional

FAILURE_WORDS = re.compile(r"fail|abort|reject|error|unreachable", re.IGNORECASE)
SAMPLE_LOG_PATH = re.compile(r"fabricated|/demo/")

CSS = """
:root {
  --bg: #f6f7f8; --panel: #ffffff; --ink: #1b2126; --muted: #5d6871; --line: #dfe3e7;
  --high: #c0342b; --high-bg: #fdecea; --medium: #b0650a; --medium-bg: #fdf2e0;
  --low: #47708f; --low-bg: #e9f1f7; --good: #1d7a54; --good-bg: #e3f4ec;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12171b; --panel: #1b2227; --ink: #e6eaed; --muted: #97a3ac; --line: #2e383f;
    --high: #f0837a; --high-bg: #3a1f1d; --medium: #e8ac5c; --medium-bg: #38291a;
    --low: #8dbad9; --low-bg: #1e2d38; --good: #6cd0a4; --good-bg: #17332a;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 960px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 32px 0 10px; }
p { margin: 0 0 10px; }
code, pre, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
.muted { color: var(--muted); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }
.banner { border-radius: 8px; padding: 10px 14px; margin-top: 12px; background: var(--medium-bg); color: var(--medium); }
.banner.live { background: var(--good-bg); color: var(--good); }
.verdict { display: inline-block; font-weight: 600; padding: 2px 10px; border-radius: 999px; margin: 8px 0; }
.verdict.clean { background: var(--good-bg); color: var(--good); }
.verdict.issues_found { background: var(--high-bg); color: var(--high); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin-top: 16px; }
.stat b { display: block; font-size: 18px; overflow-wrap: anywhere; }
.stat span { font-size: 12px; color: var(--muted); }
.change { font-size: 17px; margin: 6px 0 10px; overflow-wrap: anywhere; }
.change b { color: var(--good); }
.score-row { display: flex; gap: 10px; padding: 6px 0; border-top: 1px solid var(--line); }
.score-row:first-of-type { border-top: 0; }
.tag { flex: none; font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 999px; height: fit-content; }
.tag.good { background: var(--good-bg); color: var(--good); }
.tag.bad { background: var(--high-bg); color: var(--high); }
.tag.high { background: var(--high-bg); color: var(--high); }
.tag.medium { background: var(--medium-bg); color: var(--medium); }
.tag.low { background: var(--low-bg); color: var(--low); }
.entry { background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--line);
  border-radius: 6px; margin-bottom: 6px; scroll-margin-top: 12px; }
.entry.high { border-left-color: var(--high); }
.entry.medium { border-left-color: var(--medium); }
.entry.low { border-left-color: var(--low); }
.entry:target { outline: 2px solid var(--low); }
summary { cursor: pointer; padding: 8px 12px; display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; }
.idx { color: var(--muted); min-width: 2ch; }
.state { color: var(--muted); font-size: 12px; }
.outcome { margin-left: auto; color: var(--muted); }
.outcome.fail { color: var(--high); }
.body { padding: 0 12px 12px; }
.flag { padding: 8px 10px; border-radius: 6px; background: var(--bg); margin-bottom: 8px; }
.cite { display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline; margin-top: 4px; overflow-wrap: anywhere; }
pre { margin: 0; padding: 10px; background: var(--bg); border-radius: 6px; overflow-x: auto; }
"""


def _e(value: Any) -> str:
    return escape(str(value), quote=True)


def _source_banner(meta: dict, rerendered: bool) -> str:
    if rerendered:
        text = (f"Re-rendered from a saved debrief. No API call was made for this page. "
                f"The original call ran at {_e(meta['created_at'])}.")
        html = f'<div class="banner">{text}</div>'
    else:
        html = f'<div class="banner live">Live {_e(meta["model"])} call, made when this page was generated.</div>'
    if SAMPLE_LOG_PATH.search(Path(meta["log_path"]).as_posix()):
        html += ('<div class="banner">Input is a hand-written sample log, not a real mission. '
                 "The debrief is real; the mission it describes is not.</div>")
    return html


def _stats(meta: dict, flagged: int) -> str:
    usage = meta["usage"]
    items = [
        (meta["entry_count"], "log entries"),
        (flagged, "flagged"),
        (f"{meta['latency_s']}s", "Argon latency"),
        (usage.get("total_input_tokens"), "input tokens"),
        (usage.get("total_output_tokens"), "output tokens"),
        (usage.get("total_thought_tokens"), "thought tokens"),
    ]
    cells = "".join(f'<div class="stat"><b>{_e(v)}</b><span>{_e(k)}</span></div>' for v, k in items)
    return f'<div class="stats">{cells}</div>'


def _patch(patch: Optional[dict]) -> str:
    if not patch:
        return '<h2>Suggested patch</h2><div class="panel muted">None. Argon found nothing to change.</div>'
    links = ", ".join(f'<a href="#entry-{int(i)}">entry {int(i)}</a>' for i in patch["addresses_entries"])
    return (
        '<h2>Suggested patch</h2><div class="panel">'
        f'<div class="mono">{_e(patch["target"])}</div>'
        f'<div class="change">{_e(patch["current_value"])} &rarr; <b>{_e(patch["proposed_value"])}</b></div>'
        f'<p>{_e(patch["rationale"])}</p>'
        f'<div class="muted">Addresses {links or "no specific entry"}. '
        "Proposal only: nothing has been applied or tested.</div></div>"
    )


def _score(score: Optional[dict]) -> str:
    if score is None:
        return ""
    rows = "".join(
        f'<div class="score-row"><span class="tag {"good" if f["caught"] else "bad"}">'
        f'{"caught" if f["caught"] else "missed"}</span>'
        f'<span><b>{_e(f["id"])}</b> {_e(f["description"])}</span></div>'
        for f in score["flaws"]
    )
    if not score["flaws"]:
        rows = '<p class="muted">No flaws were planted in this log, so any flag below is a false positive.</p>'
    extras = score["extra_flags"]
    extra = ""
    if extras:
        links = ", ".join(f'<a href="#entry-{int(i)}">{int(i)}</a>' for i in extras)
        extra = f'<p class="muted">Flagged beyond the answer key: entries {links}. Read these by hand.</p>'
    return (f'<h2>Planted flaw check: {score["caught"]}/{score["total"]} caught</h2>'
            f'<div class="panel">{rows}{extra}</div>')


def _flag(suspect: dict, check: Optional[dict]) -> str:
    statuses = {c["path"]: c["status"] for c in (check or {}).get("citations", [])}
    cites = ""
    for citation in suspect["citations"]:
        status = statuses.get(citation["path"], "unchecked")
        tag = "good" if status == "verified" else "bad"
        label = "in log" if status == "verified" else status.replace("_", " ")
        cites += (f'<div class="cite"><span class="tag {tag}">{_e(label)}</span>'
                  f'<code>{_e(citation["path"])} = {_e(citation["value"])}</code></div>')
    severity = _e(suspect["severity"])
    return f'<div class="flag"><span class="tag {severity}">{severity}</span> {_e(suspect["issue"])}{cites}</div>'


def _timeline(entries: list[dict], debrief: dict, checks: list[dict]) -> str:
    rank = {"high": 3, "medium": 2, "low": 1}
    flags: dict[int, list[str]] = {}
    worst: dict[int, str] = {}
    for suspect, check in zip(debrief["suspect_transitions"], checks):
        index = suspect["entry_index"]
        flags.setdefault(index, []).append(_flag(suspect, check))
        if rank[suspect["severity"]] > rank.get(worst.get(index, ""), 0):
            worst[index] = suspect["severity"]

    rows = []
    for index, entry in enumerate(entries):
        outcome = entry.get("outcome", "")
        fail = " fail" if FAILURE_WORDS.search(outcome) else ""
        flagged = index in flags
        evidence = _e(json.dumps(entry["evidence"], indent=2))
        rows.append(
            f'<details class="entry {worst.get(index, "")}" id="entry-{index}"{" open" if flagged else ""}>'
            f'<summary><span class="idx mono">{index}</span>'
            f'<span class="mono">{_e(entry["action"])}</span>'
            f'<span class="state">{_e(entry["state"])}</span>'
            f'<span class="outcome{fail}">{_e(outcome)}</span></summary>'
            f'<div class="body">{"".join(flags.get(index, []))}'
            f'<details><summary class="muted">Raw evidence · {_e(entry["timestamp"])}</summary>'
            f"<pre>{evidence}</pre></details></div></details>"
        )
    return "<h2>Mission timeline</h2>" + "".join(rows)


def _orphan_flags(entries: list[dict], debrief: dict, checks: list[dict]) -> str:
    """Flags pointing at entries that do not exist would otherwise vanish from the page."""
    orphans = [
        _flag(s, c) for s, c in zip(debrief["suspect_transitions"], checks)
        if not 0 <= s["entry_index"] < len(entries)
    ]
    if not orphans:
        return ""
    return '<h2>Flags citing entries not in the log</h2><div class="panel">' + "".join(orphans) + "</div>"


def render_html(record: dict, entries: list[dict], score: Optional[dict] = None, rerendered: bool = False) -> str:
    debrief, meta, checks = record["debrief"], record["meta"], record["citation_checks"]
    verdict = debrief["verdict"]
    label = "No issues found" if verdict == "clean" else "Issues found"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mission Debrief</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>Mission debrief</h1>
<div class="muted mono">{_e(meta["log_path"])}</div>
{_source_banner(meta, rerendered)}
<div class="verdict {_e(verdict)}">{label}</div>
<div class="panel"><p>{_e(debrief["summary"])}</p>{_stats(meta, len(debrief["suspect_transitions"]))}</div>
{_patch(debrief["suggested_patch"])}
{_score(score)}
{_orphan_flags(entries, debrief, checks)}
{_timeline(entries, debrief, checks)}
<p class="muted mono" style="margin-top:24px;overflow-wrap:anywhere">interaction {_e(meta["interaction_id"])} · thinking {_e(meta["thinking_level"])} · log sha256 {_e(meta["log_sha256"][:12])}</p>
</main>
</body>
</html>
"""
