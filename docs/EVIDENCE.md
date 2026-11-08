# Episode records and reproducibility

## Export format

This collection contains selected completed-mission, successful image-inference and service-readiness results with supporting provenance.

Use **Export** in the browser lab to save an episode and its transport activity. Each record ties mission state to the source that produced it.

| Field or record | Purpose |
| --- | --- |
| Episode ID, source revision and controller | Identify the run and executing implementation. |
| Capture/request IDs, target IDs and timestamps | Bind each camera assessment to its object and acquisition time. |
| Input image SHA-256 | Identify the exact image sent for inference. |
| Model, provider, deployment and interaction metadata | Identify the service that returned an observation or advice. |
| Advisory context provenance | Trace Argon context consumed by a fresh Gemma assessment. |
| Solver version, route alternatives and objective | Explain the native cuOpt route selection. |
| Fragment ID and state transitions | Track stock through collection, transport, recovery and placement. |
| Final state and outcome counters | Record the episode's own completion, placement, collision, drop and recovery results. |

Keep each episode's raw bytes, hashes and provider receipts together. [Scenario configurations](SCENARIOS.md) define reproducible inputs; [source manifests](evidence/edge_gateway_source_v3.json) identify deployed file snapshots.

## Selected result artifacts

| Artifact | Contents |
| --- | --- |
| [Hosted episode](evidence/live-model-episode.json) | Complete episode and activity log exported at `2026-11-08T13:41:14.099Z`. |
| [Hosted result summary](../sim/pelagic/docs/evidence/live_stack_completed_placement.json) | Source build, artifact hash, model/solver identifiers and outcome counters. |
| [Final artifact index](evidence/final-evidence-index.json) | Selected successful results and supporting provenance, with integrity hashes. |
| [Spark image benchmark](evidence/edge_gemma_benchmark.json) | Five image requests, raw responses, latencies and resource samples. |
| [Spark runtime metadata](evidence/edge_runtime_metadata.json) | Pinned model/runtime, networking and configured resources. |
| [Native solver readiness](evidence/edge_cuopt_warmup.json) | cuOpt version, candidate costs and selected route. |
| [Technical summary](submission/technical-summary-current.pdf) | Pipeline, model roles, deployment and runtime measurements. |

The hosted reference episode's SHA-256 is:

```text
18ccaa83ff528e0536ea3e738c10f4fee185c0c014fc036e4c802d4f984ce115
```

Its source build is `b5967bb2b6399ab387408812c9344e0e1606c680`. The raw record contains one mechanically verified placement in 80.55 simulated seconds, with zero collisions, drops and recoveries. Gemma identifies as `gemma-4-E4B-it`, Argon as `gemini-4-argon`, and the route uses `reef-local-policy-v1` with native cuOpt `26.10.0`.

Browser round-trip measurements in that record are 2.687–3.201 seconds for five Gemma responses and 22.700 seconds for one Argon response. The native cuOpt solve records 0.198 seconds. [Spark measurements](EDGE_DEPLOYMENT.md#measured-resource-budget) describe local inference and resource-counter scopes.

## Verify artifact integrity

From the repository root:

```bash
python3 tools/verify_submission.py
```

The verifier checks raw hashes, source manifests, recorded model identities, edge input/response integrity, resource counters and local documentation targets. The [setup guide](../SETUP.md#regression-checks) provides software regression commands; these use declared provider doubles and local HTTP servers. Live service requests retain their own episode and transport receipts.
