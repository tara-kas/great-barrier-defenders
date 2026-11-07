import json

import pytest

from agent.base_station import BaseStation, Rack


def station():
    return BaseStation((1.0, 2.0, 0.0), [Rack("R1", "g1", "a", 1, 0.9)])


def test_take_and_put_back_track_stock():
    s = station()
    assert s.take("g1").slot == "R1"
    assert s.available("g1") == 0
    s.put_back("g1")
    assert s.stock() == {"g1": 1}


def test_taking_from_an_empty_rack_is_refused():
    s = station()
    s.take("g1")
    with pytest.raises(ValueError):
        s.take("g1")


def test_unknown_genet_has_no_stock():
    assert station().available("nope") == 0
    assert station().rack_for("nope") is None


def test_loads_the_dataset_format(tmp_path):
    path = tmp_path / "base_station.json"
    path.write_text(json.dumps({"position_world": [1, 2, 0], "racks": [
        {"slot": "R1", "genet_id": "g1", "species_class": "a", "fragments_available": 2,
         "health_status": "LIVE", "health_score": 0.9, "uv_signature": [0.1, 0.2, 0.7]},
    ]}))
    assert BaseStation.load(path).available("g1") == 2
