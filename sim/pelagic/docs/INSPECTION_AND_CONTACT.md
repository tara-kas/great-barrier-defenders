# Robot inspection and same-genet tissue contact

The current detailed scenario is selected with `configs/natural_reef.json`.
It uses a natural surface of the scanned recipient rather than the authored
extension branch visible in the earlier contact recording. The earlier
`configs/cinematic.json` recording preserves the separate limestone outplant
demonstration. It does not demonstrate the contact treatment.

## Research basis and boundary

Collins et al., *Science Advances* (2026), studied direct contact between
healthy and bleached living **Pocillopora damicornis** fragments. Compatible
same-genet pairs formed tissue connections and transferred symbionts; simply
placing fragments nearby did not reproduce that response. The laboratory
fragments were secured on a common support, and recovery was monitored over
days and weeks. Red/green fluorescence distinguished two already-known
experimental lineages. [Primary study, photographs and supplementary movie](https://pmc.ncbi.nlm.nih.gov/articles/PMC13665998/).

The robot scenario adapts the contact principle to an enlarged underwater
engineering demonstration. Its 14 cm cutting, wrist tool, basal support and
in-situ recipient branch are **not a validated deployment protocol**. It
verifies mechanical placement now; it does not simulate tissue fusion,
symbiont transfer or instant biological recovery. Recipient health remains
`bleached_alive`. No roots or new coral appear when the gripper opens.

## Pairing and attachment

Only observed, healthy donors with a known matching `genet_id` and species
proxy are eligible. The R/G registry is explicit scenario ground truth;
neither RGB colour nor a bright fluorescent signal supplies genetic identity.
Unknown or incompatible pairings hold without harvesting. Dead coral is
excluded regardless of its visual colour or region policy.

The healthy cutting keeps one mesh and identity from collection to placement.
`reefsim/natural_contact.py` selects accessible outer-branch triangles from
the same scanned mesh used by the renderer. Candidate checks keep the upright
cutting clear of the colony bulk and identify a nearby basal support point.
The core records the source triangle, normal, mesh detail and contact band.
The recipient mesh is not extended, deformed or replaced to create contact.
Only a small basal securing compound is separately authored, below the
living-tissue interface. The robot holds contact, opens the jaws, withdraws
and inspects the pair. Other coral/rock workspaces retain 0.55 m clearance;
only the intended recipient contact patch receives an owner exception.

The recording audit queries actual transformed cutting vertices against
the recipient's triangle surface in the 10–35 mm band above the cutting base.
It requires contact within 1.5 mm and rejects more than 3 mm penetration,
checks the unchanged source triangle and rejects a fabricated recipient
branch prim. This is geometric alignment evidence, not a contact-force,
tissue deformation, fusion or adhesive model.

## Lighting cases

`scripts/render_inspection.py` records 15 controlled cases: five illustrative
appearance groups × healthy, bleached living and dead. Each compares the
same robot-camera view under white, blue (450 nm) and UV (365 nm) excitation.
The UV source itself is invisible. `natural_reef.json` also enables a
co-aligned **visible violet aiming light**: its footprint and volumetric
water-scattering cone make the source direction apparent. This visible pilot
is separate from the illustrative RGB fluorescence response and is explicitly
labelled in the detail reel; it does not claim that UV radiation is visible.

The visible pigment palette and emitted palette are separate. Purple pigment
has a nonfluorescent control; other cases demonstrate cyan, green/yellow and
red/orange responses. Bleached living tissue can retain host fluorescence.
Dead controls have zero *host* signal in this scenario; real algal and skeletal
autofluorescence are outside the model. These distinctions follow coral
pigment research, not a universal diagnostic rule.
[Fluorescent protein diversity](https://pmc.ncbi.nlm.nih.gov/articles/PMC2481297/),
[colour morph study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8022974/).

Emission on detailed scanned colonies is limited per vertex by cone, range,
attenuation and surface facing, with conservative colony/rock occlusion.
The colony does not receive a uniform whole-object glow. This remains an
RGB approximation, not measured excitation transport or exact coral
self-occlusion. Turning source strength to zero removes the host signal.
Comparison modes keep ambient illumination and camera pose fixed. The
inspection tours use explicit rendering poses, separate from autonomous
navigation, and never change mission biology.

The source scan supplies spatial calice detail, not a measured fluorescence
map. New diffuse/roughness maps retain warm ivory tissue and residual pigment
islands in bleached living colonies; healthy hues are subdued and surface
specular response is reduced. Full-resolution hero geometry preserves the
original UV seams. `natural_reef.json` uses an artistic emission gain of 0.07
and a 50-degree beam half-angle. See [material provenance](ASSETS.md).

`inspection` settings include `enabled`, `mode` (`white`, `blue`, `uv`, `off`,
or mission `auto`), `ambient_scale`, `white_intensity`, `blue_intensity`,
`emission_gain`, `range_m`, `half_angle_degrees`, `attenuation`,
`visible_uv_pilot` and `uv_pilot_intensity`. `render.volumetric_water` enables
renderer scattering of the visible beam. In the
contact mission, `auto` uses UV only while approaching and scanning provisional
recipient/donor candidates. White light is used after approval, throughout
pickup, carrying, placement and mechanical verification. Both lamps use a
50-degree half-angle (100-degree full cone), giving a geometric footprint about
2.62 m across at 1.1 m axial distance: 7.2 times the old 24-degree cone area at
the same distance. Occlusion, surface slope and water attenuation affect the
visible footprint.

With `inspection.require_detection=true`, each pair must pass two three-second
UV scans before the gripper may approach a cutting. Detection records exposure,
illustrative host signal, health/species and known-lineage compatibility. Rejected
or insufficiently illuminated candidates cannot be harvested. This is an
analytical sensor/registry proxy, not classification of rendered camera pixels;
colour does not establish genotype. The final state preserves both approval
receipts and their timestamps before harvest. `detection_standoff`,
`detection_duration` and `min_detection_exposure` configure this gate.

## Current and habitat detail

Stony skeletons and grasped cuttings remain rigid. Larger flexible fans are
placed in clear reef pockets, and soft tentacle patches are anchored to
surface points on living colonies. Their vertices move under quadratic drag
from the configured mean current plus an illustrative 6.5-second surge and
transverse-flow cycle. Damped responses, anchored roots/calice cups and
bounded deformation keep the movement controlled; normals are updated.
Zero mean current gives a static control. Absolute-time evaluation keeps
preview and movie replay consistent. The enlarged polyps and lumped response
are not CFD or a calibrated fluid–structure solver.
[Coral tentacle mechanics](https://pmc.ncbi.nlm.nih.gov/articles/PMC7329047/).

The 25-second `scripts/render_reef_details.py` reel compares a cached
zero-current view with an eight-second fixed-camera current shot and a
polyp inset. It checks tracked fan-tip peak-to-peak movement exceeds 2 cm,
zero-current response before/after, stable topology and unchanged rigid
skeletons. Five subsequent views show healthy white, bleached white/blue/UV
and dead white, with robot/light context. This describes its required checks,
not a completed-recording result; see [VALIDATION.md](VALIDATION.md).

Living colonies have polyp/tissue detail absent from the dead controls.
Irregular, pitted limestone outcrops replace smooth ellipsoids; their bases
intersect the rippled seabed and their bounds respect navigation obstacles.
Connected reef pavement, clustered colonies, 42 schooling fish and marine
snow remain in the scene. All assets are bundled and rendering is offline.

## Reproduce on Spark

```bash
cd /home/smint/pelagic-reef
/home/smint/isaacsim/python.sh -u scripts/render_reef_details.py \
  --config configs/natural_reef.json --samples 3 --quality 17 \
  --output outputs/natural-reef-details
/home/smint/isaacsim/python.sh -u scripts/render_demo.py \
  --config configs/natural_reef.json --fps 24 --max-frames 2600 \
  --samples 4 --quality 17 --output outputs/natural-reef-pip
python3 scripts/validate_demo.py outputs/natural-reef-pip
```

Use `--preview-stills` on the detail recorder for three current views and
five tissue/light boards. The earlier `render_inspection.py` remains available
for the 15-case colour tour. Use `--preview-stills --all-transfers` on the
mission recorder for 34 manipulation reviews. None starts a streaming server.


### Visible flashlight cone in offline recordings

`natural_reef.json` enables the actual shaped RTX wrist light plus a modest analytical single-scattering pass (`reefsim/beam_optics.py`). The pass uses each rendered camera’s USD transform, lens and first-surface depth, along with the actual wrist-light transform. It integrates a smooth visible cone with bounded inverse-square illumination, attenuation and a full-resolution cone/depth intersection mask. Foreground opaque surfaces end the integration; no screen-space cone is drawn through them. Six tests cover zero/off behavior, cone placement, thin foreground occlusion, rigid-transform invariance and bounded output.

The visible violet pilot is separate from invisible 365 nm excitation. Native RTX lighting supplies the surface footprint; the added water glow is an illustrative, non-spectral scattering approximation. It does not calculate a source-to-water shadow map or calibrated radiative transfer. Automatic lamp power scales with squared target distance to keep nearby contact views readable. The fixed current-review camera has a white observer lamp; it is switched off for mission and optical-comparison shots. No geometry is added during the recording.
