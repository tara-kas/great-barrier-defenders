# control

Reflex layer (CPU, fast, no network calls): thruster allocation, station keeping, current compensation, carry-aware control (mass/drag change when holding a fragment), collision and depth limits.

Owner: TBD (see CLAUDE.md section 10).

Consumes sensor packets / state estimates from `/perception`; never blocks on `/cloud`.
