# Reef world composition and water response

The browser scene is an artistic, seeded engineering environment, not a surveyed reef or a validated fluid/structural solver. Layout should be natural without changing the meaning of perception evidence.

## Habitat composition

Implemented: two predominantly healthy regions, two predominantly bleached-but-living regions, and one mixed central transition. The shared field drives 620 irregularly clustered habitat specimens and the registered mission colony layout. Seeded region centers, sizes and density variation should produce recognizable patches without aligned rows, repeated equal spacing or a binary dividing line. Keep some healthy colonies in bleached areas and some pale colonies near healthy areas. Dead/rubble controls remain explicitly excluded from restoration targets. Mission IDs, specimen geometry, rendered health and registry eligibility must refer to the same generated placement.

The shared region field is scenario composition, not an ecological prediction of bleaching spread. Health is assigned as known scenario state; Gemma observations remain separate estimates. Avoid presenting a generated distribution as measured Moore Reef data.

## Current display

Implemented: 25 sampled flow arrows and particles advected using nearby field samples, taken from the same current model used for vehicle/fragment drag. Arrow length uses a labelled ×5 visual scale capped at 1.6 metres; opacity is boosted only for spectator readability. The visible overlay should identify its engineering scale and units, including any length/time exaggeration. Keep navigation overlays out of the robot camera images used for model inference. Suspended particles and near-bed sediment can communicate water movement without obscuring the external viewer.

## Material-specific response

- **Stony corals:** retain the attached calcium-carbonate skeleton and accurate contact geometry. A colony should not sway like a generic plant. Small polyp-tip crowns on active inspection colonies use a bounded visual response of at most 2 mm. This is an animation proxy, not solved tissue elasticity.
- **Detached cuttings:** carry state, gravity/buoyancy/drag, current-driven drift, contact and recovery identity come from the reduced simulation. The modeled grip may fail when load exceeds its engineering threshold.
- **Boulders and hard substrate:** remain fixed in the demonstrated current range. Movement of a rock is not required to show that flow acts around it.
- **Flexible organisms and sediment:** allow bounded response appropriate to the material. Visual sway, particles and seeded wildlife trajectories are not calibrated fluid–structure or behavioral models.

NOAA distinguishes rigid stony-coral skeletons from flexible soft corals: [coral anatomy](https://oceanservice.noaa.gov/education/tutorial_corals/coral01_intro.html), [hard and soft coral growth](https://oceanservice.noaa.gov/education/tutorial_corals/coral03_growth.html). These references support different material behavior; they do not validate the application's coefficients.

## Remaining physical validation

Validate six-degree-of-freedom vehicle response, calibrated hydrodynamic loads, thruster allocation, grasp slip/contact, cutting/fracture, soft-tissue response and sediment motion in the intended Isaac/hardware workflow. Browser shaders cannot establish these properties. Keep load, stiffness, friction and flow coefficients labelled as engineering approximations until measured validation exists.
