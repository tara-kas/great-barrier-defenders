#!/usr/bin/env python3
"""Optional GPU gateway scaffold; requires NVIDIA cuOpt 26.10 + cudf + numpy.

Not deployed or GPU-validated in this workspace. No CPU result is labelled cuOpt.
Run on an explicitly provisioned GPU host with CUOPT_API_KEY set, then point
CUOPT_ADAPTER_URL at its protected /solve endpoint. Local reflexes own collisions.
"""
import json
import math
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def optimize(data):
    import numpy as np
    from cuopt import distance_engine, routing
    import cudf
    routes = data.get("alternatives")
    if not isinstance(routes, list) or not 1 <= len(routes) <= 2:
        raise ValueError("Expected one or two routes")
    costs = {}
    for route in routes:
        name, points = route.get("id"), route.get("points")
        if name not in ("direct", "clearance") or name in costs or not isinstance(points, list) or not 2 <= len(points) <= 64:
            raise ValueError("Invalid route")
        if any(not isinstance(p,list) or len(p)!=3 or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in p) for p in points):
            raise ValueError("Invalid coordinates")
        # Each supplied corridor becomes a bidirectional weighted waypoint graph.
        # GPU costs compare declared corridors; this is not free-space path creation.
        offsets, edges, weights = [0], [], []
        for i, point in enumerate(points):
            for j in (i-1,i+1):
                if 0 <= j < len(points):
                    edges.append(j)
                    weights.append(max(1e-6, math.dist(point, points[j])))
            offsets.append(len(edges))
        graph = distance_engine.WaypointMatrix(np.array(offsets,dtype=np.int32), np.array(edges,dtype=np.int32), np.array(weights,dtype=np.float32))
        targets = np.array([0,len(points)-1],dtype=np.int32)
        cost_matrix = graph.compute_cost_matrix(targets)
        model = routing.DataModel(2,1,1)
        model.add_cost_matrix(cost_matrix)
        model.set_vehicle_locations(cudf.Series([0],dtype="int32"),cudf.Series([1],dtype="int32"))
        model.set_order_locations(cudf.Series([1],dtype="int32"))
        settings = routing.SolverSettings()
        settings.set_time_limit(1)
        solution = routing.Solve(model,settings)
        cost = float(solution.get_total_objective())
        route_frame = solution.get_route()
        if not math.isfinite(cost) or cost < 0 or len(route_frame)==0:
            raise ValueError("Solver did not produce a finite route")
        costs[name] = cost
    return {"id":data.get("id"),"source":"cuopt","model":"nvidia-cuopt-26.10",
            "status":"solved_candidate_costs","routeMode":min(costs,key=costs.get),"costs":costs}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def do_POST(self):
        import hmac
        key=os.environ.get("CUOPT_API_KEY","")
        if not key or not hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+key):
            self.send_error(403);return
        if self.path!="/solve":
            self.send_error(404);return
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=32768:raise ValueError("Body limit")
            result=optimize(json.loads(self.rfile.read(length)))
            status=200
        except Exception:
            result={"ok":False,"error":"GPU optimizer unavailable or invalid request; no fallback"};status=502
        body=json.dumps(result,allow_nan=False).encode()
        self.send_response(status);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)


if __name__=="__main__":
    if not os.environ.get("CUOPT_API_KEY"):
        raise SystemExit("Set CUOPT_API_KEY before starting the optional GPU gateway")
    server=ThreadingHTTPServer(("127.0.0.1",8091),Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
