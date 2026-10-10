"""Unit tests for the pure automation helpers in the bundled Remote Script.

The Remote Script imports Ableton's ``_Framework``, which only exists inside
Live, so a minimal stub is registered before loading the file.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / "MCP_Server" /
          "bundled_ableton_remote_script" / "AbletonMCP_init.py")


def _load_script():
    framework = types.ModuleType("_Framework")
    control_surface = types.ModuleType("_Framework.ControlSurface")
    control_surface.ControlSurface = type("ControlSurface", (), {})
    sys.modules.setdefault("_Framework", framework)
    sys.modules.setdefault("_Framework.ControlSurface", control_surface)
    spec = importlib.util.spec_from_file_location("abletonmcp_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


class AutomationPointsTest(unittest.TestCase):
    def test_sorts_and_converts(self):
        pts = script._automation_points([{"time": 4, "value": 1}, {"time": 0, "value": "0.5"}])
        self.assertEqual(pts, [(0.0, 0.5, False), (4.0, 1.0, False)])

    def test_rejects_missing_fields_and_empty(self):
        with self.assertRaises(ValueError):
            script._automation_points([{"time": 1}])
        with self.assertRaises(ValueError):
            script._automation_points([])


class AutomationValueAtTest(unittest.TestCase):
    def setUp(self):
        self.pts = script._automation_points(
            [{"time": 0, "value": 0}, {"time": 4, "value": 1, "step": True}, {"time": 8, "value": 0}])

    def test_linear_ramp(self):
        self.assertAlmostEqual(script._automation_value_at(self.pts, 2), 0.5)

    def test_step_holds_until_next_point(self):
        self.assertEqual(script._automation_value_at(self.pts, 6), 1.0)

    def test_holds_outside_points(self):
        self.assertEqual(script._automation_value_at(self.pts, -3), 0.0)
        self.assertEqual(script._automation_value_at(self.pts, 20), 0.0)


class AutomationSegmentsTest(unittest.TestCase):
    def test_segments_cover_range_without_gaps(self):
        pts = script._automation_points([{"time": 0, "value": 0}, {"time": 4, "value": 1}])
        segs = script._automation_segments(pts, 0.0, 16.0, 0.25, 0.0, 1.0)
        self.assertAlmostEqual(segs[0][0], 0.0)
        for (t0, d0, _), (t1, _, _) in zip(segs, segs[1:]):
            self.assertAlmostEqual(t0 + d0, t1)
        last_t, last_d, last_v = segs[-1]
        self.assertAlmostEqual(last_t + last_d, 16.0)
        self.assertEqual(last_v, 1.0)

    def test_constant_runs_merge(self):
        pts = script._automation_points([{"time": 0, "value": 0.3}])
        segs = script._automation_segments(pts, 0.0, 16.0, 0.125, 0.0, 1.0)
        self.assertEqual(segs, [(0.0, 16.0, 0.3)])

    def test_values_clamped_to_parameter_range(self):
        pts = script._automation_points([{"time": 0, "value": -5}, {"time": 1, "value": 5}])
        segs = script._automation_segments(pts, 0.0, 2.0, 0.5, 0.0, 1.0)
        self.assertTrue(all(0.0 <= v <= 1.0 for _, _, v in segs))

    def test_point_times_are_step_boundaries(self):
        pts = script._automation_points(
            [{"time": 0, "value": 0, "step": True}, {"time": 1.3, "value": 1}])
        segs = script._automation_segments(pts, 0.0, 4.0, 1.0, 0.0, 1.0)
        self.assertIn(1.3, [round(t, 9) for t, _, _ in segs])

    def test_resolution_floor(self):
        pts = script._automation_points([{"time": 0, "value": 0}, {"time": 1, "value": 1}])
        segs = script._automation_segments(pts, 0.0, 1.0, 0.0, 0.0, 1.0)
        self.assertLessEqual(len(segs), 64)


if __name__ == "__main__":
    unittest.main()
