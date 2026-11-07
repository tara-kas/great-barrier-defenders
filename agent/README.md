# agent

On-device agent loop (~1 Hz, Gemma): observe, update belief, pick a tool (`scan`, `goto`, `inspect`, `grasp`, `carry`, `place`, `verify`, `abort`), check outcome, revise plan. Episodic memory of rejected sites. Site optimiser (classical, inspectable scoring + assignment with spacing constraints and a value-of-information step).

Owner: TBD (see CLAUDE.md section 10).

Every decision must log the sensor evidence that caused it (feeds the on-screen decision log and the `/cloud` debrief). Abstains (hold/re-observe/skip) when unsure.
