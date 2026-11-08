"""Offline comparison layout using only supplied Isaac camera frames."""
from __future__ import annotations

from PIL import Image, ImageDraw

from .compositor import draw_brand, FONTS, _place_image, _text_fit


WIDTH, HEIGHT = 1600, 900
WHITE_BOX = (24, 131, 788, 561)
ACTIVE_BOX = (812, 131, 1576, 561)
ROBOT_BOX = (24, 605, 488, 866)
BG = (5, 19, 25)
INK = (225, 237, 233)
MUTED = (130, 163, 167)
TEAL = (107, 215, 195)
AMBER = (232, 185, 108)

HEALTH_TITLES = {"healthy": "HEALTHY / LIVING DONOR",
                 "bleached_alive": "BLEACHED / STILL ALIVE",
                 "dead": "DEAD / EXCLUDED"}
POLICY = {"healthy": "Donor only · never an assistance recipient",
          "bleached_alive": "Eligible for assistance · recovery is not simulated",
          "dead": "Excluded from assistance · dead tissue is not revived"}
MODE_TITLES = {"white": "WHITE INSPECTION LIGHT",
               "blue": "BLUE EXCITATION · 450 nm",
               "uv": "UV EXCITATION · 365 nm"}


def compose_inspection(white, active, robot, case, metadata, *, case_number=1,
                       case_count=15, elapsed=0., duration=45.):
    """Compare a cached white reference with the same live robot camera pose.

    This function never recolours the camera imagery. Emission comes from the
    scene material response; the overlay keeps known scenario labels separate
    from the observed RGB view.
    """
    mode = metadata["mode"]
    health = case["health"]
    profile = case["profile"]
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(canvas)
    draw_brand(draw)
    draw.text((218, 25), "ROBOT LIGHTING / CORAL APPEARANCE", font=FONTS["body"], fill=TEAL)
    draw.text((218, 54), "LOW-AMBIENT INSPECTION  ·  RGB RESPONSE PROXY  ·  OFFLINE", font=FONTS["tiny"], fill=MUTED)
    draw.text((1310, 22), f"CASE {case_number:02d} / {case_count:02d}", font=FONTS["body"], fill=INK)
    draw.text((1310, 51), "ISAAC SIM 6.0 · DGX SPARK", font=FONTS["tiny"], fill=MUTED)
    draw.line((24, 88, 1576, 88), fill=(40, 65, 70))
    draw.text((24, 103), "WHITE REFERENCE / SAME ROBOT CAMERA", font=FONTS["small"], fill=INK)
    draw.text((812, 103), MODE_TITLES[mode] + " / CURRENT VIEW", font=FONTS["small"], fill=TEAL)
    _place_image(canvas, white, WHITE_BOX)
    _place_image(canvas, active, ACTIVE_BOX)
    _place_image(canvas, robot, ROBOT_BOX)
    draw = ImageDraw.Draw(canvas)
    for box, color in ((WHITE_BOX, (73, 93, 92)), (ACTIVE_BOX, (75, 160, 151)),
                       (ROBOT_BOX, (52, 90, 95))):
        draw.rectangle(box, outline=color, width=1)
    draw.text((24, 579), "ROBOT-MOUNTED SOURCE / REEF CONTEXT", font=FONTS["tiny"], fill=MUTED)
    draw.text((520, 590), HEALTH_TITLES[health], font=FONTS["title"], fill=INK)
    group = profile["group"].upper()
    draw.text((520, 630), f"SCENARIO COLOUR GROUP: {group}  ·  {case['coral_id']}", font=FONTS["body"], fill=TEAL)
    draw.text((520, 663), POLICY[health], font=FONTS["body"], fill=INK)
    tag = profile.get("synthetic_genotype", "UNLABELLED")
    draw.text((520, 702), f"Known scenario lineage: {tag}  /  not inferred from colour", font=FONTS["small"], fill=MUTED)
    if profile.get("negative_control"):
        explanation = "Purple pigment control: living tissue can have little or no host fluorescence."
    elif health == "dead":
        explanation = "No host emission in this scenario; real algae and skeleton signals are not modelled."
    elif health == "bleached_alive":
        explanation = "Bleached living tissue retains host fluorescence here; a bright signal is not recovery."
    else:
        explanation = "Reflected pigment and emitted fluorescence are separate properties."
    _text_fit(draw, (520, 736), explanation, FONTS["small"], AMBER, 1040)
    mode_note = {"white": "White light reveals reflected pigment. No induced host emission is added.",
                 "blue": "Blue source excites illustrative visible fluorescence; no calibrated spectral filter.",
                 "uv": "UV itself is invisible. The coloured response is simulated visible fluorescence."}[mode]
    _text_fit(draw, (520, 766), mode_note, FONTS["small"], MUTED, 1040)
    draw.text((520, 808), "COLOUR ≠ GENOTYPE     ·     BRIGHTNESS ≠ HEALTH", font=FONTS["body"], fill=INK)
    draw.text((520, 844), "Fixed-pose inspection cases; biological labels stay unchanged in every lighting mode.", font=FONTS["tiny"], fill=MUTED)
    fraction = max(0., min(1., elapsed / max(.001, duration)))
    draw.rectangle((24, 882, 1576, 885), fill=(25, 50, 57))
    draw.rectangle((24, 882, 24 + 1552 * fraction, 885), fill=TEAL)
    return canvas
