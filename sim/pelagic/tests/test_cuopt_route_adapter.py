"""Native solver protocol tests use dependency doubles; live GPU checks are separate."""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("cuopt_route_adapter", Path(__file__).resolve().parents[1]/"scripts/cuopt_route_adapter.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

class CuOptProtocolTests(unittest.TestCase):
    def modules(self, status=0, cost=3.0, locations=(0,1), infeasible=()):
        solution = Mock()
        solution.get_status.return_value = status
        solution.get_total_objective.return_value = cost
        solution.get_vehicle_count.return_value = 1
        solution.get_infeasible_orders.return_value = list(infeasible)
        frame = {"location":Mock()}
        frame["location"].to_arrow.return_value.to_pylist.return_value = list(locations)
        solution.get_route.return_value = frame
        routing = types.SimpleNamespace(DataModel=Mock(), SolverSettings=Mock(), Solve=Mock(return_value=solution), SolutionStatus=types.SimpleNamespace(SUCCESS=0))
        graph = Mock()
        distance = types.SimpleNamespace(WaypointMatrix=Mock(return_value=graph))
        np = types.SimpleNamespace(array=lambda value, dtype:value, int32="int32",float32="float32")
        cudf = types.SimpleNamespace(Series=lambda value,dtype:value)
        return {"numpy":np,"cudf":cudf,"cuopt":types.SimpleNamespace(routing=routing,distance_engine=distance)}, routing, distance

    def test_success_requires_native_graph_solve_and_complete_endpoints(self):
        modules,routing,distance = self.modules()
        with patch.dict("sys.modules",modules):
            result=adapter.optimize({"id":"plan-1","alternatives":[{"id":"direct","points":[[0,0,0],[3,0,0]]}]})
        routing.Solve.assert_called_once()
        distance.WaypointMatrix.assert_called_once_with([0,1,2],[1,0],[5.0,5.0])
        self.assertEqual(result["solverStatus"],"SUCCESS")
        self.assertEqual(result["objectiveCost"],3)
        self.assertEqual(result["requestId"],"plan-1")

    def test_failed_incomplete_and_nonfinite_native_solutions_never_claim_success(self):
        for args in ({"status":2},{"cost":float("nan")},{"locations":(0,)},{"infeasible":(1,)}):
            modules,_,_=self.modules(**args)
            with patch.dict("sys.modules",modules),self.assertRaises(ValueError):
                adapter.optimize({"id":"plan-1","alternatives":[{"id":"direct","points":[[0,0,0],[3,0,0]]}]})

    def test_contact_penalty_can_favor_clearance_and_current_changes_direction_cost(self):
        contacts=[{"position":[1,0,0],"sources":["synthetic_geometric_sonar"]}]
        direct=adapter.edge_cost([0,0,0],[2,0,0],[0,0,0],contacts)
        path=[[0,0,0],[0,2,0],[2,2,0],[2,0,0]]
        clearance=sum(adapter.edge_cost(a,b,[0,0,0],contacts) for a,b in zip(path,path[1:]))
        self.assertLess(clearance,direct)
        self.assertLess(adapter.edge_cost([0,0,0],[2,0,0],[.3,0,0],[]),adapter.edge_cost([2,0,0],[0,0,0],[.3,0,0],[]))

    def test_malformed_coordinates_fail_before_solver(self):
        modules,routing,_=self.modules()
        with patch.dict("sys.modules",modules),self.assertRaises(ValueError):
            adapter.optimize({"id":"plan-1","alternatives":[{"id":"direct","points":[[0,0,0],[float("inf"),0,0]]}]})
        routing.Solve.assert_not_called()
