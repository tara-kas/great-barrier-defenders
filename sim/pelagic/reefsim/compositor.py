"""Offline documentary layout for synchronized Isaac camera recordings.

Only real render products are supplied here. This module never fabricates a
camera view or mission state, and contains no network/client/server code.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1600, 900
MAIN_BOX = (24, 116, 1184, 769)
SCOUT_BOX = (1204, 154, 1576, 377)
WORKER_BOX = (1204, 448, 1576, 671)

INK = (225, 238, 229)
MUTED = (136, 171, 170)
BG = (5, 22, 27)
TEAL = (112, 212, 195)
AMBER = (232, 180, 99)


def _font(size, bold=False):
    names = (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if bold else
             ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf"])
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default()


FONTS = {"brand": _font(32, True), "title": _font(26, True),
         "body": _font(18), "small": _font(14), "tiny": _font(12),
         "number": _font(28, True)}


def phase_name(state):
    worker = next((robot for robot in state.get("robots", [])
                   if robot.get("role") == "restoration"), {})
    phase = worker.get("state", "WAIT_FOR_MAP")
    if state.get("detection_required") and phase in {"WAIT_FOR_MAP", "PLAN", "NAVIGATE_TO_DONOR"}:
        return {
            "WAIT_FOR_MAP": ("01 / SURVEY", "Map provisional candidates; UV detection precedes treatment"),
            "PLAN": ("02 / CANDIDATES", "Select a provisional pair; UV approval is required before harvest"),
            "NAVIGATE_TO_DONOR": ("02 / DETECT DONOR", "Approach the donor for UV approval before harvest"),
        }[phase]
    contact = any(c.get("contact_fixture") for c in state.get("corals", []))
    if contact and phase in {"PLAN", "NAVIGATE_TO_SITE", "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER", "VERIFY_ATTACHMENT", "COMPLETE"}:
        return {
            "PLAN": ("02 / MATCH", "Select a healthy donor from the same known clonal lineage"),
            "NAVIGATE_TO_SITE": ("04 / CARRY", "Carry the matched fragment to the living bleached recipient"),
            "LOWER_FRAGMENT": ("05 / CONTACT", "Align living tissue against the recipient branch"),
            "SECURE_FRAGMENT": ("05 / SECURE", "Support the cut base while maintaining tissue contact"),
            "OPEN_GRIPPER": ("06 / RELEASE", "Open jaws; the support holds the contacting tissue pair"),
            "VERIFY_ATTACHMENT": ("07 / MECHANICAL CHECK", "White-light check of secured contact; recovery remains pending"),
            "COMPLETE": ("CONTACTS SECURED", "Four same-genet contacts ready for follow-up over days/weeks"),
        }[phase]
    return {
        "WAIT_FOR_MAP": ("01 / SURVEY", "Finding healthy donors and bleached living colonies"),
        "PLAN": ("02 / PLAN", "Matching a healthy donor to a bleached living colony"),
        "NAVIGATE_TO_SCAN_RECIPIENT": ("02 / DETECT RECIPIENT", "Approaching a provisional candidate for UV detection"),
        "SCAN_RECIPIENT": ("02 / UV DETECTION", "Check the living bleached recipient before approving treatment"),
        "SCAN_DONOR": ("02 / UV DETECTION", "Check the healthy donor before approving fragment harvest"),
        "NAVIGATE_TO_PICKUP": ("03 / APPROVED DONOR", "UV checks accepted; approach for white-light pickup"),
        "NAVIGATE_TO_DONOR": ("02 / DONOR REEF", "Approaching a living donor colony"),
        "APPROACH_FRAGMENT": ("03 / APPROACH", "Open jaws align with the donor branch"),
        "CLOSE_GRIPPER": ("03 / GRASP", "Soft jaws close around the coral stem"),
        "DETACH_FRAGMENT": ("03 / DETACH", "Holding the branch while separating the cutting"),
        "RETRACT_FRAGMENT": ("03 / LIFT", "Withdrawing the same grasped coral fragment"),
        "NAVIGATE_TO_SITE": ("04 / CARRY", "Carrying a healthy cutting to the bleached living reef"),
        "LOWER_FRAGMENT": ("05 / LOWER", "Lowering the held fragment onto a stable attachment patch"),
        "SECURE_FRAGMENT": ("05 / SECURE", "Holding the fragment at the prepared substrate"),
        "OPEN_GRIPPER": ("06 / RELEASE", "Jaws open while the fragment remains in place"),
        "RETRACT_GRIPPER": ("06 / WITHDRAW", "Empty gripper retreats from the placed fragment"),
        "VERIFY_ATTACHMENT": ("07 / MECHANICAL CHECK", "White-light check that the same fragment remains attached"),
        "COMPLETE": ("MISSION COMPLETE", "Four bleached living colonies assisted; dead coral excluded"),
        "NO_STOCK": ("HOLD", "No approved donor fragments remain"),
        "DETECTION_REJECTED": ("DETECTION HOLD", "UV check rejected the pair; no harvesting or treatment authorized"),
    }.get(phase, (phase.replace("_", " "), "Autonomous reef restoration mission"))


def inspection_caption(inspection, worker_state):
    """Describe the recorded light and purpose without implying UV is visible."""
    mode = inspection.get("mode", "white")
    if mode == "uv":
        recipient = worker_state in {"NAVIGATE_TO_SCAN_RECIPIENT", "SCAN_RECIPIENT"}
        donor = worker_state in {"NAVIGATE_TO_DONOR", "SCAN_DONOR"}
        target = "RECIPIENT" if recipient else "DONOR" if donor else "RESPONSE PROXY"
        subtitle = ("VISIBLE VIOLET AIM LIGHT / UV INVISIBLE"
                    if inspection.get("visible_uv_pilot") else "UV IS INVISIBLE / SYNTHETIC RESPONSE")
        return f"UV DETECTION / {target}", subtitle
    if mode == "blue":
        return "BLUE EXCITATION / 450 nm", "ILLUSTRATIVE FLUORESCENCE RESPONSE"
    if worker_state == "VERIFY_ATTACHMENT":
        return "WHITE / MECHANICAL CHECK", "SECURED CONTACT / RECOVERY PENDING"
    manipulation = {"NAVIGATE_TO_PICKUP", "APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT", "RETRACT_FRAGMENT",
                    "NAVIGATE_TO_SITE", "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER",
                    "RETRACT_GRIPPER"}
    return ("WHITE / MANIPULATION" if worker_state in manipulation else "WHITE / REEF SURVEY",
            "KNOWN LINEAGE IS SCENARIO METADATA")


def _place_image(canvas, image, box):
    """Fit without cropping a camera's field of view."""
    if not isinstance(image, Image.Image):
        image = Image.fromarray(image)
    image = image.convert("RGB")
    width, height = box[2] - box[0], box[3] - box[1]
    scale = min(width / image.width, height / image.height)
    resized = image.resize((max(1, round(image.width * scale)),
                            max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    x = box[0] + (width - resized.width) // 2
    y = box[1] + (height - resized.height) // 2
    canvas.paste(resized, (x, y))


def _text_fit(draw, xy, text, font, fill, max_width):
    if draw.textlength(text, font=font) > max_width:
        while text and draw.textlength(text + "…", font=font) > max_width:
            text = text[:-1]
        text += "…"
    draw.text(xy, text, font=font, fill=fill)


def _robot_caption(draw, box, title, subtitle, accent):
    x, y = box[0], box[1] - 38
    draw.rectangle((x, y, box[2], box[1]), fill=(10, 37, 42))
    draw.rectangle((x, y, x + 3, box[1]), fill=accent)
    draw.text((x + 13, y + 6), title, font=FONTS["small"], fill=INK)
    draw.text((x + 13, box[3] + 10), subtitle, font=FONTS["tiny"], fill=MUTED)


def compose_frame(main, scout, worker, state, playback_speed=1.0, *, keyframe=False):
    """Return a 1600×900 RGB frame with two synchronized actual camera PiPs."""
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(canvas)
    # Deliberately restrained: recorded views remain the main evidence.
    draw.line((24, 88, 1576, 88), fill=(36, 66, 68), width=1)
    draw.line((24, 790, 1576, 790), fill=(36, 66, 68), width=1)
    draw.text((24, 23), "PELAGIC", font=FONTS["brand"], fill=INK)
    contact = any(c.get("contact_fixture") for c in state.get("corals", []))
    draw.text((218, 30), "SAME-GENET CONTACT  /  P. DAMICORNIS PROXY" if contact else "HEALTHY → BLEACHED / ALIVE  /  OFFLINE REPLAY", font=FONTS["small"], fill=MUTED)
    for x, label, color in ((218, "COLOURED / DONOR", "#d79c75"),
                            (445, "BLEACHED / STILL ALIVE", "#eee2c8"),
                            (715, "DEAD / EXCLUDED", "#828778")):
        draw.ellipse((x, 58, x + 7, 65), fill=color)
        draw.text((x + 14, 53), label, font=FONTS["tiny"], fill=color)
    seconds = max(0., float(state.get("time", 0.)))
    # Round first so 59.999999 becomes 01:00.00, never 00:60.00.
    hundredths = round(seconds * 100)
    minutes, remainder = divmod(hundredths, 6000)
    stamp = f"T+ {minutes:02d}:{remainder / 100:05.2f}"
    draw.text((1320, 21), stamp, font=FONTS["body"], fill=INK)
    draw.text((1320, 51), "ISAAC SIM 6.0  ·  DGX SPARK", font=FONTS["tiny"], fill=MUTED)

    _place_image(canvas, main, MAIN_BOX)
    _place_image(canvas, scout, SCOUT_BOX)
    _place_image(canvas, worker, WORKER_BOX)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(MAIN_BOX, outline=(39, 74, 74), width=1)
    draw.rectangle(SCOUT_BOX, outline=(46, 96, 91), width=1)
    draw.rectangle(WORKER_BOX, outline=(103, 88, 60), width=1)
    draw.text((24, 96), "ACTION CAMERA", font=FONTS["tiny"], fill=MUTED)
    robots = state.get("robots", [{}, {}])
    scout_state = next((r.get("state", "SURVEY") for r in robots if r.get("role") == "survey"), "SURVEY")
    worker_state = next((r.get("state", "WAIT_FOR_MAP") for r in robots if r.get("role") == "restoration"), "WAIT_FOR_MAP")
    _robot_caption(draw, SCOUT_BOX, "SCOUT-01  /  DOWNWARD CAMERA",
                   scout_state.replace("_", " "), TEAL)
    _robot_caption(draw, WORKER_BOX, "RESTORE-02  /  TOOL CAMERA",
                   worker_state.replace("_", " "), AMBER)

    water = state.get("water", {})
    current = water.get("current", [0, 0, 0])
    flow = math.sqrt(sum(float(value) ** 2 for value in current))
    inspection = state.get("inspection", {})
    if inspection:
        label, explanation = inspection_caption(inspection, worker_state)
        draw.text((1204, 714), label, font=FONTS["small"], fill=TEAL)
        _text_fit(draw, (1204, 740), explanation, FONTS["tiny"], MUTED, 370)
    else:
        draw.text((1204, 714), f"VISIBILITY  {water.get('visibility', 0):.1f} m", font=FONTS["small"], fill=MUTED)
        draw.text((1204, 740), f"CURRENT      {flow:.2f} m/s", font=FONTS["small"], fill=MUTED)
    transfer = next((r for r in robots if r.get("role") == "restoration"), {})
    fragment_id = transfer.get("fragment_id")
    if fragment_id:
        donor_id = transfer.get("donor_id", "")
        _text_fit(draw, (1204, 765), f"{fragment_id}  ·  {donor_id}", FONTS["tiny"], AMBER, 370)

    phase, description = phase_name(state)
    draw.text((24, 808), phase, font=FONTS["small"], fill=TEAL)
    _text_fit(draw, (24, 836), description, FONTS["body"], INK, 720)
    metrics = state.get("metrics", {})
    total = metrics.get("total_corals", len(state.get("corals", [])))
    blocks = [(790, f"{metrics.get('observed', 0):02d} / {total:02d}", "COLONIES MAPPED"),
              (1045, f"{metrics.get('verified', 0):02d}", "ASSISTED COLONIES"),
              (1305, f"{metrics.get('donor_fragments_available', metrics.get('inventory', 0)):02d}", "DONOR FRAGMENTS AVAILABLE")]
    for x, number, label in blocks:
        draw.line((x - 22, 813, x - 22, 867), fill=(36, 66, 68), width=1)
        draw.text((x, 806), number, font=FONTS["number"], fill=INK)
        draw.text((x, 849), label, font=FONTS["tiny"], fill=MUTED)
    review = "MILESTONE KEYFRAME REVIEW" if keyframe else "VARIABLE-SPEED REPLAY · MANIPULATION EMPHASIZED"
    draw.text((24, 877), f"RECORDED ROBOT CAMERAS  ·  {review}  ·  ATTACHMENT ≠ BIOLOGICAL RECOVERY",
              font=FONTS["tiny"], fill=(96, 133, 134))
    return canvas
