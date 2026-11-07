"""Offline tests: every Argon response here is canned, so nothing touches the network."""

import json
import math
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agent.decision_log import DecisionLog, DecisionLogEntry
from cloud import debrief as d
from cloud.report import render_html

SAMPLES = Path(__file__).parent / "sample_logs"
FLAWED = SAMPLES / "fabricated_flawed.jsonl"
CLEAN = SAMPLES / "fabricated_clean.jsonl"

ISSUES = {
    "verdict": "issues_found",
    "summary": "Two clusters restored.",
    "suspect_transitions": [{
        "entry_index": 5,
        "severity": "high",
        "issue": "Normal below threshold.",
        "citations": [
            {"path": "evidence.normal_dot_z", "value": "0.71"},
            {"path": "evidence.normal_dot_z_min", "value": "0.866"},
        ],
    }],
    "suggested_patch": {
        "target": "agent/fsm.py:graft_check",
        "current_value": "none",
        "proposed_value": "reject below minimum",
        "rationale": "Enforce the limit.",
        "addresses_entries": [5],
    },
}
CLEAN_REPLY = {"verdict": "clean", "summary": "Nominal.", "suspect_transitions": [], "suggested_patch": None}


class FakeClient:
    def __init__(self, reply, status="completed"):
        self.calls = []
        self.interactions = self
        self.reply, self.status = reply, status

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="v1_test", status=self.status, model=d.MODEL_ID,
            output_text=self.reply if isinstance(self.reply, str) else json.dumps(self.reply),
            usage=SimpleNamespace(total_input_tokens=10, total_output_tokens=5, total_thought_tokens=2, total_tokens=17),
        )


def entry(**evidence):
    return DecisionLogEntry("2026-11-07T14:00:00+00:00", "S", "a", evidence, "done")


def run_main(tmp_path, client, *extra, log=FLAWED):
    out = tmp_path / "out.json"
    return d.main(["--log", str(log), "--out", str(out), *extra], client=client), out


def test_request_uses_argon_with_schema_and_no_legacy_params():
    client = FakeClient(ISSUES)
    d.call_argon(client, DecisionLog.load(str(FLAWED)).entries, "high")
    call = client.calls[0]
    assert call["model"] == "gemini-4-argon"
    assert call["generation_config"] == {"thinking_level": "high"}
    assert call["response_format"]["schema"] == d.Debrief.model_json_schema()


def test_answer_key_never_reaches_argon():
    prompt = d.build_input(DecisionLog.load(str(FLAWED)).entries) + d.SYSTEM_INSTRUCTION
    assert "planted" not in prompt.lower()
    assert "expected" not in prompt.lower()


@pytest.mark.parametrize("reply", [
    {**CLEAN_REPLY, "suspect_transitions": ISSUES["suspect_transitions"]},
    {**CLEAN_REPLY, "suggested_patch": ISSUES["suggested_patch"]},
    {**ISSUES, "suggested_patch": None},
    {**ISSUES, "suspect_transitions": []},
    {**ISSUES, "verdict": "fine"},
])
def test_inconsistent_debriefs_are_rejected(reply):
    with pytest.raises(ValidationError):
        d.Debrief.model_validate(reply)


def test_a_flag_needs_at_least_one_citation():
    suspect = {**ISSUES["suspect_transitions"][0], "citations": []}
    with pytest.raises(ValidationError):
        d.Debrief.model_validate({**ISSUES, "suspect_transitions": [suspect]})


def check_one(path, value, evidence):
    suspect = {**ISSUES["suspect_transitions"][0], "entry_index": 0, "citations": [{"path": path, "value": value}]}
    debrief = d.Debrief.model_validate({**ISSUES, "suspect_transitions": [suspect]})
    return d.check_citations(debrief, [entry(**evidence)])[0]


@pytest.mark.parametrize("path,value,evidence,expected", [
    ("evidence.x", "0.71", {"x": 0.71}, "verified"),
    ("evidence.x", "0.710", {"x": 0.71}, "verified"),
    ("evidence.x", "true", {"x": True}, "verified"),
    ("evidence.x", "L-07", {"x": "L-07"}, "verified"),
    ("evidence.c.1.h", "0.9", {"c": [{"h": 0.1}, {"h": 0.9}]}, "verified"),
    ("outcome", "done", {}, "verified"),
    ("evidence.x", "null", {"x": None}, "verified"),
    ("evidence.x", "0", {"x": None}, "value_mismatch"),
    ("evidence.x", "0.72", {"x": 0.71}, "value_mismatch"),
    ("evidence.x", "abc", {"x": 0.71}, "value_mismatch"),
    ("evidence.missing", "1", {"x": 1}, "path_not_found"),
])
def test_citation_checks(path, value, evidence, expected):
    assert check_one(path, value, evidence)["citations"][0]["status"] == expected


