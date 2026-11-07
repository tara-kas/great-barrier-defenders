# eval

Scenario suite, metrics, and the regression harness that gates every Argon-proposed patch (CLAUDE.md section 8: "every Argon-generated patch needs a regression test before it is merged").

Owner: TBD (see CLAUDE.md section 10).

Metrics to report (CLAUDE.md section 11): fragment survival/placement stability across N perturbation runs, optimiser vs. nearest-site baseline, v1 vs. v2 after a human-approved patch, abstention quality, latency/energy per component.

Deterministic seeds for scenarios; an unseeded "live" mode is reserved for the one unscripted change in the demo video.
