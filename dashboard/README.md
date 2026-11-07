# dashboard

Live view shown alongside the stream during the demo: camera + detections, map, decision log, link status (simulated acoustic link state).

Owner: TBD (see CLAUDE.md section 10).

Reads from the same event/decision log the `/agent` loop writes to; does not call models directly.
