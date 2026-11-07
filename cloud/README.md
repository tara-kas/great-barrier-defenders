# cloud

Between-dives loop (Argon, via the Interactions API): debrief (review run logs/video, label failures), coder (propose patches to planner weights / behaviour tree / controller), verifier (run patches against the `/eval` regression suite, promote only if nothing regresses **and a human approves**), scene generation/critique for Isaac Sim assets.

Owner: TBD (see CLAUDE.md section 10).

Never called from the dive loop (`/control`, `/perception`, `/agent` must stay network-free during a run). Human approval gate required before any promoted patch.
