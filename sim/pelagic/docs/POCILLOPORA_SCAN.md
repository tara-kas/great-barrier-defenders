# Pocillopora specimen geometry

The bundled model is a scan of **Pocillopora damicornis, USNM 46926**, a dried
specimen from a patch reef at Fernandina Island in the Galápagos. The Smithsonian
record identifies its 3D media as public domain and its metadata as CC0. Credit:
Smithsonian Institution, National Museum of Natural History; coral digitization
project with The Hydrous. This project is not endorsed by the Smithsonian.
[Official record](https://3d.si.edu/es/object/3d/pocillopora-damicornis%3Aae26ad01-e7be-4664-8a3a-b8bffd42a186),
[Open Access terms](https://www.si.edu/openaccess/faq),
[CC0 terms](https://creativecommons.org/publicdomain/zero/1.0/).

This specimen has a compact colony shape with irregular thick branches and
visible corallite texture. The official source preview and the derived mesh
were inspected: there is no rectangular museum plinth, and no basal trimming
was needed. The entire connected colony is retained. The Smithsonian describes
multiple growth forms of this species; this asset represents one specimen,
not every Pocillopora colony or a surveyed Great Barrier Reef site.
[Smithsonian growth-form context](https://3d.si.edu/corals/shape-structure).

## Files and conversion

All files are in `assets/pocillopora/`; rendering requires no network request.

| File | Purpose |
| --- | --- |
| `usnm_46926-source.glb` | Unmodified official 150,000-triangle / 1024-pixel model |
| `usnm_46926-voyager.json` | Official model manifest and coordinate metadata |
| `source-preview.jpg` | Official source-model preview used to inspect specimen shape |
| `pocillopora_damicornis_20k.json.gz` | Derived connected mesh: 9,952 vertices, 19,908 triangles, approximately 481 KB |
| `pocillopora_damicornis_hero.json.gz` | Full source mesh: 90,281 vertices, 150,000 triangles, preserving original UV seams and normal detail |
| `pocillopora_basecolor.jpg` | Original diffuse texture re-encoded as JPEG |
| `pocillopora_normal.png` | Extracted original normal map |
| `pocillopora_occlusion.png` | Original glTF occlusion red-channel atlas; calice contrast used in derived tissue maps |
| `convert_source.py` | Optional conversion script; never imported by the simulator |
| `convert_hero.py` | Optional full-resolution extraction without simplification or nearest-vertex UV transfer |
| `manifest.json` | Official URLs, license, dimensions, conversion details, byte sizes and SHA-256 checksums |
| `geometry-review.png` | Local three-state geometry inspection image |

The official source is
[USNM 46926 low-resolution GLB](https://3d-api.si.edu/content/document/3d_package:ae26ad01-e7be-4664-8a3a-b8bffd42a186/USNM_46926-150k-1024-low.glb).
Its SHA-256 is `0ccb9adf413b88a67b128768a6c62fbaa68394edf2f8f8bb8bbcc1e3a3719ed1`.
Files were downloaded on 2026-11-07.

The reduced-background conversion uses Trimesh 5.2.0, DracoPy 2.2.0 and fast-simplification 0.2.0.
Coincident vertices are welded and quadric decimation targets 20,000 faces.
Degenerate faces and tiny disconnected 2–4-triangle simplification artefacts
are discarded, retaining the connected whole colony. Smooth normals are
recomputed. Colour and UV transfer use the nearest original vertex, so UV
seams can have approximation errors. This mesh remains appropriate for
selected background colonies, rather than close-up tissue inspection.

`convert_hero.py` extracts the original 150,000 triangles, original UV seams
and source normals with no decimation or UV reassignment. Only degenerate
source normals require a unit-normal fallback. The current
`render.realistic_tissue` path uses this hero mesh for registered living and
bleached contact colonies, so their mapped calice detail is not reconstructed
from the reduced mesh's nearest-vertex UVs. The runtime still needs only the
bundled gzip/JSON, not Trimesh, DracoPy or an asset-server connection.

Source GLB coordinates are Z-up; its Voyager model transform rotates them for
the Y-up viewer. The derived mesh is centred in XY and grounded at Z=0. Its
unscaled dimensions depend slightly on the retained geometry: the reduced
mesh has radius **0.05999166 m**, height **0.06466389 m** and height/radius
**1.07788127**; the original hero mesh has radius **0.06042744 m**, height
**0.06511742 m** and height/radius **1.07761350**. Both JSON files store
normalized coordinates plus their own source dimensions. Correct
inverse-transpose scaling preserves normal direction through normalization
and runtime sizing.

## Runtime contract

`reefsim.pocillopora_scan.generate_pocillopora_scan(health, radius, height,
seed=0, *, preserve_aspect=True, preserve_colors=False, detail="standard")` returns standard
indexed mesh fields: `points`, `normals`, `colors`, `uvs`, `counts`, `indices`.
The implementation uses only Python's standard library and caches the source.
Returned arrays are independent mutable copies.

The default uniformly scales the specimen to fit the requested radius and
height, retaining its actual shape. `preserve_aspect=False` deliberately fits
radius and height separately; this must be described as an artistic proxy.
Seed varies yaw and healthy pigment, not skeletal topology. `detail="hero"`
selects the preserved source-resolution mesh; `"standard"` selects the
19,908-triangle background version. `source_dimensions(detail)` reports each
mesh's proportions, and `texture_files()` exposes the original detail maps.
Returned vertex colours remain fallback scenario tints retaining scan
luminance; `preserve_colors=True` keeps the dry specimen's sampled colour.

The detailed renderer binds the UV-aligned maps from
`assets/materials/pocillopora_tissue/` directly to the hero mesh. Diffuse maps
partially remove broad museum illumination while retaining calice contrast,
then add muted living pigment or warm partial-bleaching patterns. Local contrast from the original occlusion atlas restores the calice cups without multiplying broad museum shadows into the whole colony. Roughness
maps and low specular reflectance reduce the smooth plastic appearance. The
original normal atlas is retained. These are artistic tissue materials;
they are not a scan of living tissue or a calibrated optical measurement.

The scan supplies skeletal morphology. It does not establish living tissue,
health, fluorescence, genotype or compatibility. It is not a scan of either
laboratory genet from the contact-recovery paper. Manipulated cuttings remain
procedural engineering geometry. Natural-contact planning now selects a
triangle on this unchanged recipient mesh and records its source detail,
index and coordinates; the renderer adds only a small basal securing compound,
not an artificial recipient extension branch. A recoloured museum skeleton
does not itself become biologically alive, and tinting it dark does not create
erosion or breakage. The detailed scene keeps procedural dead controls distinct
and adds deformable polyp patches only to living colonies; the hard scan stays
rigid throughout.

Validation checks cover reduced-mesh connectedness, triangle indices, finite attributes,
unit normals, dimensions, deterministic replay, independent returned arrays,
and bundled-file checksums. The local inspection image is a geometry check,
not an Isaac rendering or a biological accuracy claim.
