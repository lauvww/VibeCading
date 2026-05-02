from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.dsl import CadJob
from core.job_runner import run_job
from core.nl_job_planner import draft_feature_plan_from_natural_language, draft_primitive_job_from_natural_language
from core.validators import validate_job


SHAFT_REQUEST = "做一个阶梯轴，总长120，最大直径40，左段直径30长度40，右段直径20长度30，中心孔直径10贯穿，材料45钢"
PLATE_REQUEST = "做一个安装板，长120宽80厚8，四角孔孔径8，孔边距15，材料6061铝"


class NaturalLanguageJobPlannerTests(unittest.TestCase):
    def test_drafts_valid_stepped_shaft_job(self) -> None:
        draft = draft_primitive_job_from_natural_language(SHAFT_REQUEST)
        self.assertTrue(draft["ready_for_execution"])
        self.assertEqual(draft["strategy"]["chosen_strategy"], "revolve_then_cut_revolve")
        self.assertIsNotNone(draft["job"])
        self.assertEqual(draft["feature_plan"]["dominant_geometry"], "rotational")
        self.assertEqual(draft["feature_plan"]["features"][0]["method"], "revolve")
        self.assertIn("rotational_part", draft["feature_plan"]["engineering_context"]["part_roles"])
        self.assertEqual(draft["feature_plan"]["features"][0]["functional_role"], "stepped_rotational_body")
        self.assertEqual(draft["feature_plan"]["features"][0]["sketch_strategy"]["type"], "half_section_closed_profile")

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        self.assertEqual(job.kind, "primitive_part")
        self.assertEqual(job.part.material, "45钢")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("revolve"), 1)
        self.assertEqual(operation_types.count("cut_revolve"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 2)

    def test_preview_runs_generated_stepped_shaft_job(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "nl-stepped-shaft-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            draft = draft_primitive_job_from_natural_language(SHAFT_REQUEST)
            job = CadJob.from_dict(draft["job"])
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 16)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("revolve"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_revolve"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 120.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 40.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 40.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_does_not_silently_ignore_ring_groove(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "做一个阶梯轴，总长120，最大直径40，中心孔直径10，环形槽宽8槽底直径32"
        )
        self.assertFalse(draft["ready_for_execution"])
        self.assertIsNone(draft["job"])
        self.assertTrue(any("环形槽" in item for item in draft["questions"]))
        self.assertTrue(any("环形槽" in item for item in draft["warnings"]))

    def test_drafts_valid_mounting_plate_job(self) -> None:
        draft = draft_primitive_job_from_natural_language(PLATE_REQUEST)
        self.assertTrue(draft["ready_for_execution"])
        self.assertEqual(draft["strategy"]["chosen_strategy"], "extrude_then_cut_extrude")
        self.assertEqual(len(draft["parsed_parameters"]["holes"]), 4)
        self.assertEqual(draft["feature_plan"]["dominant_geometry"], "prismatic")
        self.assertEqual(draft["feature_plan"]["features"][0]["method"], "extrude")
        self.assertEqual(draft["feature_plan"]["features"][1]["method"], "cut_extrude")
        self.assertIn("mounting_support", draft["feature_plan"]["engineering_context"]["part_roles"])
        self.assertIn("four_corner_fastener_pattern", draft["feature_plan"]["engineering_context"]["mating_interfaces"])
        self.assertEqual(draft["feature_plan"]["features"][0]["functional_role"], "mounting_plate_body")
        self.assertEqual(draft["feature_plan"]["features"][1]["functional_role"], "fastener_hole_pattern")
        self.assertEqual(draft["feature_plan"]["features"][1]["sketch_strategy"]["type"], "same_plane_circle_layout")

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        self.assertEqual(job.kind, "primitive_part")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("extrude"), 1)
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("add_circle"), 4)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 2)

    def test_preview_runs_generated_mounting_plate_job(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "nl-mounting-plate-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            draft = draft_primitive_job_from_natural_language(PLATE_REQUEST)
            job = CadJob.from_dict(draft["job"])
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 18)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("extrude"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_extrude"), 1)
            self.assertEqual(summary["metadata"]["hole_count"], 4)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 120.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 80.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 8.0)
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_plate_slot_is_not_silently_ignored(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长120宽80厚8，中间开槽，槽宽12")
        self.assertFalse(draft["ready_for_execution"])
        self.assertIsNone(draft["job"])
        self.assertTrue(any("槽" in item for item in draft["questions"]))
        self.assertTrue(any(item["feature"] == "slot_or_pocket" for item in draft["feature_plan"]["missing_capabilities"]))

    def test_adjustment_obround_slot_is_recorded_as_planned_feature(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "做一个用于固定电机的安装板，长120宽80厚8，两个长圆孔用于调节张紧，槽长30槽宽8"
        )
        self.assertTrue(draft["ready_for_execution"])
        feature_plan = draft["feature_plan"]
        self.assertIn("adjustable_mounting", feature_plan["engineering_context"]["working_context"])
        self.assertFalse(any(item["feature"] == "obround_slot" for item in feature_plan["missing_capabilities"]))
        slot_feature = next(feature for feature in feature_plan["features"] if feature["kind"] == "obround_slot")
        self.assertEqual(slot_feature["functional_role"], "adjustment_slot")
        self.assertEqual(slot_feature["sketch_strategy"]["type"], "straight_slot_profile")
        self.assertEqual(slot_feature["parameters"]["length"], 30.0)
        self.assertEqual(slot_feature["parameters"]["width"], 8.0)
        self.assertEqual(slot_feature["parameters"]["count"], 2)
        self.assertEqual(slot_feature["parameters"]["position_strategy"], "two_parallel_slots_symmetric_about_part_center")
        self.assertEqual(slot_feature["required_parameters"], [])

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("add_straight_slot"), 2)
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 2)

    def test_preview_runs_generated_obround_slot_job(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "nl-obround-slot-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            draft = draft_primitive_job_from_natural_language(
                "做一个用于固定电机的安装板，长120宽80厚8，两个长圆孔用于调节张紧，槽长30槽宽8"
            )
            job = CadJob.from_dict(draft["job"])
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 13)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_straight_slot"), 2)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_extrude"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 120.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 80.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 8.0)
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_rotational_seal_groove_is_recorded_as_planned_feature(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "做一个阶梯轴，总长120，最大直径40，中心孔直径10，密封槽宽5槽底直径32距左端40"
        )
        self.assertTrue(draft["ready_for_execution"])
        feature_plan = draft["feature_plan"]
        self.assertIn("sealing", feature_plan["engineering_context"]["part_roles"])
        groove_feature = next(feature for feature in feature_plan["features"] if feature["kind"] == "groove")
        self.assertEqual(groove_feature["functional_role"], "seal_groove")
        self.assertEqual(groove_feature["method"], "cut_revolve")
        self.assertEqual(groove_feature["parameters"]["width"], 5.0)
        self.assertEqual(groove_feature["parameters"]["bottom_diameter"], 32.0)
        self.assertEqual(groove_feature["required_parameters"], [])

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("cut_revolve"), 2)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 3)

    def test_countersink_is_recorded_as_fastener_interface(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长100宽60厚10，中心沉头孔M6，沉头直径12沉头深3")
        self.assertTrue(draft["ready_for_execution"])
        feature_plan = draft["feature_plan"]
        self.assertIn("countersunk_fastener_interface", feature_plan["engineering_context"]["mating_interfaces"])
        countersink = next(feature for feature in feature_plan["features"] if feature["kind"] == "countersink")
        self.assertEqual(countersink["functional_role"], "countersunk_fastener_interface")
        self.assertEqual(countersink["parameters"]["nominal_size"], 6.0)
        self.assertEqual(countersink["parameters"]["head_diameter"], 12.0)
        self.assertEqual(countersink["sketch_strategy"]["type"], "concentric_hole_seat_profile")

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("cut_extrude"), 2)
        self.assertEqual(operation_types.count("add_circle"), 2)
        countersink_cut = [operation for operation in job.part.operations if operation.id == "拉伸切除_沉头座"][0]
        self.assertEqual(countersink_cut.parameters["draft_angle"], 45.0)

    def test_counterbore_is_compiled_as_top_face_seat_cut(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长100宽60厚10，中心沉孔M6，沉孔直径12沉孔深3")
        self.assertTrue(draft["ready_for_execution"])
        counterbore = next(feature for feature in draft["feature_plan"]["features"] if feature["kind"] == "counterbore")
        self.assertEqual(counterbore["functional_role"], "counterbored_fastener_interface")
        self.assertEqual(counterbore["parameters"]["head_diameter"], 12.0)
        self.assertEqual(counterbore["parameters"]["seat_depth"], 3.0)

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("cut_extrude"), 2)
        self.assertEqual(operation_types.count("start_sketch_on_face"), 1)

    def test_threaded_hole_is_compiled_as_tap_drill_with_metadata(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长100宽60厚10，中心螺纹孔M6深8")
        self.assertTrue(draft["ready_for_execution"])
        threaded_hole = next(feature for feature in draft["feature_plan"]["features"] if feature["kind"] == "threaded_hole")
        self.assertEqual(threaded_hole["parameters"]["thread_size"], 6.0)
        self.assertEqual(threaded_hole["parameters"]["tap_drill_diameter"], 5.0)
        self.assertEqual(threaded_hole["parameters"]["thread_depth"], 8.0)

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        cut_operations = [operation for operation in job.part.operations if operation.type == "cut_extrude"]
        self.assertEqual(len(cut_operations), 1)
        self.assertEqual(cut_operations[0].parameters["thread_metadata"]["thread_size"], 6.0)

    def test_pocket_boss_and_rib_are_compiled_when_dimensions_are_complete(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "做一个安装板，长120宽80厚8，中间口袋长40宽20深3，中间凸台直径20高6，加强筋长50厚5高12"
        )
        self.assertTrue(draft["ready_for_execution"])
        feature_kinds = [feature["kind"] for feature in draft["feature_plan"]["features"]]
        self.assertIn("slot_or_pocket", feature_kinds)
        self.assertIn("boss", feature_kinds)
        self.assertIn("rib", feature_kinds)

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("extrude"), 3)
        self.assertEqual(operation_types.count("start_sketch_on_face"), 3)

    def test_centered_clearance_slot_is_compiled_when_dimensions_are_complete(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长120宽80厚8，中间避让槽长45宽18深4")
        self.assertTrue(draft["ready_for_execution"])
        clearance = next(feature for feature in draft["feature_plan"]["features"] if feature["functional_role"] == "clearance_cut_or_relief_slot")
        self.assertEqual(clearance["parameters"]["length"], 45.0)
        self.assertEqual(clearance["parameters"]["width"], 18.0)
        self.assertEqual(clearance["parameters"]["position_strategy"], "centered_on_part_origin")

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("start_sketch_on_face"), 1)

    def test_drafts_washer_as_rotational_job(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个垫圈，外径50内径20厚5，材料45钢")
        self.assertTrue(draft["ready_for_execution"])
        self.assertEqual(draft["strategy"]["chosen_strategy"], "revolve_then_cut_revolve")
        self.assertEqual(draft["parsed_parameters"]["total_length"], 5.0)
        self.assertEqual(draft["parsed_parameters"]["outer_diameter"], 50.0)
        self.assertEqual(draft["parsed_parameters"]["bore_diameter"], 20.0)
        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("revolve"), 1)
        self.assertEqual(operation_types.count("cut_revolve"), 1)

    def test_feature_plan_can_be_requested_without_job_output(self) -> None:
        result = draft_feature_plan_from_natural_language(PLATE_REQUEST)
        self.assertTrue(result["ready_for_compilation"])
        self.assertNotIn("job", result)
        feature_plan = result["feature_plan"]
        self.assertEqual(feature_plan["version"], "feature_plan.v1")
        self.assertEqual(feature_plan["dominant_geometry"], "prismatic")
        self.assertIn("engineering_context", feature_plan)
        self.assertEqual([feature["kind"] for feature in feature_plan["features"]], ["base_body", "hole_pattern"])
        self.assertTrue(all("sketch_strategy" in feature for feature in feature_plan["features"]))

    def test_unsupported_strategy_still_returns_feature_plan(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个放样过渡风道，入口圆形出口矩形")
        self.assertFalse(draft["ready_for_execution"])
        self.assertIsNone(draft["job"])
        self.assertEqual(draft["feature_plan"]["version"], "feature_plan.v1")
        self.assertTrue(
            any(item["feature"] == "unsupported_feature_plan_family" for item in draft["feature_plan"]["missing_capabilities"])
        )


if __name__ == "__main__":
    unittest.main()
