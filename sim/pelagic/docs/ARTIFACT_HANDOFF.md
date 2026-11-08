# Pipeline artifacts

| Artifact | Location |
| --- | --- |
| Pipeline video | [pipeline-video.mp4](../../../docs/media/pipeline-video.mp4) |
| README preview | [pipeline-preview.gif](../../../docs/media/pipeline-preview.gif) |
| Technical summary | [technical-summary-current.pdf](../../../docs/submission/technical-summary-current.pdf) |
| Selected result index | [final-evidence-index.json](../../../docs/evidence/final-evidence-index.json) |
| Completed mission record | [live-model-episode.json](../../../docs/evidence/live-model-episode.json) |
| Completed mission summary | [live_stack_completed_placement.json](evidence/live_stack_completed_placement.json) |

The [artifact reference](../../../docs/EVIDENCE.md) explains source revisions, image hashes, model receipts and outcome counters. The [media reference](../../../docs/media/README.md) records video dimensions and checksums.

Build the technical summary from the repository root with `python3 tools/build_technical_summary.py` in an environment containing ReportLab. Render both PDF pages and inspect their layout, then run `python3 tools/verify_submission.py`.

For new recordings, export the episode and telemetry with the capture. `scripts/finalize_live_capture.py` checks recording continuity and duration; outcome counters come from the episode itself. Keep each recording's source labels and model receipts attached to that recording.
