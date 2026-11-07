"""Offline detail reel layouts using supplied Isaac camera images only."""
from PIL import Image, ImageDraw

from .compositor import FONTS, _place_image, _text_fit

WIDTH, HEIGHT = 1600, 900
BG, INK, MUTED = (5,22,27), (225,238,229), (136,171,170)
TEAL, AMBER = (112,212,195), (232,180,99)
LEFT = (24,132,788,562)
RIGHT = (812,132,1576,562)
MAIN = (24,132,1160,771)
CONTEXT = (1184,132,1576,353)
REFERENCE = (1184,423,1576,644)
POLYP = (24,608,488,869)


def _base(title, elapsed, duration):
    frame=Image.new("RGB",(WIDTH,HEIGHT),BG)
    draw=ImageDraw.Draw(frame)
    draw.text((24,23),"PELAGIC",font=FONTS["brand"],fill=INK)
    draw.text((218,27),title,font=FONTS["body"],fill=TEAL)
    draw.text((218,55),"ACTUAL ISAAC CAMERA VIEWS  ·  OFFLINE DETAIL RECORDING",font=FONTS["tiny"],fill=MUTED)
    draw.text((1348,27),f"{elapsed:05.1f} / {duration:04.1f}s",font=FONTS["body"],fill=INK)
    draw.line((24,88,1576,88),fill=(36,66,68))
    fraction=max(0.,min(1.,elapsed/max(.01,duration)))
    draw.rectangle((24,883,1576,887),fill=(28,49,53))
    draw.rectangle((24,883,24+1552*fraction,887),fill=TEAL)
    return frame


def compose_current(reference, active, polyps, metadata, *, elapsed, duration):
    frame=_base("CURRENT RESPONSE / FIXED CAMERA",elapsed,duration)
    _place_image(frame,reference,LEFT)
    _place_image(frame,active,RIGHT)
    _place_image(frame,polyps,POLYP)
    draw=ImageDraw.Draw(frame)
    for box in (LEFT,RIGHT,POLYP):draw.rectangle(box,outline=(63,104,103),width=1)
    draw.text((24,106),"ZERO-CURRENT REFERENCE / SAME CAMERA",font=FONTS["small"],fill=INK)
    draw.text((812,106),"CURRENT + SURGE / MOVING SOFT TISSUE",font=FONTS["small"],fill=TEAL)
    draw.text((24,581),"LIVING POLYPS / ROBOT MACRO CAMERA",font=FONTS["tiny"],fill=MUTED)
    draw.text((520,595),"Visible flow response",font=FONTS["title"],fill=INK)
    flow=metadata.get("flow_velocity",(0.,0.,0.))
    draw.text((520,637),f"Flow: {flow[0]:+.2f}, {flow[1]:+.2f}, {flow[2]:+.2f} m/s",font=FONTS["body"],fill=TEAL)
    draw.text((520,672),f"Fan-tip deflection: {100*metadata.get('max_tip_displacement_m',0.):.1f} cm",font=FONTS["body"],fill=INK)
    draw.text((520,705),f"Polyp-tip deflection: {1000*metadata.get('max_polyp_displacement_m',0.):.1f} mm",font=FONTS["body"],fill=INK)
    draw.text((520,749),"Soft fans and polyps bend; mineral skeletons remain rigid.",font=FONTS["body"],fill=AMBER)
    draw.text((520,784),"Anchored roots · bounded damped response · deterministic replay",font=FONTS["small"],fill=MUTED)
    draw.text((520,819),"Reduced-order physical proxy; not calibrated fluid–structure simulation.",font=FONTS["small"],fill=MUTED)
    return frame


def compose_tissue(main, overview, white_reference, case, metadata, *, elapsed, duration):
    titles={"healthy":"HEALTHY LIVING TISSUE", "bleached_alive":"PARTLY BLEACHED / STILL ALIVE", "dead":"DEAD SKELETON / EXCLUDED"}
    mode=metadata["mode"]
    light={"white":"WHITE INSPECTION", "blue":"BLUE EXCITATION", "uv":"UV + VISIBLE VIOLET AIMING LIGHT"}[mode]
    frame=_base(titles[case["health"]],elapsed,duration)
    _place_image(frame,main,MAIN)
    _place_image(frame,overview,CONTEXT)
    if white_reference is not None:_place_image(frame,white_reference,REFERENCE)
    draw=ImageDraw.Draw(frame)
    for box in (MAIN,CONTEXT,REFERENCE):draw.rectangle(box,outline=(63,104,103),width=1)
    draw.text((24,106),"ROBOT MACRO CAMERA / " + light,font=FONTS["small"],fill=TEAL)
    draw.text((1184,106),"ROBOT + LIGHT CONE",font=FONTS["small"],fill=INK)
    draw.text((1184,397),"WHITE-LIGHT REFERENCE",font=FONTS["small"],fill=INK)
    draw.text((1184,676),case["coral_id"],font=FONTS["body"],fill=INK)
    if mode=="uv":
        lines=("UV itself is invisible.","The violet cone is a", "visible aiming-light proxy.")
    elif mode=="blue":
        lines=("Visible blue beam", "and illustrative host", "fluorescence response.")
    else:
        lines=("Fine calice texture", "and patchy tissue pigment", "under white illumination.")
    for i,line in enumerate(lines):draw.text((1184,714+i*25),line,font=FONTS["small"],fill=AMBER if mode=="uv" else MUTED)
    if case["health"]=="bleached_alive":
        caption="Pale living tissue retains pigment islands and polyps. Brightness is not recovery."
    elif case["health"]=="dead":
        caption="Dead coral is excluded from treatment; this control adds no host fluorescence."
    else:
        caption="Muted living pigment and calice detail; reflected colour is separate from fluorescence."
    _text_fit(draw,(24,803),caption,FONTS["body"],INK,1128)
    draw.text((24,841),"Known scenario health labels · optical response proxy · no biological recovery simulated",font=FONTS["small"],fill=MUTED)
    return frame
