"""Offline Smithsonian-UV tissue materials; no image libraries at runtime.

Colours indicate known scenario states, not diagnostic measurements. Texture
conversion and provenance live in assets/materials/pocillopora_tissue/.
"""
from pathlib import Path


ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets"
MATERIAL_ROOT = ASSET_ROOT / "materials/pocillopora_tissue"
PHENOTYPES = ("tan", "violet", "blue", "yellow", "red", "pink", "green")
_PALETTES = ((.54,.40,.28), (.44,.33,.44), (.29,.41,.43),
             (.58,.47,.28), (.55,.33,.27), (.60,.40,.40), (.37,.44,.30))


def material_files(health, phenotype=None):
    """Return absolute diffuse/roughness/normal map paths and interpretation.

    Bind diffuse as sRGB with unit scale; roughness and the original OpenGL
    normal map are raw linear data. Do not multiply by a second solid pigment
    tint, which would remove the intended pale tissue and residual islands.
    The default tan phenotype is used for known R/G contact genets: emission
    identity is separate from reflected appearance. Geometry is untouched.
    """
    if health not in ("healthy", "bleached_alive", "dead"):
        raise ValueError("health must be healthy, bleached_alive or dead")
    phenotype = "tan" if phenotype is None else phenotype
    if phenotype not in PHENOTYPES:
        raise ValueError(f"Unsupported phenotype {phenotype!r}")
    prefix = "dead" if health == "dead" else f"{health}_{phenotype}"
    paths = {"diffuse":MATERIAL_ROOT/f"{prefix}_diffuse.jpg",
             "roughness":MATERIAL_ROOT/f"{health}_roughness.png",
             "normal":ASSET_ROOT/"pocillopora/pocillopora_normal.png"}
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"Required bundled tissue map missing: {path}")
    return {key:str(value) for key,value in paths.items()} | {
        "health":health,"phenotype":phenotype,
        "interpretation":"artistic tissue pigmentation; not measured living tissue or fluorescence"}


def tissue_color(health, seed=0):
    """Muted fallback colour for procedural scenery without scan UVs."""
    if health not in ("healthy", "bleached_alive", "dead"):
        raise ValueError("Unsupported coral health")
    if isinstance(seed,bool) or not isinstance(seed,int):
        raise ValueError("seed must be an integer")
    base=_PALETTES[seed % len(_PALETTES)]
    if health == "dead":
        return (.23,.27,.19)
    if health == "bleached_alive":
        # Retained pigment varies by colony, without tinting bleached tissue
        # the saturated colour of a healthy colony.
        amount=.10+.035*(seed%4)
        ivory=(.80,.75,.66)
        return tuple(ivory[i]*(1-amount)+base[i]*amount for i in range(3))
    return base
