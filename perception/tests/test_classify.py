import numpy as np
import pytest

from perception.classify import (
    CORAL_TYPES, RESPONSE_SCHEMA, ClassificationError, classify_crop, crop_box, normalise_type, parse_response,
)
from perception.tests.fakes import FakeLLM, cls_json


def test_clean_json():
    r = parse_response(cls_json("BLEACHED", "acropora_table", 0.5, 0.8))
    assert (r.species_class, r.health_status, r.health_score, r.confidence) == ("acropora_table", "BLEACHED", 0.5, 0.8)
    assert r.is_coral and not r.should_abstain()


def test_fenced_json_with_prose():
    text = 'Sure! Here is the result:\n```json\n{"health_status": "dead", "coral_type": "Brain coral", "health_score": 0.1, "confidence": 0.7, "is_coral": true, "evidence": "grey skeleton {with algae}"}\n```'
    r = parse_response(text)
    assert r.health_status == "DEAD"
    assert r.species_class == "massive_meandering"
    assert r.evidence == "grey skeleton {with algae}"


@pytest.mark.parametrize(
    "raw,expected",
    [("Acropora", "acropora_branching"), ("table acropora", "acropora_table"), ("Pocillopora", "pocillopora"),
     ("branching", "branching_other"), ("massive/meandering", "massive_meandering"), ("sea fan", "other_coral"),
     (None, "other_coral")],
)
def test_type_normalisation(raw, expected):
    assert normalise_type(raw) == expected


def test_healthy_synonym_and_percent_values():
    r = parse_response('{"health_status": "Healthy", "health_score": 85, "confidence": 90}')
    assert r.health_status == "LIVE" and r.health_score == 0.85 and r.confidence == 0.9


def test_score_clamped_into_status_band():
    assert parse_response(cls_json("DEAD", score=0.9)).health_score == 0.3
    assert parse_response(cls_json("LIVE", score=0.1)).health_score == 0.6


def test_missing_score_uses_band_midpoint():
    assert parse_response('{"health_status": "DEAD", "confidence": 0.8}').health_score == 0.15


@pytest.mark.parametrize(
    "text",
    ["no json here", '{"health_status": "SICK", "confidence": 0.9}', '{"health_status": "LIVE"}',
     '{"health_status": "LIVE", "confidence": "very"}'],
)
def test_bad_outputs_raise(text):
    with pytest.raises(ClassificationError):
        parse_response(text)


def test_abstain_on_low_confidence_or_not_coral():
    assert parse_response(cls_json(conf=0.4)).should_abstain()
    assert parse_response(cls_json(is_coral="false")).should_abstain()


def test_classify_crop_uses_llm_and_records_latency():
    llm = FakeLLM([cls_json("DEAD", "pocillopora", 0.1, 0.95)])
    r = classify_crop(llm, np.zeros((32, 32, 3), dtype=np.uint8))
    assert r.health_status == "DEAD" and r.latency_ms == 12.0
    assert "raw_text" not in r.to_evidence()


def test_schema_enums_match_constants():
    assert RESPONSE_SCHEMA["properties"]["coral_type"]["enum"] == list(CORAL_TYPES)


def test_crop_box_pads_and_clips():
    img = np.zeros((100, 100, 3))
    assert crop_box(img, (10, 10, 60, 60)).shape == (60, 60, 3)
    assert crop_box(img, (0, 0, 100, 100)).shape == (100, 100, 3)
