from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.strategy_planner import plan_modeling_strategy


class StrategyPlannerTests(unittest.TestCase):
    def test_rotational_request_prefers_revolve_and_cut_revolve(self) -> None:
        plan = plan_modeling_strategy("做一个带中心孔和环形槽的阶梯轴，直径40，长度120")
        self.assertEqual(plan.intent, "part_modeling")
        self.assertEqual(plan.dominant_geometry, "rotational")
        self.assertEqual(plan.chosen_strategy, "revolve_then_cut_revolve")
        self.assertIn("revolve", plan.recommended_primitives)
        self.assertIn("cut_revolve", plan.recommended_primitives)
        self.assertTrue(plan.ready_for_primitive_dsl)

    def test_face_derived_edge_notch_prefers_convert_offset_cleanup_cut(self) -> None:
        plan = plan_modeling_strategy("在120x70x8的安装板上表面做一个从边缘切入的开口槽，槽宽12")
        self.assertEqual(plan.chosen_strategy, "extrude_base_then_face_derived_cut_extrude")
        primitives = " ".join(plan.recommended_primitives)
        self.assertIn("convert_entities", primitives)
        self.assertIn("offset_entities", primitives)
        self.assertIn("trim_entities/delete_entities", primitives)
        self.assertIn("cut_extrude", primitives)

    def test_loft_request_asks_for_sections_when_missing(self) -> None:
        plan = plan_modeling_strategy("做一个放样过渡风道")
        self.assertEqual(plan.chosen_strategy, "ordered_profiles_loft_or_cut_loft")
        self.assertFalse(plan.ready_for_primitive_dsl)
        self.assertTrue(any("放样" in question and "截面" in question for question in plan.questions))

    def test_unknown_request_falls_back_to_prismatic_strategy(self) -> None:
        plan = plan_modeling_strategy("做一个零件")
        self.assertEqual(plan.chosen_strategy, "extrude_then_cut_extrude")
        self.assertEqual(plan.confidence, 0.3)
        self.assertFalse(plan.ready_for_primitive_dsl)

    def test_plate_with_center_hole_stays_prismatic(self) -> None:
        plan = plan_modeling_strategy("做一个安装板，长120宽80厚8，中间孔直径20")
        self.assertEqual(plan.dominant_geometry, "prismatic")
        self.assertEqual(plan.chosen_strategy, "extrude_then_cut_extrude")
        self.assertIn("cut_extrude", plan.recommended_primitives)


if __name__ == "__main__":
    unittest.main()
