# Smithsonian coral scan assets

The offline scene can use an actual Smithsonian 3D scan of **Acropora secale, USNM 268**, from the National Museum of Natural History, Invertebrate Zoology Department. Its collection locality is the East Indies, South Pacific Ocean; collection dates are 1838–1842. The specimen includes a small attached *Tubipora musica* colony. This is an Indo-Pacific museum specimen, not a scan of the Great Barrier Reef or living tissue. [Official specimen and download record](https://3d.si.edu/es/object/3d/acropora-secale%3Acb2e1f4d-8eaa-454b-b61d-cc78b6b64b7b), [Smithsonian coral collection context](https://3d.si.edu/corals/coral-community).

## License and credit

The model is released through Smithsonian Open Access under **CC0 1.0**. Its official record identifies the media as public domain, and the specimen appears in the Smithsonian explorer's CC0 media results. Credit: Smithsonian Institution, National Museum of Natural History; coral digitization project with The Hydrous. Modified for this simulation by decimation, coordinate normalization and scenario recolouring. This project is not endorsed by the Smithsonian. [Official CC0-filtered catalogue](https://3d.si.edu/explore?edan_fq%5B%5D=-place%3A%22Mexico%22&edan_fq%5B%5D=media_usage%3A%22CC0%22&edan_q=corals), [Smithsonian Open Access policy](https://www.si.edu/openaccess/faq), [CC0 terms](https://creativecommons.org/publicdomain/zero/1.0/).

## Bundled files and provenance

| File in `assets/corals/` | Purpose |
| --- | --- |
| `usnm_268-source.glb` | Unmodified official 150,000-face / 1024-pixel source download |
| `usnm_268-voyager.json` | Official Voyager manifest describing the source derivatives and specimen record |
| `acropora_secale_15k.json.gz` | Portable derived geometry: 14,999 triangles, 7,443 vertices, normals, sampled scan colours and UVs; about 350 KB |
| `acropora_secale_basecolor.jpg` | Original scan base-colour image, re-encoded as JPEG |
| `acropora_secale_normal.png` | Extracted original scan normal map |
| `convert_source.py` | Optional one-time conversion script; not imported by the runtime |
| `manifest.json` | Download URLs, source/derived SHA-256 values, license and conversion details |

Source files were obtained from the official Smithsonian delivery service on 2026-11-07; derived files were created locally. No third-party account or runtime network request is used. The original download is [USNM 268 low-resolution GLB](https://3d-api.si.edu/content/document/3d_package:cb2e1f4d-8eaa-454b-b61d-cc78b6b64b7b/usnm_268-150k-1024-low.glb). The source SHA-256 is `141d379617fadff6f2517faa99d8857f0f47e68c828a571d09f006662249a626`.

Conversion used temporary Trimesh 5.2.0, DracoPy 2.2.0 and fast-simplification 0.2.0 tools. The rectangular museum plinth was removed by excluding triangles with a source vertex below Z=0.041 m. Coincident mesh vertices were welded before simplification. Quadric decimation targeted 15,000 faces (14,999 retained), with aggressiveness 7. The original GLB vertex coordinates are Z-up; the Voyager scene rotates them for its Y-up viewer. Derived vertices are centred in XY, based at Z=0 and normalized to horizontal radius 1 and height 1. Smooth normals account for this normalization. Scan colour and UV transfer use nearest source vertices; optional texture use can show small UV errors near source seams. The original scan is preserved separately for future reprocessing.

## Runtime interface

`reefsim.scanned_coral.generate_scanned_coral(health, radius, height, seed=0, *, asset="acropora_secale", preserve_colors=False, preserve_aspect=False)` returns the same indexed mesh dictionary as `organic.generate_coral`: `points`, `normals`, `colors`, `uvs`, `counts`, `indices`. The loader uses only standard-library JSON/gzip/math modules and caches the source data. Every returned mesh has independent mutable lists.

The default fits the requested radius and height separately, preserving surface structure while allowing artistic proportions. `preserve_aspect=True` uniformly scales the specimen to fit both bounds, retaining the original proportions. Seed changes yaw and the healthy pigment choice; it does not change topology. `preserve_colors=True` retains the dried specimen's sampled colour. Otherwise healthy specimens use warm orange, dusky purple, teal or ochre pigments; bleached living specimens use warm ivory; dead specimens use dark algae brown/grey. These are scenario colours, not measured living colours of this specimen. `texture_files()` exposes the optional bundled base-colour and normal maps.

Use scans for background or static hero colonies. Keep procedural donor parent branches and the single persistent manipulation cutting unchanged so the jaw contact and detachment contract remains explicit. A bleached-coloured scan does not claim the museum skeleton is biologically alive. The simulation's semantic state supplies that scenario interpretation.

Mesh integrity checks cover valid triangle indices, matching vertex attributes, finite unit normals, requested dimensions, Z=0 placement and deterministic replay. The original proportions can be retained for comparison with the specimen record. No ecological accuracy or restoration efficacy follows from using scanned geometry.