def test_citing_an_entry_outside_the_log_is_caught():
    suspect = {**ISSUES["suspect_transitions"][0], "entry_index": 99}
    debrief = d.Debrief.model_validate({**ISSUES, "suspect_transitions": [suspect]})
    assert d.check_citations(debrief, [entry()])[0]["status"] == "entry_not_found"


def test_scoring_counts_hits_misses_and_extras():
    expected = {"planted_flaws": [
        {"id": "F1", "description": "", "entry_indexes": [1]},
        {"id": "F2", "description": "", "entry_indexes": [5]},
    ]}
    flags = {"suspect_transitions": [{"entry_index": 5}, {"entry_index": 8}]}
    score = d.score_against_expected(flags, expected)
    assert (score["caught"], score["total"], score["extra_flags"]) == (1, 2, [8])


def test_live_run_saves_a_record_and_html(tmp_path):
    html = tmp_path / "r.html"
    code, out = run_main(tmp_path, FakeClient(ISSUES), "--html", str(html))
    assert code == 0
    record = json.loads(out.read_text())
    assert record["meta"]["interaction_id"] == "v1_test"
    assert record["meta"]["usage"]["total_tokens"] == 17
    assert record["citation_checks"][0]["status"] == "verified"
    assert 'id="entry-5" open' in html.read_text()


def test_rerender_makes_no_call_and_says_so(tmp_path):
    _, out = run_main(tmp_path, FakeClient(ISSUES))
    html, client = tmp_path / "r.html", FakeClient(ISSUES)
    code = d.main(["--log", str(FLAWED), "--from-json", str(out), "--html", str(html)], client=client)
    assert code == 0 and client.calls == []
    assert "No API call was made" in html.read_text()


def test_rerender_refuses_a_different_log(tmp_path):
    _, out = run_main(tmp_path, FakeClient(ISSUES))
    assert d.main(["--log", str(CLEAN), "--from-json", str(out)], client=FakeClient(ISSUES)) == 1


def test_malformed_argon_output_fails_and_keeps_the_raw_text(tmp_path):
    code, out = run_main(tmp_path, FakeClient("not json"))
    assert code == 1 and not out.exists()
    assert out.with_suffix(".raw.txt").read_text() == "not json"


def test_incomplete_interaction_fails(tmp_path):
    code, out = run_main(tmp_path, FakeClient(ISSUES, status="incomplete"))
    assert code == 1 and not out.exists()


