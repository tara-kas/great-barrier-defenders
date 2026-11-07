import json

import pytest

from perception.classify import ClassificationError
from perception.detect import DetectionError, parse_detections


def test_normalised_boxes_to_pixels():
    text = json.dumps({"objects": [{"label": "dead coral", "box_2d": [100, 200, 500, 600]}]})
    (d,) = parse_detections(text, width=1000, height=500)
    assert d.box_xyxy == (200, 50, 600, 250) and d.label == "dead coral"


def test_bare_list_and_fences_accepted():
    assert len(parse_detections('```json\n[{"label": "c", "box_2d": [0, 0, 500, 500]}]\n```', 100, 100)) == 1


def test_swapped_clipped_tiny_malformed_and_duplicate_boxes():
    text = json.dumps({"objects": [
        {"label": "a", "box_2d": [500, 500, 0, 0]},        # swapped -> fixed
        {"label": "b", "box_2d": [0, 0, 1200, 1200]},      # clipped to image
        {"label": "tiny", "box_2d": [0, 0, 10, 10]},       # 1px -> dropped
        {"label": "bad", "box_2d": [0, 0, 10]},            # malformed -> dropped
        {"label": "dup", "box_2d": [0, 0, 1000, 990]},     # IoU with b > 0.7 -> dropped
        "junk",
    ]})
    dets = parse_detections(text, 100, 100)
    assert [d.box_xyxy for d in dets] == [(0, 0, 50, 50), (0, 0, 100, 100)]


def test_empty_and_invalid():
    assert parse_detections('{"objects": []}', 100, 100) == []
    with pytest.raises(DetectionError):
        parse_detections('{"objects": "none"}', 100, 100)
    with pytest.raises(ClassificationError):
        parse_detections("nothing", 100, 100)
