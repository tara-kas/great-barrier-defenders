#!/usr/bin/env python3
"""Native GPU corridor optimizer; requires NVIDIA cuOpt 26.10 + cudf + numpy.

Not deployed or GPU-validated in this workspace. No CPU result is labelled cuOpt.
Run on an explicitly provisioned GPU host with CUOPT_API_KEY set, then point
CUOPT_ADAPTER_URL at its protected /solve endpoint. Local reflexes own collisions.
"""
import json
import math
import os
import time
import importlib.metadata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


COST_MODEL = {"name":"current_and_contact_transit_proxy", "units":"weighted_seconds", "nominalSpeedMS":0.6,
              "minimumGroundSpeedMS":0.15, "maximumGroundSpeedMS":2.0, "hazardRadiusM":1.2,
              "hazardPenaltySecondsPerM":30.0, "calibrated":False,
              "source":"request synthetic fusion contacts and current vector; engineering proxy"}


def vector(value):
    return isinstance(value, list) and len(value) == 3 and all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and abs(x)<=10000 for x in value)


def edge_cost(start, end, current, contacts):
    """Transparent engineering weights supplied to the actual GPU graph solver."""
    delta = [b-a for a,b in zip(start,end)]
    length = max(1e-6, math.dist(start,end))
    projection = sum(c*d/length for c,d in zip(current,delta))
    speed = min(COST_MODEL["maximumGroundSpeedMS"],max(COST_MODEL["minimumGroundSpeedMS"],COST_MODEL["nominalSpeedMS"]+projection))
    penalty = 0.0
    for contact in contacts:
        point = contact["position"]
        t = min(1,max(0,sum((p-a)*d for p,a,d in zip(point,start,delta))/(length*length)))
        distance = math.dist(point,[a+t*d for a,d in zip(start,delta)])
        penalty += COST_MODEL["hazardPenaltySecondsPerM"]*length*max(0,1-distance/COST_MODEL["hazardRadiusM"])**2
    return length/speed + penalty


def optimize(data):
    started = time.perf_counter()
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not 1 <= len(data["id"]) <= 120:
        raise ValueError("A bounded request id is required")
    import numpy as np
    from cuopt import distance_engine, routing
    import cudf
    routes = data.get("alternatives")
    if not isinstance(routes, list) or not 1 <= len(routes) <= 2:
        raise ValueError("Expected one or two routes")
    current = data.get("currentVector", [0,0,0])
    fusion = data.get("fusion", {})
    if not vector(current) or any(abs(v)>20 for v in current) or not isinstance(fusion, dict):
        raise ValueError("Invalid bounded current or fusion")
    contacts = fusion.get("contacts", [])
    if not isinstance(contacts, list) or len(contacts)>32 or any(not isinstance(c,dict) or not vector(c.get("position")) for c in contacts):
        raise ValueError("Invalid bounded contact positions")
    costs = {}
    for route in routes:
        if not isinstance(route, dict):
            raise ValueError("Route must be an object")
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
                    weights.append(edge_cost(point, points[j], current, contacts))
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
        status = solution.get_status()
        success = routing.SolutionStatus.SUCCESS
        if getattr(status, "value", status) != getattr(success, "value", success) or len(solution.get_infeasible_orders()) != 0:
            raise ValueError("cuOpt did not solve every required order")
        cost = float(solution.get_total_objective())
        route_frame = solution.get_route()
        if not math.isfinite(cost) or cost < 0 or len(route_frame)==0:
            raise ValueError("Solver did not produce a finite route")
        locations = route_frame["location"].to_arrow().to_pylist()
        if 0 not in locations or 1 not in locations or solution.get_vehicle_count() != 1:
            raise ValueError("cuOpt route does not visit both required endpoints")
        costs[name] = cost
    selected = min(costs, key=costs.get)
    try:
        version = importlib.metadata.version("cuopt-cu12")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return {"id": data["id"], "requestId": data["id"], "source": "cuopt", "configured": True,
            "model": "nvidia-cuopt", "solverVersion": version, "solverStatus": "SUCCESS",
            "status": "solved", "routeMode": selected, "objectiveCost": costs[selected], "costs": costs,
            "solveTimeMs": round((time.perf_counter()-started)*1000), "costModel": COST_MODEL,
            "inputContacts":len(contacts), "inputCurrentVector":current}



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
