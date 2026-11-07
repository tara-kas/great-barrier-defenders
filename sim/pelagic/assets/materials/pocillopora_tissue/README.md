# Offline Pocillopora tissue material maps

These maps reuse the UV atlas of the Smithsonian's **USNM 46926** dried
*Pocillopora damicornis* specimen. The original 3D media are CC0/public domain:
[Smithsonian record](https://3d.si.edu/es/object/3d/pocillopora-damicornis%3Aae26ad01-e7be-4664-8a3a-b8bffd42a186).
Original source files and their provenance are in `assets/pocillopora/`.
The derived maps and conversion script are released under CC0-1.0.

`generate.py` partially normalizes broad museum lighting while retaining
small calice contrast, then adds muted scenario pigments. It also extracts
the original GLB's separate occlusion atlas to
`assets/pocillopora/pocillopora_occlusion.png`. Its local-normalized cup contrast
is incorporated into the diffuse maps; broad AO shading is removed so the
whole colony does not become unnecessarily dark. Living bleached
maps have warm ivory tissue, restrained pink-brown calice rims and residual
pigment islands. They do not use green algae staining. Dead maps instead use
dark brown/olive biofilm and a rougher surface. The texture pattern is an
artistic health-state cue, not a measurement of live tissue, bleaching
severity, fluorescence, genetic identity or restoration response.

The seven reflected-colour phenotypes are tan, violet, blue, yellow, red,
pink and green. Known R/G contact genets use the default **tan** diffuse map;
their fluorescence response is a separate scene property. Colours do not
supply genetic identity.

Use `reefsim.reef_tissue.material_files(health, phenotype=None)`. Diffuse maps
are **sRGB**; roughness and the unchanged source OpenGL normal map are **raw
linear data**. Diffuse texture scale should be `(1,1,1,1)`, without another
solid pigment multiplication. Low specular reflectance and no clearcoat are
appropriate for the illustrative renderer. Roughness maps vary between
approximately 0.73 and 0.95 across the three health states.

Geometry, topology and UV coordinates are never changed by this material
conversion. All runtime files are bundled. `manifest.json` records source
hashes, map hashes and the conversion's scientific limits.

Regenerate with NumPy and Pillow available:

```bash
python3 assets/materials/pocillopora_tissue/generate.py
python3 -m unittest discover -s tests -p test_reef_tissue.py -v
```
