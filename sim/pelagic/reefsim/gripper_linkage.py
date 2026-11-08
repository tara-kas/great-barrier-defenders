"""Dimensions shared by the gripper renderer and connection checks (metres).

The contact origin stays at the coral grasp point. Sliding carriages connect
the fingers to the palm even when a broad natural branch needs a wide grasp.
"""
from __future__ import annotations

WRIST_CENTER = (-.100, 0., 0.)
PALM_CENTER = (-.075, 0., 0.)
PALM_SIZE = (.045, .120, .045)
CARRIAGE_SIZE = (.028, .028, .038)


def jaw_linkage(grasp_radius=.012, opening=1.):
    """Return connected tool-local slide geometry for both fingers.

    Rails overlap the palm by 25 mm and terminate inside their carriage.
    Carriages overlap the proximal finger capsule in X by at least 19 mm.
    The same mechanism therefore remains connected throughout its travel.
    """
    separation = max(0., float(grasp_radius)) + .006 + .038 * max(0., min(1., float(opening)))
    return tuple({
        "finger": (0., side * separation, 0.),
        "rail_start": (-.075, side * .035, 0.),
        "rail_end": (-.075, side * separation, 0.),
        "carriage": (-.066, side * separation, 0.),
    } for side in (-1, 1))