def test_empty_log_costs_no_call(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    client = FakeClient(ISSUES)
    assert run_main(tmp_path, client, log=empty)[0] == 1
    assert client.calls == []


@pytest.mark.parametrize("content", ["not json\n", '{"unexpected": 1}\n'])
def test_bad_log_is_reported_without_a_call(tmp_path, content):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(content)
    client = FakeClient(ISSUES)
    assert run_main(tmp_path, client, log=bad)[0] == 1
    assert client.calls == []


@pytest.mark.parametrize("content", [None, "not json", "[]", '{"note": "no flaws key"}'])
def test_bad_answer_key_costs_no_call(tmp_path, content):
    key = tmp_path / "key.json"
    if content is not None:
        key.write_text(content)
    client = FakeClient(ISSUES)
    assert run_main(tmp_path, client, "--expected", str(key))[0] == 1
    assert client.calls == []


@pytest.mark.parametrize("content", [None, "not json", "{}", '{"meta": {}}'])
def test_bad_saved_debrief_is_reported(tmp_path, content):
    saved = tmp_path / "saved.json"
    if content is not None:
        saved.write_text(content)
    client = FakeClient(ISSUES)
    assert d.main(["--log", str(FLAWED), "--from-json", str(saved)], client=client) == 1
    assert client.calls == []


def test_log_written_by_the_real_writer_is_accepted(tmp_path):
    log = DecisionLog()
    log.record("SURVEY_SEABED", "survey_complete", {"position": (1.0, 2.0)}, "ok")
    path = tmp_path / "mission.jsonl"
    log.save(str(path))
    client = FakeClient(CLEAN_REPLY)
    assert run_main(tmp_path, client, log=path)[0] == 0
    assert len(client.calls) == 1


def test_two_flags_on_one_entry_keep_their_own_status(capsys, tmp_path):
    good = ISSUES["suspect_transitions"][0]
    bad = {**good, "issue": "Second.", "citations": [{"path": "evidence.nope", "value": "1"}]}
    run_main(tmp_path, FakeClient({**ISSUES, "suspect_transitions": [good, bad]}))
    out = capsys.readouterr().out
    assert "entry 5 (verified)" in out and "entry 5 (unverified)" in out


def test_files_are_utf8_whatever_the_platform_default(tmp_path, monkeypatch):
    import pathlib

    written = []
    real = pathlib.Path.write_text
    monkeypatch.setattr(pathlib.Path, "write_text", lambda self, text, encoding=None, **kw: (
        written.append(encoding), real(self, text, encoding=encoding, **kw))[1])
    run_main(tmp_path, FakeClient(ISSUES), "--html", str(tmp_path / "r.html"))
    assert written == ["utf-8", "utf-8"]


@pytest.mark.parametrize("path,labelled", [
    ("cloud/sample_logs/fabricated_clean.jsonl", True),
    ("dashboard/demo/decisions.jsonl", True),
    ("eval/out/mission.jsonl", False),
])
def test_sample_logs_are_labelled_as_samples(path, labelled):
    record = {
        "debrief": CLEAN_REPLY,
        "citation_checks": [],
        "meta": {
            "model": "m", "interaction_id": "i", "thinking_level": "low", "latency_s": 1,
            "usage": {}, "created_at": "t", "log_path": path, "log_sha256": "abc", "entry_count": 0,
        },
    }
    assert ("not a real mission" in render_html(record, [])) is labelled


def test_missing_key_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert d.main(["--log", str(FLAWED), "--out", str(tmp_path / "o.json")]) == 1


def test_report_escapes_log_and_argon_text():
    attack = "<script>alert(1)</script>"
    reply = json.loads(json.dumps(ISSUES))
    reply["summary"] = attack
    reply["suspect_transitions"][0].update(entry_index=0, issue=attack)
    reply["suggested_patch"]["rationale"] = attack
    log = [asdict(DecisionLogEntry("t", attack, attack, {"k": attack}, attack))]
    record = {
        "debrief": reply,
        "citation_checks": [{"entry_index": 0, "status": "unverified", "citations": []}],
        "meta": {
            "model": "m", "interaction_id": "i", "thinking_level": "low", "latency_s": 1,
            "usage": {}, "created_at": "t", "log_path": "x.jsonl", "log_sha256": "abc", "entry_count": 1,
        },
    }
    assert "<script" not in render_html(record, log)


def test_report_keeps_flags_on_missing_entries_visible(tmp_path):
    reply = json.loads(json.dumps(ISSUES))
    reply["suspect_transitions"][0]["entry_index"] = 99
    html = tmp_path / "r.html"
    run_main(tmp_path, FakeClient(reply), "--html", str(html))
    assert "Normal below threshold." in html.read_text()


def test_samples_have_correct_pairing_costs():
    """A wrong sum in a sample would be a flaw nobody planted."""
    for path in (FLAWED, CLEAN):
        for row in DecisionLog.load(str(path)).entries:
            if row.action != "select_pair":
                continue
            ev, w = row.evidence, row.evidence["weights"]
            c = ev["chosen"]
            assert c["travel"] == pytest.approx(math.dist(ev["rov_position"], ev["station_position"]), abs=0.01)
            assert c["transfer"] == pytest.approx(math.dist(ev["station_position"], ev["recipient"]["position_world"]), abs=0.01)
            assert c["J"] == pytest.approx(w["w1"] * c["travel"] + w["w2"] * c["transfer"] - w["w3"] * c["health"], abs=0.01)


def test_clean_sample_pairs_only_matching_genets():
    for row in DecisionLog.load(str(CLEAN)).entries:
        if row.action == "select_pair":
            assert row.evidence["rack"]["genet_id"] == row.evidence["recipient"]["genet_id"]
            assert row.evidence["recipient"]["health_status"] == "BLEACHED"


def test_answer_key_points_at_the_flawed_entries():
    entries = DecisionLog.load(str(FLAWED)).entries
    key = {f["id"]: f["entry_indexes"][0] for f in json.loads((SAMPLES / "fabricated_flawed.expected.json").read_text())["planted_flaws"]}
    f1 = entries[key["F1"]].evidence
    assert f1["rack"]["genet_id"] != f1["recipient"]["genet_id"]
    assert entries[key["F2"]].evidence["normal_dot_z"] == 0.71
    assert entries[key["F3"]].evidence["contact_maintained"] is False
