# eval

Evaluation tools and regression tests for the Python research stack. The current
browser demo has its own tests under `sim/pelagic/tests`. Start with the
[project README](../README.md), [architecture](../docs/ARCHITECTURE.md),
[scenarios](../docs/SCENARIOS.md) and [judging guide](../docs/JUDGING_GUIDE.md)
for the implemented pipeline and evidence boundaries.

## Offline regression checks

```bash
python -m pytest agent/tests perception/tests eval cloud/test_debrief.py -q
```

The mock robot and seeded scenarios check planning, safety guards, registry
updates, same-fragment recovery and adapter contracts. Controlled model
responses test parsers and failure handling. Passing these tests does not
establish a live model call, a physical robot run or field performance.

## Explicit model evaluations

- `run_mock_mission.py` joins the mock robot to a configured Gemma endpoint;
  model access must be supplied separately.
- `coralscapes_eval.py --dry-run` prepares real-photo evaluation crops (and can download dataset assets);
  running without `--dry-run` evaluates the configured Gemma endpoint.
- `generate_synthetic_frames.py` produces labelled synthetic image fixtures.
  Their requested labels are not independently verified ground truth.

Model evaluations can require credentials, network access and paid inference.
Record the model identifier, configuration, input provenance, failures and
measured outputs with any reported result. A fixture or proposed metric is not
an achieved result. In particular, this directory does not establish physical
fragment survival, energy usage or an automatic Argon patch-promotion pipeline.
