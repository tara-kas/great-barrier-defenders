# Lab verification commands

The browser, gateway and solver adapters have separate regression checks. The [scenario guide](../../../docs/SCENARIOS.md) maps the cases to their tests, and the [selected artifact reference](../../../docs/EVIDENCE.md) describes live-result records.

From the repository root, install dependencies following [SETUP](../../../SETUP.md), then run:

```bash
python3 tools/verify_submission.py
cd sim/pelagic
node --test tests/lab-*.test.mjs
python3 -m unittest tests.test_lab_server tests.test_cuopt_route_adapter tests.test_team_feed tests.test_live_feed tests.test_live_stream_capture
python3 scripts/edge_test_gateway.py
```

These regressions execute production controller and adapter code with declared provider doubles and local HTTP servers. Artifact verification checks the retained live results independently: hashes, source revisions, model identifiers, native solver records and measured resource scopes.

To exercise configured services, open the lab, wait for readiness, load a documented scene and start the mission. Export the complete episode with transport activity. Use camera capture IDs, image hashes, target IDs, provider receipts, solver output and final counters to trace the run end to end.
