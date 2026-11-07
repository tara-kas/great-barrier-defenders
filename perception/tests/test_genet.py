import numpy as np
import pytest

from perception.genet import BANDS, GenetRecord, match_genet, read_signature

LIBRARY = [
    GenetRecord("A", "pocillopora", (0.1, 0.7, 0.2)),
    GenetRecord("B", "pocillopora", (0.12, 0.3, 0.58)),
    GenetRecord("C", "acropora_table", (0.1, 0.7, 0.2)),
]


def uv_image(signature, brightness=0.6):
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[20:80, 20:80] = np.clip(np.array(signature) @ BANDS * brightness * 255, 0, 255)
    return image


@pytest.mark.parametrize("signature", [(0.1, 0.7, 0.2), (0.55, 0.35, 0.1), (0.08, 0.22, 0.7)])
@pytest.mark.parametrize("brightness", [0.5, 0.9])
def test_signature_round_trips_at_any_brightness(signature, brightness):
    read = read_signature(uv_image(signature, brightness), (20, 20, 80, 80))
    assert np.abs(np.array(read) - np.array(signature)).sum() < 0.05


def test_dark_colony_gives_no_reading():
    assert read_signature(uv_image((0.1, 0.7, 0.2), 0.05), (20, 20, 80, 80)) is None


def test_close_signature_matches():
    assert match_genet("pocillopora", (0.11, 0.68, 0.21), LIBRARY).genet_id == "A"


def test_in_between_signature_is_no_match():
    match = match_genet("pocillopora", (0.11, 0.5, 0.39), LIBRARY)
    assert match.genet_id is None and match.nearest in ("A", "B")


def test_never_matches_across_species():
    assert match_genet("acropora_table", (0.12, 0.3, 0.58), LIBRARY).genet_id is None
    assert match_genet("stylophora", (0.1, 0.7, 0.2), LIBRARY).genet_id is None
