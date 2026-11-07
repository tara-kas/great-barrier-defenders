"""Derive offline coral tissue PBR maps from the CC0 Smithsonian scan atlas.

This is a reproducible artistic material conversion, not measured live tissue.
The scan's UV layout and normal map are retained. Pillow and NumPy are needed
only here; the simulator reads the prebuilt maps with no conversion dependency.
"""
from pathlib import Path
import hashlib
import io
import json
import struct

import numpy as np
from PIL import Image, ImageFilter, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "assets/pocillopora/pocillopora_basecolor.jpg"
NORMAL = ROOT / "assets/pocillopora/pocillopora_normal.png"
OCCLUSION = ROOT / "assets/pocillopora/pocillopora_occlusion.png"

PALETTES = {
    "tan": (.60, .44, .29),
    "violet": (.46, .35, .47),
    "blue": (.31, .43, .48),
    "yellow": (.65, .53, .29),
    "red": (.60, .34, .27),
    "pink": (.66, .43, .43),
    "green": (.39, .48, .32),
}


def blur(values, radius):
    picture = Image.fromarray(np.uint8(np.clip(values, 0, 1) * 255), "L")
    return np.asarray(picture.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255


def coherent_noise(size, seed):
    rng = np.random.default_rng(seed)
    total = np.zeros(size[::-1], dtype=np.float32)
    weights = ((7, .45), (19, .30), (47, .18), (113, .07))
    for resolution, weight in weights:
        small = Image.fromarray(np.uint8(rng.random((resolution, resolution)) * 255), "L")
        total += weight * np.asarray(small.resize(size, Image.Resampling.BICUBIC), dtype=np.float32) / 255
    return total


def smoothstep(low, high, values):
    x = np.clip((values - low) / (high - low), 0, 1)
    return x*x*(3-2*x)


def save_rgb(name, array):
    Image.fromarray(np.uint8(np.clip(array, 0, 1) * 255), "RGB").save(OUT/name, quality=96, subsampling=0)


def extract_occlusion():
    """Keep the source GLB's calice AO atlas, formerly omitted by conversion."""
    source=(ROOT/"assets/pocillopora/usnm_46926-source.glb").read_bytes()
    assert source[:4]==b"glTF"
    offset=12;document=None;binary=None
    while offset<len(source):
        length,kind=struct.unpack_from("<II",source,offset)
        payload=source[offset+8:offset+8+length]
        if kind==0x4E4F534A:document=json.loads(payload)
        elif kind==0x004E4942:binary=payload
        offset+=8+length
    texture=document["materials"][0]["occlusionTexture"]["index"]
    image=document["images"][document["textures"][texture]["source"]]
    view=document["bufferViews"][image["bufferView"]]
    first=view.get("byteOffset",0)
    picture=Image.open(io.BytesIO(binary[first:first+view["byteLength"]])).convert("RGB")
    # glTF occlusion uses the red channel; no atlas reorientation is performed.
    picture.getchannel("R").save(OCCLUSION)
    return np.asarray(picture.getchannel("R"),dtype=np.float32)/255


def main():
    original = Image.open(SOURCE).convert("RGB")
    pixels = np.asarray(original, dtype=np.float32) / 255
    luminance = pixels @ np.array((.2126, .7152, .0722), dtype=np.float32)
    local = blur(luminance, 6)
    broader = blur(luminance, 20)
    # Divide out much of the broad museum illumination while keeping the
    # small recessed calices. Deep atlas gutters stay dark to avoid UV halos.
    relative = np.clip(luminance / np.maximum(local, .055), .35, 1.35)
    detail = np.clip(.52 + .48*relative + .12*(local-broader), .36, 1.12)
    gutter = .12 + .88*smoothstep(.025, .14, local)
    detail *= gutter
    occlusion=extract_occlusion()
    # The source viewer uses a separate AO atlas whose rounded cup contrast
    # is much clearer than the base-colour photograph. Retain this local
    # calice signal, not its broad museum ambient shading. Mostly neutral
    # values preserve the living pigment and avoid making entire limbs dark.
    ao_relative=np.clip(occlusion/np.maximum(blur(occlusion,3),.06),.25,1.35)
    calice_contrast=np.clip(1.+.8*(ao_relative-1.),.55,1.06)
    detail *= calice_contrast
    coarse = coherent_noise(original.size, 2607)
    fine = coherent_noise(original.size, 2608)
    # Approximately 20% residual pigment islands: patchy living bleaching,
    # with another low-amplitude warm tissue variation across the ivory areas.
    residual = smoothstep(.47, .66, coarse)
    warmth = smoothstep(.42, .67, fine)
    crevices = np.clip(1-relative, 0, 1)
    for phenotype, pigment in PALETTES.items():
        pigment = np.asarray(pigment, dtype=np.float32)
        earthy = np.asarray((.57,.43,.30), dtype=np.float32)
        local_tint = pigment[None,None,:]*(.90+.15*fine[:,:,None])
        local_tint = local_tint*(1-.16*warmth[:,:,None]) + earthy*.16*warmth[:,:,None]
        healthy = local_tint * detail[:,:,None]
        save_rgb(f"healthy_{phenotype}_diffuse.jpg", healthy)

        ivory = np.asarray((.87,.82,.72), dtype=np.float32)
        living_blush = np.asarray((.82,.70,.66), dtype=np.float32)
        bleached = ivory*(1-.28*warmth[:,:,None]) + living_blush*.28*warmth[:,:,None]
        # Residual islands are living brown/pink tissue, not green biofilm.
        remnant = pigment*.64 + np.asarray((.60,.44,.36))*.36
        amount = .72*residual[:,:,None]
        bleached = (bleached*(1-amount) + remnant*amount) * detail[:,:,None]
        # Slight pink-brown calice rims retain tissue cues on pale branches.
        rim = np.minimum(.10, crevices*.18)[:,:,None]
        bleached = bleached*(1-rim) + np.asarray((.55,.38,.33))*rim*gutter[:,:,None]
        save_rgb(f"bleached_alive_{phenotype}_diffuse.jpg", bleached)

    algae = smoothstep(.35,.68,coarse)
    dead_base = (np.asarray((.35,.29,.20))*(1-algae[:,:,None]) +
                 np.asarray((.20,.29,.18))*algae[:,:,None])
    worn_detail = np.clip((detail-.60)*1.45+.60,.12,1.16)
    dead = dead_base * worn_detail[:,:,None] * (.88+.22*fine[:,:,None])
    save_rgb("dead_diffuse.jpg", dead)
    for health, base, spread in (("healthy",.76,.13), ("bleached_alive",.79,.11), ("dead",.89,.10)):
        rough = np.clip(base + spread*(.55*fine+.45*crevices-.25), .68, .98)
        Image.fromarray(np.uint8(rough*255), "L").save(OUT/f"{health}_roughness.png")
    files = {}
    for path in sorted(OUT.glob("*_diffuse.jpg")) + sorted(OUT.glob("*_roughness.png")):
        payload=path.read_bytes()
        files[path.name] = {"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()}
    manifest = {
        "asset":"pocillopora_tissue_materials", "license":"CC0-1.0",
        "source_specimen":"Smithsonian USNM 46926, dried Pocillopora damicornis",
        "source_record":"https://3d.si.edu/es/object/3d/pocillopora-damicornis%3Aae26ad01-e7be-4664-8a3a-b8bffd42a186",
        "source_diffuse_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "source_normal_sha256":hashlib.sha256(NORMAL.read_bytes()).hexdigest(),
        "source_occlusion_sha256":hashlib.sha256(OCCLUSION.read_bytes()).hexdigest(),
        "geometry_changed":False, "uv_layout_changed":False,
        "colour_space":{"diffuse":"sRGB","roughness":"raw linear","normal":"raw linear OpenGL"},
        "interpretation":"Artistic healthy/partially bleached/dead tissue proxy derived from a dried specimen atlas; not calibrated tissue or a fluorescence map",
        "method":"Partial local illumination normalization; local-normalized original GLB occlusion atlas restores calice cup contrast without broad AO shading; deterministic muted tissue pigmentation and residual pigment islands; high varying roughness; original normal atlas reused",
        "phenotypes":list(PALETTES), "files":files,
    }
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    preview=Image.new("RGB",(1536,542),(12,24,28));draw=ImageDraw.Draw(preview)
    for i,health in enumerate(("healthy","bleached_alive","dead")):
        file=f"{health}_tan_diffuse.jpg" if health!="dead" else "dead_diffuse.jpg"
        preview.paste(Image.open(OUT/file).resize((512,512)),(i*512,30))
        draw.text((i*512+12,10),health,fill="white")
    preview.save(OUT/"material-review.jpg",quality=92)
    print(json.dumps({"files":len(files),"size":original.size,"residual_mean":float(residual.mean()),
                      "calice_contrast_mean":float(calice_contrast.mean())}))


if __name__ == "__main__":
    main()
