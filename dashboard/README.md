# Reef Rescue Mission Control

React, TypeScript, Vite and Three.js dashboard interface, replacing the earlier static dashboard. It includes mission, reef map, 3D spatial view, decision trace, vehicle systems, permit-planning, topology and manual-control simulator views.

## Run locally

Requires Node.js 20.19+ or 22.12+.

```sh
cd dashboard
npm install
npm run dev
```

Open http://127.0.0.1:3000. To produce a static build, run `npm run build`; to serve the build locally, run `npm run preview`.

## Data and safety status

This interface currently runs as a **local interactive simulation**. Reef observations, camera imagery, vehicle telemetry, alerts, mission transitions and control responses are generated in the browser. It does not connect to the Python `/api/state` endpoint, a live camera, a vehicle, or a permit authority. Controls affect only simulated UI state and must not be used as real vehicle controls. The persistent notice in the interface states this.

The existing `server.py` remains available as a read-only file adapter for future integration. No production connection between that adapter and this React interface is included yet. Do not present seeded readings or scenario outcomes as field measurements.

## Build check

```sh
npm run build
```
