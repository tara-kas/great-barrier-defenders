# Integrated reef mission validation — 8 November 2026

The actual team `mission.runner` / `MissionFSM` completed on both the Mac CPU
runtime and the DGX Spark. Isaac Sim 6.0.1 rendered the resulting authoritative
trajectory offline on the Spark. No camera livestream or model API was used.

## Finished recording

- File: `sim/pelagic/outputs/team-video/pelagic-team-pip.mp4` (generated, excluded from Git).
- Duration: 57.708 seconds; 1,385 frames, 1600×900, 24 fps.
- Size: 24,739,208 bytes.
- SHA-256: `37710b948c0ca191f59398aebe8d65a2cdbe34ef0d7a1f9901c88303c87f3b29` (Spark and local copy match).
- Entire MP4 decoded successfully. Nine action frames extracted from the encoded
  MP4 were reviewed, including UV, donor grasp, loss, regrasp, lowering, release,
  push test and withdrawal.
- Three synchronized actual RTX camera products: director, scout, wrist/tool.
- 518 scanned decorative colonies, 48 original-UV high-detail specimens near
  the action, 15,864,591 decorative triangles; 24 semantic colonies additionally.

## Mission evidence

- One harvest from living `coral-005`; no supply table/rack.
- Two accepted UV inspections before harvest: recipient, then donor.
- `fragment-005` was harvested, dropped, recovered and placed on `coral-007`.
  Identity and local geometry remained unchanged through every stage.
- Cutting surfaces partition the original donor scan. There is no manufactured
  donor connector or recipient extension branch, and no roots appear at release.
- The selected contact is an original living-tissue vertex above the severed
  edge against an actual triangle of the bleached colony.
- 0.18 N spring-damper push test: peak integrated displacement
  0.432 mm; sampled contact gap
  0.399 mm, below the 1.5 mm tolerance.
- 104 independent USD geometry checks passed, including persistent meshes,
  position/yaw, measured grip alignment, wrist rotation and recipient contact.
- Weak/broken joint tests fail as intended. A carried-fragment replan preserves
  identity; no approved recipient and no valid return fixture causes a safe hold.

## Software checks and limits

251 tests passed across the applicable team, perception and simulator suites.
One optional installed-SDK serialization test was skipped in the default local
interpreter; the Gemini SDK transport was separately tested in an isolated SDK
2.33 environment without making an API call. Regression reruns addressed two
legacy tests' working-directory assumptions and localhost socket sandbox limits.

The recording uses a pre-mapped synthetic registry and analytical UV checks,
explicitly labelled **OFFLINE DEMO PERCEPTION / NO MODEL CALL**. The cheap Gemini
adapter is implemented but live-service validation awaits a configured key.
The perturbation is intentionally injected, and playback speed varies. This is
not an unscripted live-perception competition submission.

Body movement is a reduced velocity-tracking model; loose cuttings use submerged
weight/drag and a bed constraint; attachments use a spring-damper proxy. These
are not full fluid/PhysX contact/fracture dynamics. The current adapter does not
supply rendered RGB-D to the visual classifier. Coral health and known lineage
are scenario metadata. Immediate verified treatment does not mean tissue fusion,
symbiont transfer, genetic identification, or biological recovery was simulated.
