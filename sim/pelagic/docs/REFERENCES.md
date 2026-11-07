# Design references

Original implementation; no code or assets copied from the projects below. These references informed the separation of sensing, hydrodynamics, mission control and rendering.

- [OceanSim, University of Michigan Field Robotics Group](https://github.com/umfieldrobotics/OceanSim): underwater image attenuation/backscatter and separating perception from robot motion. Its published 5.1 extension is not imported into this 6.0 project.
- [GRAAL-Lab IsaacSim Underwater](https://github.com/GRAAL-Lab/IsaacSim_Underwater): modular vehicle dynamics and sensor stack. This project uses a smaller explicitly documented dynamics model, not its full Fossen model.
- [Isaac Sim 6.0 basic robot tutorial](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/introduction/quickstart_isaacsim_robot.html): standalone application lifecycle and initialization order.
- [NVIDIA RTX common settings](https://docs-prod.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_common.html): exponential renderer fog.
- [NOAA coral bleaching](https://oceanservice.noaa.gov/facts/coral_bleach.html): distinguishes bleached living coral from dead coral.
- [NOAA restoration guidance](https://floridakeys.noaa.gov/media/docs/20190605-guidance-on-coral-restoration-outplanting.pdf): substrate suitability and avoiding unstable bioeroded structures.
- [Collins et al., Science Advances, 2026, doi:10.1126/sciadv.aeh1580](https://pmc.ncbi.nlm.nih.gov/articles/PMC13665998/): same-genet healthy/bleached *Pocillopora damicornis* tissue contact. Study photographs informed the paired branch fixture; laboratory recovery is not simulated. See [implementation boundaries](INSPECTION_AND_CONTACT.md).
- [Coral fluorescent protein diversity](https://pmc.ncbi.nlm.nih.gov/articles/PMC2481297/) and [colour morph study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8022974/): reflected pigment and host fluorescence are distinct; synthetic appearance groups are not a universal genetic classifier.
- [Coral tentacle mechanics](https://pmc.ncbi.nlm.nih.gov/articles/PMC7329047/): motivation for flexible living appendages while stony skeletons remain rigid. The fan bending model is an engineering approximation.

Browser renderer dependency: vendored Three.js, MIT license in `web/vendor/THREE-LICENSE.txt`. Procedural geometry and bundled scan/material assets require no runtime downloads; see [asset provenance](ASSETS.md).

Habitat and health distinctions: [Reef Authority coral and coral cover](https://www.gbrmpa.gov.au/learn/coral), [Reef Authority coral bleaching](https://www.gbrmpa.gov.au/learn/reef-health/coral-bleaching). These inform the artistic scene; the simulation does not predict recovery. Bundled scan provenance is in [SCANNED_CORALS.md](SCANNED_CORALS.md) and [POCILLOPORA_SCAN.md](POCILLOPORA_SCAN.md).
