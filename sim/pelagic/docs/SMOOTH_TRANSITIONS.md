# Transition update — 8 November 2026

The quick review video is `outputs/smooth-transitions/pelagic-smooth-transitions.mp4`: 50.708 seconds, 1217 frames, 1600 × 900 at 24 fps. It is an explicitly labelled edit of the existing verified Isaac recording, not a fresh simulator render. Full video decoding passed and six frames were visually reviewed.

The edit removes brief intermediate camera shots, uses 16-frame camera-pane dissolves, slows carrying/orientation, interpolates ten frames around the old push-approach jump, and holds the final verified contact view. Both robot camera panes remain visible. Biological recovery and model inference remain demo assumptions; no model calls were made.

The simulator source separately fixes the 40 mm push-approach endpoint mismatch. A mission regression checks that the transition moves less than 2 mm. Team-demo plans now enable director camera smoothing (0.45 second time constant), with presentation-time stepping and rewind-safe history. Completion retains the contact shot. These source camera changes have timing/reset smoke checks but have not yet been captured in a fresh Isaac video.

To reproduce this specific edit, install OpenCV and NumPy and make ffmpeg available, then run from the repository root:

```sh
python3 sim/pelagic/scripts/smooth_recording.py \
  --source sim/pelagic/outputs/team-video/pelagic-team-pip.mp4 \
  --output sim/pelagic/outputs/smooth-transitions
```

The script verifies the source capture hash because its edit decisions use fixed frame indexes. The output folder includes the edit report and source/output provenance. Videos remain local and are ignored by Git.
