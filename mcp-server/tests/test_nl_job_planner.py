from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.dsl import CadJob
from core.edit_planner import build_edit_plan
from core.edit_execution import apply_edit_dsl_to_feature_plan, validate_edit_dsl
from core.feature_plan import compile_feature_plan_to_primitive_job, resolve_feature_plan_references
from core.job_runner import run_job
from core.nl_job_planner import draft_feature_plan_from_natural_language, draft_primitive_job_from_natural_language
from core.part_context import build_part_context, write_part_context
from core.validators import validate_job


SHAFT_REQUEST = "做一个阶梯轴，总长120，最大直径40，左段直径30长度40，右段直径20长度30，中心孔直径10贯穿，材料45钢"
PLATE_REQUEST = "做一个安装板，长120宽80厚8，四角孔孔径8，孔边距15，材料6061铝"


class NaturalLanguageJobPlannerTests(unittest.TestCase):
    def test_auto_job_id_is_unique_without_explicit_job_id(self) -> None:
        first = draft_primitive_job_from_natural_language(PLATE_REQUEST)
        second = draft_primitive_job_from_natural_language(PLATE_REQUEST)
        self.assertTrue(first["ready_for_execution"])
        self.assertTrue(second["ready_for_execution"])
        self.assertNotEqual(first["job"]["job_id"], second["job"]["job_id"])
        self.assertTrue(first["job"]["job_id"].startswith("自然语言棱柱零件-"))

    @staticmethod
    def _manual_prismatic_plan(request: str, features: list[dict], holes: list[dict] | None = None) -> dict:
        return {
            "version": "feature_plan.v1",
            "source": "natural_language",
            "request": request,
            "units": "mm",
            "dominant_geometry": "prismatic",
            "strategy": {
                "chosen_strategy": "extrude_then_cut_extrude",
                "selection_reason": "test",
                "alternatives_considered": [],
            },
            "engineering_context": {
                "part_roles": ["mounting_support"],
                "working_context": ["fixed_mounting"],
                "mating_interfaces": ["mounting_face"],
                "manufacturing_intent": ["milled_or_plate_like"],
                "semantic_assumptions": ["units_mm"],
            },
            "features": [
                {
                    "id": "棱柱主形体",
                    "kind": "base_body",
                    "method": "extrude",
                    "functional_role": "mounting_plate_body",
                    "feature_intent": "provide the primary mounting body and flat mounting faces",
                    "mating_interfaces": ["mounting_face"],
                    "modeling_method": {"command": "extrude", "reason": "test"},
                    "sketch_strategy": {"type": "centered_closed_rectangle"},
                    "parameters": {"length": 120.0, "width": 80.0, "thickness": 8.0},
                    "references": {"sketch_plane": "base"},
                },
                *features,
            ],
            "parameters": {
                "length": 120.0,
                "width": 80.0,
                "thickness": 8.0,
                "hole_diameter": 6.0,
                "holes": holes or [],
                "material": "6061铝",
            },
            "questions": [],
            "warnings": [],
            "missing_capabilities": [],
        }

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
        self.assertEqual(job.part.source_kind, "feature_plan_rotational")
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
        self.assertEqual(draft["strategy"]["questions"], draft["feature_plan"]["questions"])
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
        self.assertEqual(job.part.source_kind, "feature_plan_prismatic")
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
        self.assertEqual(countersink["parameters"]["clearance_diameter"], 6.6)
        self.assertEqual(countersink["parameters"]["clearance_class"], "normal")
        self.assertEqual(countersink["parameters"]["head_diameter"], 12.0)
        self.assertAlmostEqual(countersink["parameters"]["seat_angle"], 83.97, places=2)
        self.assertEqual(countersink["sketch_strategy"]["type"], "concentric_hole_seat_profile")

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("cut_extrude"), 2)
        self.assertEqual(operation_types.count("add_circle"), 2)
        through_hole_cut = [operation for operation in job.part.operations if operation.id == "拉伸切除_安装孔"][0]
        self.assertEqual(through_hole_cut.parameters["hole_metadata"]["holes"][0]["finished_diameter"], 6.6)
        countersink_cut = [operation for operation in job.part.operations if operation.id == "拉伸切除_沉头座"][0]
        self.assertAlmostEqual(countersink_cut.parameters["draft_angle"], 41.987, places=3)
        self.assertEqual(countersink_cut.parameters["hole_metadata"]["clearance_diameter"], 6.6)

    def test_counterbore_is_compiled_as_top_face_seat_cut(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长100宽60厚10，中心沉孔M6，沉孔直径12沉孔深3")
        self.assertTrue(draft["ready_for_execution"])
        counterbore = next(feature for feature in draft["feature_plan"]["features"] if feature["kind"] == "counterbore")
        self.assertEqual(counterbore["functional_role"], "counterbored_fastener_interface")
        self.assertEqual(counterbore["parameters"]["clearance_diameter"], 6.6)
        self.assertEqual(counterbore["parameters"]["head_diameter"], 12.0)
        self.assertEqual(counterbore["parameters"]["seat_depth"], 3.0)

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("cut_extrude"), 2)
        self.assertEqual(operation_types.count("start_sketch_on_face"), 2)
        through_hole_sketch = [operation for operation in job.part.operations if operation.id == "开始_孔切除草图"][0]
        self.assertEqual(through_hole_sketch.parameters["target"]["feature"], "拉伸_底板")
        through_hole_cut = [operation for operation in job.part.operations if operation.id == "拉伸切除_安装孔"][0]
        self.assertEqual(through_hole_cut.parameters["hole_metadata"]["holes"][0]["finished_diameter"], 6.6)
        counterbore_cut = [operation for operation in job.part.operations if operation.id == "拉伸切除_沉孔座"][0]
        self.assertEqual(counterbore_cut.parameters["hole_metadata"]["kind"], "counterbore")

    def test_explicit_hole_wizard_counterbore_and_countersink_compile_to_hole_wizard(self) -> None:
        cases = [
            ("用SolidWorks孔向导做一个安装板，长100宽60厚10，中心沉孔M6，沉孔直径12沉孔深3", "counterbore"),
            ("用SolidWorks孔向导做一个安装板，长100宽60厚10，中心沉头孔M6，沉头直径12沉头深3", "countersink"),
        ]
        for request, hole_type in cases:
            with self.subTest(hole_type=hole_type):
                draft = draft_primitive_job_from_natural_language(request)
                self.assertTrue(draft["ready_for_execution"])
                job = CadJob.from_dict(draft["job"])
                validate_job(job)
                operations = [operation for operation in job.part.operations if operation.type == "hole_wizard"]
                self.assertEqual(len(operations), 1)
                self.assertEqual(operations[0].parameters["hole_type"], hole_type)
                self.assertEqual(operations[0].parameters["size"], "M6")
                self.assertEqual(operations[0].parameters["locations"][0]["center"], [0.0, 0.0])

    def test_threaded_hole_is_compiled_as_tap_drill_with_metadata(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长100宽60厚10，中心M6螺纹孔深8")
        self.assertTrue(draft["ready_for_execution"])
        threaded_hole = next(feature for feature in draft["feature_plan"]["features"] if feature["kind"] == "threaded_hole")
        self.assertEqual(threaded_hole["parameters"]["thread_size"], 6.0)
        self.assertEqual(threaded_hole["parameters"]["thread_pitch"], 1.0)
        self.assertEqual(threaded_hole["parameters"]["tap_drill_diameter"], 5.0)
        self.assertEqual(threaded_hole["parameters"]["thread_depth"], 8.0)
        self.assertEqual(threaded_hole["parameters"]["drill_depth"], 10.1)

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        cut_operations = [operation for operation in job.part.operations if operation.type == "cut_extrude"]
        self.assertEqual(len(cut_operations), 1)
        self.assertEqual(cut_operations[0].parameters["thread_metadata"]["thread_size"], 6.0)
        self.assertEqual(cut_operations[0].parameters["thread_metadata"]["thread_pitch"], 1.0)
        self.assertEqual(cut_operations[0].parameters["thread_metadata"]["drill_depth"], 10.1)

    def test_explicit_hole_wizard_threaded_hole_compiles_to_hole_wizard_operation(self) -> None:
        draft = draft_primitive_job_from_natural_language("用SolidWorks孔向导做一个安装板，长100宽60厚10，中心M6螺纹孔深8")
        self.assertTrue(draft["ready_for_execution"])
        threaded_hole = next(feature for feature in draft["feature_plan"]["features"] if feature["kind"] == "threaded_hole")
        self.assertEqual(threaded_hole["method"], "hole_wizard")
        self.assertTrue(threaded_hole["parameters"]["use_hole_wizard"])
        self.assertEqual(threaded_hole["parameters"]["thread_modeling"], "solidworks_hole_wizard")

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("hole_wizard"), 1)
        self.assertEqual(operation_types.count("cut_extrude"), 0)
        hole_wizard = next(operation for operation in job.part.operations if operation.type == "hole_wizard")
        self.assertEqual(hole_wizard.parameters["hole_type"], "threaded")
        self.assertEqual(hole_wizard.parameters["size"], "M6")
        self.assertEqual(hole_wizard.parameters["locations"][0]["center"], [0.0, 0.0])
        self.assertEqual(hole_wizard.parameters["thread_metadata"]["thread_modeling"], "solidworks_hole_wizard")
        self.assertEqual(hole_wizard.parameters["hole_metadata"]["resolved_target"]["feature"], "拉伸_底板")

    def test_explicit_hole_wizard_four_corner_mounting_holes_compile_to_clearance_pattern(self) -> None:
        draft = draft_primitive_job_from_natural_language("用SolidWorks孔向导做一个安装板，长120宽80厚8，四角M8安装孔，孔边距15")
        self.assertTrue(draft["ready_for_execution"])
        hole_feature = next(
            feature
            for feature in draft["feature_plan"]["features"]
            if feature["kind"] in {"hole", "hole_pattern"}
        )
        self.assertEqual(hole_feature["method"], "hole_wizard")
        self.assertEqual(hole_feature["parameters"]["hole_type"], "clearance")
        self.assertEqual(hole_feature["parameters"]["size_label"], "M8")

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        hole_wizard = next(operation for operation in job.part.operations if operation.type == "hole_wizard")
        self.assertEqual(hole_wizard.parameters["hole_type"], "clearance")
        self.assertEqual(hole_wizard.parameters["size"], "M8")
        self.assertEqual(len(hole_wizard.parameters["locations"]), 4)

    def test_explicit_hole_wizard_threaded_hole_positions_compile(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "用SolidWorks孔向导做一个安装板，长120宽80厚8，两个M6螺纹孔深8位置分别为x20y10和x-30y15"
        )
        self.assertTrue(draft["ready_for_execution"])
        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        hole_wizard = next(operation for operation in job.part.operations if operation.type == "hole_wizard")
        self.assertEqual(hole_wizard.parameters["hole_type"], "threaded")
        self.assertEqual(len(hole_wizard.parameters["locations"]), 2)
        self.assertEqual(hole_wizard.parameters["locations"][0]["center"], [20.0, 10.0])

    def test_explicit_hole_wizard_counterbore_positions_compile(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "用SolidWorks孔向导做一个安装板，长120宽80厚8，两个沉孔M6，沉孔直径12沉孔深3，位置分别为x20y10和x-30y15"
        )
        self.assertTrue(draft["ready_for_execution"])
        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        hole_wizard = next(operation for operation in job.part.operations if operation.type == "hole_wizard")
        self.assertEqual(hole_wizard.parameters["hole_type"], "counterbore")
        self.assertEqual(len(hole_wizard.parameters["locations"]), 2)

    def test_explicit_non_symmetric_hole_positions_are_parsed(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "做一个安装板，长120宽80厚8，两个M6安装孔位置分别为x20y10和x-30y15，材料6061铝"
        )
        self.assertTrue(draft["ready_for_execution"])
        hole_feature = next(
            feature
            for feature in draft["feature_plan"]["features"]
            if feature["kind"] in {"hole", "hole_pattern"}
        )
        centers = [hole["center"] for hole in hole_feature["parameters"]["holes"]]
        self.assertEqual(centers, [[20.0, 10.0], [-30.0, 15.0]])

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        cut = next(operation for operation in job.part.operations if operation.type == "cut_extrude")
        self.assertEqual(len(cut.parameters["hole_metadata"]["holes"]), 2)

    def test_explicit_hole_positions_on_centerlines_use_axis_locator_relations(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "做一个安装板，长120宽80厚8，两个M6安装孔位置分别为x0y15和x20y0，材料6061铝"
        )
        self.assertTrue(draft["ready_for_execution"])
        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        operation_ids = {operation.id for operation in job.part.operations}
        self.assertIn("孔1中心竖直定位辅助线", operation_ids)
        self.assertIn("孔2中心水平定位辅助线", operation_ids)

    def test_resolver_inferrs_boss_top_face_for_hole_on_boss(self) -> None:
        plan = self._manual_prismatic_plan(
            "做一个安装板，长120宽80厚8，中间凸台直径20高6，凸台上加一个M6螺纹孔深8",
            features=[
                {
                    "id": "凸台",
                    "kind": "boss",
                    "method": "extrude",
                    "functional_role": "boss_or_standoff_interface",
                    "feature_intent": "provide a raised boss",
                    "mating_interfaces": ["boss_or_standoff_interface"],
                    "modeling_method": {"command": "extrude", "reason": "test"},
                    "sketch_strategy": {"type": "face_based_closed_profile"},
                    "parameters": {"diameter": 20.0, "height": 6.0, "center": [0.0, 0.0]},
                    "required_parameters": [],
                    "references": {"target_face": "base_top_face", "sketch_plane": "target_face"},
                },
                {
                    "id": "螺纹孔",
                    "kind": "threaded_hole",
                    "method": "cut_extrude",
                    "functional_role": "threaded_fastener_interface",
                    "feature_intent": "provide internal threads",
                    "mating_interfaces": ["threaded_fastener_interface"],
                    "modeling_method": {"command": "cut_extrude", "reason": "test"},
                    "sketch_strategy": {"type": "tap_drill_circle_layout"},
                    "parameters": {
                        "thread_size": 6.0,
                        "thread_standard": "ISO metric coarse",
                        "thread_pitch": 1.0,
                        "thread_depth": 8.0,
                        "drill_depth": 10.1,
                        "tap_drill_diameter": 5.0,
                        "thread_modeling": "tap_drill_geometry_with_thread_metadata",
                        "callout": "M6 x 1",
                    },
                    "required_parameters": [],
                    "references": {},
                },
            ],
            holes=[{"id": "孔1", "center": [0.0, 0.0], "diameter": 6.0}],
        )
        resolved = resolve_feature_plan_references(plan)
        hole_feature = resolved["features"][2]
        self.assertEqual(hole_feature["references"]["resolved_target"]["feature"], "拉伸_凸台1")
        self.assertEqual(hole_feature["references"]["target_inference_reason"], "single_boss_top_face_inferred_from_request")

        job = CadJob.from_dict(
            compile_feature_plan_to_primitive_job(
                resolved,
                job_id="boss-top-hole",
                part_name="凸台顶面孔测试",
                material="6061铝",
                export_formats=["svg"],
            )
        )
        validate_job(job)
        thread_cut = next(operation for operation in job.part.operations if operation.id == "拉伸切除_螺纹底孔")
        self.assertEqual(thread_cut.parameters["thread_metadata"]["resolved_target"]["feature"], "拉伸_凸台1")

    def test_resolver_inferrs_pocket_floor_face_for_hole_on_pocket_floor(self) -> None:
        plan = self._manual_prismatic_plan(
            "做一个安装板，长120宽80厚8，中间口袋长40宽20深3，口袋底部加定位孔",
            features=[
                {
                    "id": "口袋",
                    "kind": "slot_or_pocket",
                    "method": "cut_extrude",
                    "functional_role": "slot_or_pocket_cut",
                    "feature_intent": "provide a pocket",
                    "mating_interfaces": ["cut_feature_interface"],
                    "modeling_method": {"command": "cut_extrude", "reason": "test"},
                    "sketch_strategy": {"type": "closed_slot_or_pocket_profile"},
                    "parameters": {"length": 40.0, "width": 20.0, "depth": 3.0, "center": [0.0, 0.0]},
                    "required_parameters": [],
                    "references": {"target_face": "base_top_face", "sketch_plane": "target_face"},
                },
                {
                    "id": "定位孔",
                    "kind": "hole",
                    "method": "cut_extrude",
                    "functional_role": "locating_pin_interface",
                    "feature_intent": "locate mating parts with pin holes",
                    "mating_interfaces": ["locating_pin_interface"],
                    "modeling_method": {"command": "cut_extrude", "reason": "test"},
                    "sketch_strategy": {"type": "same_plane_circle_layout"},
                    "parameters": {"holes": [{"id": "孔1", "center": [0.0, 0.0], "diameter": 6.0}], "through": True},
                    "required_parameters": [],
                    "references": {},
                },
            ],
            holes=[{"id": "孔1", "center": [0.0, 0.0], "diameter": 6.0}],
        )
        resolved = resolve_feature_plan_references(plan)
        hole_feature = resolved["features"][2]
        self.assertEqual(hole_feature["references"]["resolved_target"]["feature"], "拉伸切除_口袋1")
        self.assertEqual(hole_feature["references"]["target_inference_reason"], "single_pocket_floor_face_inferred_from_request")

    def test_four_corner_holes_keep_inferred_base_face_metadata(self) -> None:
        draft = draft_primitive_job_from_natural_language(PLATE_REQUEST)
        hole_feature = draft["feature_plan"]["features"][1]
        self.assertEqual(hole_feature["references"]["resolved_target"]["feature"], "拉伸_底板")
        self.assertEqual(hole_feature["references"]["target_inference_reason"], "single_main_function_face_default")
        self.assertEqual(hole_feature["references"]["target_assumption"], "inferred_default_base_top_face")

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        through_hole_cut = next(operation for operation in job.part.operations if operation.id == "拉伸切除_安装孔")
        self.assertEqual(through_hole_cut.parameters["hole_metadata"]["resolved_target"]["feature"], "拉伸_底板")
        self.assertEqual(through_hole_cut.parameters["hole_metadata"]["target_assumption"], "inferred_default_base_top_face")

    def test_multiple_bosses_require_question_for_hole_on_boss(self) -> None:
        plan = self._manual_prismatic_plan(
            "做一个安装板，长120宽80厚8，两个凸台，凸台上加一个M6螺纹孔深8",
            features=[
                {
                    "id": "凸台1",
                    "kind": "boss",
                    "method": "extrude",
                    "functional_role": "boss_or_standoff_interface",
                    "feature_intent": "provide a raised boss",
                    "mating_interfaces": ["boss_or_standoff_interface"],
                    "modeling_method": {"command": "extrude", "reason": "test"},
                    "sketch_strategy": {"type": "face_based_closed_profile"},
                    "parameters": {"diameter": 20.0, "height": 6.0, "center": [-20.0, 0.0]},
                    "required_parameters": [],
                    "references": {"target_face": "base_top_face", "sketch_plane": "target_face"},
                },
                {
                    "id": "凸台2",
                    "kind": "boss",
                    "method": "extrude",
                    "functional_role": "boss_or_standoff_interface",
                    "feature_intent": "provide a raised boss",
                    "mating_interfaces": ["boss_or_standoff_interface"],
                    "modeling_method": {"command": "extrude", "reason": "test"},
                    "sketch_strategy": {"type": "face_based_closed_profile"},
                    "parameters": {"diameter": 20.0, "height": 6.0, "center": [20.0, 0.0]},
                    "required_parameters": [],
                    "references": {"target_face": "base_top_face", "sketch_plane": "target_face"},
                },
                {
                    "id": "螺纹孔",
                    "kind": "threaded_hole",
                    "method": "cut_extrude",
                    "functional_role": "threaded_fastener_interface",
                    "feature_intent": "provide internal threads",
                    "mating_interfaces": ["threaded_fastener_interface"],
                    "modeling_method": {"command": "cut_extrude", "reason": "test"},
                    "sketch_strategy": {"type": "tap_drill_circle_layout"},
                    "parameters": {
                        "thread_size": 6.0,
                        "thread_standard": "ISO metric coarse",
                        "thread_pitch": 1.0,
                        "thread_depth": 8.0,
                        "drill_depth": 10.1,
                        "tap_drill_diameter": 5.0,
                        "thread_modeling": "tap_drill_geometry_with_thread_metadata",
                        "callout": "M6 x 1",
                    },
                    "required_parameters": [],
                    "references": {},
                },
            ],
            holes=[{"id": "孔1", "center": [0.0, 0.0], "diameter": 6.0}],
        )
        resolved = resolve_feature_plan_references(plan)
        self.assertTrue(any("多个凸台" in question for question in resolved["questions"]))

    def test_compiled_features_preserve_resolved_targets(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "做一个安装板，长120宽80厚8，中间口袋长40宽20深3，中间凸台直径20高6，加强筋长50厚5高12"
        )
        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        pocket_cut = next(operation for operation in job.part.operations if operation.id == "拉伸切除_口袋1")
        boss_extrude = next(operation for operation in job.part.operations if operation.id == "拉伸_凸台2")
        rib_extrude = next(operation for operation in job.part.operations if operation.id == "拉伸_加强筋1")
        self.assertIn("resolved_target", pocket_cut.parameters["feature_metadata"])
        self.assertIn("resolved_target", boss_extrude.parameters["feature_metadata"])
        self.assertIn("resolved_target", rib_extrude.parameters["feature_metadata"])

    def test_generic_hole_role_triggers_clarification_question(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长120宽80厚8，一个孔直径8位置x20y10")
        self.assertFalse(draft["ready_for_execution"])
        self.assertIn("工程作用", "".join(draft["questions"]))

    def test_locating_hole_requires_fit_information(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长120宽80厚8，一个定位孔直径6位置x20y10")
        self.assertFalse(draft["ready_for_execution"])
        self.assertIn("公差", "".join(draft["questions"]))

    def test_bearing_hole_requires_fit_information(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长120宽80厚8，一个轴承孔直径32位置x0y0")
        self.assertFalse(draft["ready_for_execution"])
        self.assertIn("轴承孔", "".join(draft["questions"]))

    def test_summary_contains_engineering_hole_callouts(self) -> None:
        draft = draft_primitive_job_from_natural_language("做一个安装板，长120宽80厚8，中心M6螺纹孔深8")
        job = CadJob.from_dict(draft["job"])
        output_root = SERVER_ROOT / "tests" / ".tmp" / "preview-job"
        if output_root.exists():
            shutil.rmtree(output_root)
        try:
            summary = run_job(job, output_root=output_root, backend="preview")
            callouts = summary["metadata"]["engineering_hole_callouts"]
            self.assertEqual(len(callouts), 1)
            self.assertEqual(callouts[0]["thread_callout"], "M6 x 1")
            self.assertEqual(callouts[0]["thread_modeling"], "tap_drill_geometry_with_thread_metadata")
            annotation_plan = summary["metadata"]["drawing_annotation_plan"]
            self.assertTrue(annotation_plan["ready_for_lightweight_drawing"])
            self.assertEqual(annotation_plan["hole_annotations"][0]["callout"], "M6 x 1")
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

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

    def test_pocket_boss_and_rib_preserve_position_and_draft_metadata(self) -> None:
        draft = draft_primitive_job_from_natural_language(
            "做一个安装板，长120宽80厚8，口袋位置x15y-10长40宽20深3拔模角2，凸台位置x20y10直径20高6拔模角1，加强筋位置x-20y0长50厚5高12拔模角1.5"
        )
        self.assertTrue(draft["ready_for_execution"])
        features = draft["feature_plan"]["features"]
        pocket = next(feature for feature in features if feature["kind"] == "slot_or_pocket")
        boss = next(feature for feature in features if feature["kind"] == "boss")
        rib = next(feature for feature in features if feature["kind"] == "rib")
        self.assertEqual(pocket["parameters"]["center"], [15.0, -10.0])
        self.assertEqual(pocket["parameters"]["draft_angle"], 2.0)
        self.assertEqual(boss["parameters"]["center"], [20.0, 10.0])
        self.assertEqual(boss["parameters"]["draft_angle"], 1.0)
        self.assertEqual(rib["parameters"]["center"], [-20.0, 0.0])
        self.assertEqual(rib["parameters"]["draft_angle"], 1.5)

        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        pocket_cut = [operation for operation in job.part.operations if operation.id == "拉伸切除_口袋1"][0]
        boss_extrude = [operation for operation in job.part.operations if operation.id == "拉伸_凸台2"][0]
        rib_extrude = [operation for operation in job.part.operations if operation.id == "拉伸_加强筋1"][0]
        rib_dimensions = [operation for operation in job.part.operations if operation.id == "加强筋尺寸1"][0]
        self.assertEqual(pocket_cut.parameters["draft_angle"], 2.0)
        self.assertEqual(pocket_cut.parameters["feature_metadata"]["center"], [15.0, -10.0])
        self.assertEqual(boss_extrude.parameters["draft_angle"], 1.0)
        self.assertEqual(boss_extrude.parameters["feature_metadata"]["center"], [20.0, 10.0])
        self.assertEqual(rib_extrude.parameters["draft_angle"], 1.5)
        self.assertEqual(rib_extrude.parameters["feature_metadata"]["center"], [-20.0, 0.0])
        self.assertEqual(pocket_cut.parameters["feature_metadata"]["resolved_target"]["feature"], "拉伸_底板")
        self.assertEqual(boss_extrude.parameters["feature_metadata"]["resolved_target"]["feature"], "拉伸_底板")
        self.assertEqual(rib_extrude.parameters["feature_metadata"]["resolved_target"]["feature"], "拉伸_底板")
        rib_dimension_ids = {dimension["id"] for dimension in rib_dimensions.parameters["dimensions"]}
        self.assertIn("加强筋1_x定位", rib_dimension_ids)
        operation_ids = {operation.id for operation in job.part.operations}
        self.assertIn("加强筋1中心水平定位辅助线", operation_ids)

    def test_feature_plan_compiler_preserves_explicit_face_targets(self) -> None:
        target = {
            "type": "body_face",
            "feature": "拉伸_二级台阶",
            "normal": [0, 0, 1],
            "position": "max",
            "area": "largest",
        }
        feature_plan = {
            "version": "feature_plan.v1",
            "units": "mm",
            "dominant_geometry": "prismatic",
            "engineering_context": {},
            "parameters": {"length": 120, "width": 80, "thickness": 8},
            "features": [
                {
                    "id": "二级台阶口袋",
                    "kind": "slot_or_pocket",
                    "method": "cut_extrude",
                    "functional_role": "clearance_cut_or_relief_slot",
                    "parameters": {"length": 30, "width": 16, "depth": 3, "center": [10, 0]},
                    "required_parameters": [],
                    "references": {"target_face": target},
                }
            ],
            "questions": [],
            "missing_capabilities": [],
        }
        job_data = compile_feature_plan_to_primitive_job(
            feature_plan,
            job_id="explicit-face-target",
            part_name="显式面引用测试",
            material="6061铝",
            export_formats=["step"],
        )
        job = CadJob.from_dict(job_data)
        validate_job(job)
        pocket_start = [operation for operation in job.part.operations if operation.id == "开始_口袋切除草图1"][0]
        pocket_cut = [operation for operation in job.part.operations if operation.id == "拉伸切除_口袋1"][0]
        self.assertEqual(pocket_start.parameters["target"], target)
        self.assertEqual(pocket_cut.parameters["feature_metadata"]["target_face"], target)

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
        self.assertEqual(draft["strategy"]["questions"], draft["feature_plan"]["questions"])
        self.assertEqual(draft["feature_plan"]["version"], "feature_plan.v1")
        self.assertTrue(
            any(item["feature"] == "unsupported_feature_plan_family" for item in draft["feature_plan"]["missing_capabilities"])
        )

    def test_context_rebuild_appends_threaded_hole_on_existing_boss(self) -> None:
        base_request = "做一个安装板，长120宽80厚8，中间凸台直径20高6，材料6061铝"
        base_draft = draft_primitive_job_from_natural_language(base_request)
        self.assertTrue(base_draft["ready_for_execution"])
        base_job = CadJob.from_dict(base_draft["job"])
        context = build_part_context(
            job=base_job,
            feature_plan=base_draft["feature_plan"],
            request=base_request,
            strategy=base_draft["strategy"],
        )
        output_root = SERVER_ROOT / "tests" / ".tmp" / "part-context-boss-hole"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            context_path = write_part_context(output_root / "part_context.json", context)
            draft = draft_primitive_job_from_natural_language(
                "在凸台上加一个中心M6螺纹孔深8",
                context_file=context_path,
            )
            self.assertTrue(draft["ready_for_execution"])
            self.assertEqual(draft["parsed_parameters"]["length"], 120.0)
            self.assertEqual(draft["parsed_parameters"]["width"], 80.0)
            self.assertEqual(draft["parsed_parameters"]["thickness"], 8.0)
            requested_feature_plan = draft["requested_feature_plan"]
            self.assertEqual([feature["kind"] for feature in requested_feature_plan["features"]], ["base_body", "threaded_hole"])
            self.assertEqual(draft["edit_plan"]["mode"], "rebuild_from_context")
            self.assertEqual(draft["edit_plan"]["output_revision"]["revision_index"], 2)
            append_actions = [action for action in draft["edit_plan"]["actions"] if action["action"] == "append_feature"]
            self.assertTrue(append_actions)
            self.assertEqual(append_actions[0]["target_scope"], "feature_append")
            self.assertEqual(append_actions[0]["feature_selector"]["kind"], "threaded_hole")
            self.assertEqual(append_actions[0]["host_reference"]["feature"], "拉伸_凸台1")
            self.assertEqual(append_actions[0]["host_feature_selector"]["kind"], "boss")
            self.assertEqual(append_actions[0]["selector_strategy"], "new_feature_append")
            self.assertTrue(any(selector["parameter_path"] == ["thread_size"] for selector in append_actions[0]["parameter_selectors"]))
            local_rebuild_actions = [action for action in draft["edit_plan"]["actions"] if action["action"] == "local_rebuild"]
            self.assertTrue(local_rebuild_actions)
            self.assertEqual(local_rebuild_actions[0]["boundary"]["executor_scope"], "recompile_feature_plan_then_rebuild_revision")
            self.assertEqual(local_rebuild_actions[0]["boundary"]["rebuild_scope"], "affected_feature_dependency_chain")
            self.assertTrue(local_rebuild_actions[0]["preflight"]["requires_feature_plan_recompile"])
            self.assertTrue(local_rebuild_actions[0]["boundary"]["dependency_summary"]["affects_host_features"])
            self.assertTrue("same_plane_derived_feature_selectors" in local_rebuild_actions[0]["boundary"]["dependency_summary"])
            self.assertFalse(local_rebuild_actions[0]["boundary"]["dependency_summary"]["affects_downstream_subtractive_features"])
            self.assertFalse(local_rebuild_actions[0]["boundary"]["dependency_summary"]["affects_base_body"])
            self.assertEqual(local_rebuild_actions[0]["boundary"]["dependency_summary"]["rebuild_entry_nodes"][0]["kind"], "threaded_hole")
            self.assertEqual(draft["edit_dsl"]["version"], "edit_part.v1")
            self.assertTrue(any(operation["type"] == "local_rebuild" for operation in draft["edit_dsl"]["operations"]))
            feature_plan = draft["feature_plan"]
            self.assertEqual(sum(1 for feature in feature_plan["features"] if feature["kind"] == "base_body"), 1)
            self.assertEqual(sum(1 for feature in feature_plan["features"] if feature["kind"] == "boss"), 1)
            hole_feature = next(feature for feature in feature_plan["features"] if feature["kind"] == "threaded_hole")
            self.assertEqual(hole_feature["references"]["resolved_target"]["feature"], "拉伸_凸台1")
            self.assertEqual(hole_feature["references"]["target_inference_reason"], "structured_target_semantic_reference")
            self.assertIn("rebuild_from_existing_part_context", feature_plan["engineering_context"]["semantic_assumptions"])

            job = CadJob.from_dict(draft["job"])
            validate_job(job)
            operation_ids = {operation.id for operation in job.part.operations}
            self.assertIn("拉伸_凸台1", operation_ids)
            threaded_cut = next(operation for operation in job.part.operations if operation.id == "拉伸切除_螺纹底孔")
            self.assertEqual(threaded_cut.parameters["thread_metadata"]["resolved_target"]["feature"], "拉伸_凸台1")
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_edit_dsl_explicitly_applies_requested_feature_plan_to_existing_context(self) -> None:
        base_request = "做一个安装板，长120宽80厚8，中间凸台直径20高6，材料6061铝"
        base_draft = draft_primitive_job_from_natural_language(base_request)
        context = build_part_context(
            job=CadJob.from_dict(base_draft["job"]),
            feature_plan=base_draft["feature_plan"],
            request=base_request,
            strategy=base_draft["strategy"],
        )
        output_root = SERVER_ROOT / "tests" / ".tmp" / "explicit-edit-apply"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            context_path = write_part_context(output_root / "part_context.json", context)
            draft = draft_primitive_job_from_natural_language(
                "在凸台上加一个中心M6螺纹孔深8",
                context_file=context_path,
            )
            applied = apply_edit_dsl_to_feature_plan(
                edit_dsl=draft["edit_dsl"],
                existing_feature_plan=context["feature_plan"],
                requested_feature_plan=draft["requested_feature_plan"],
            )
            self.assertEqual([feature["kind"] for feature in draft["requested_feature_plan"]["features"]], ["base_body", "threaded_hole"])
            self.assertEqual(sum(1 for feature in applied["features"] if feature["kind"] == "boss"), 1)
            self.assertEqual(sum(1 for feature in applied["features"] if feature["kind"] == "threaded_hole"), 1)
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_local_rebuild_dependency_summary_can_report_same_plane_derived_features(self) -> None:
        base_request = "做一个安装板，长120宽80厚8，中间凸台直径20高6，凸台上加一个中心M6螺纹孔深8，材料6061铝"
        base_draft = draft_primitive_job_from_natural_language(base_request)
        context = build_part_context(
            job=CadJob.from_dict(base_draft["job"]),
            feature_plan=base_draft["feature_plan"],
            request=base_request,
            strategy=base_draft["strategy"],
        )
        output_root = SERVER_ROOT / "tests" / ".tmp" / "same-plane-derived"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            context_path = write_part_context(output_root / "part_context.json", context)
            draft = draft_primitive_job_from_natural_language(
                "在凸台上加一个中心沉孔M6，沉孔直径12沉孔深3",
                context_file=context_path,
            )
            self.assertTrue(draft["ready_for_execution"])
            local_rebuild = next(action for action in draft["edit_plan"]["actions"] if action["action"] == "local_rebuild")
            summary = local_rebuild["boundary"]["dependency_summary"]
            self.assertTrue(summary["affects_same_plane_derived_features"])
            self.assertTrue(any(item["kind"] == "threaded_hole" for item in summary["same_plane_derived_feature_selectors"]))
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_context_feature_plan_draft_uses_existing_part_context(self) -> None:
        base_request = "做一个安装板，长120宽80厚8，中间口袋长40宽20深3，材料6061铝"
        base_draft = draft_primitive_job_from_natural_language(base_request)
        base_job = CadJob.from_dict(base_draft["job"])
        context = build_part_context(
            job=base_job,
            feature_plan=base_draft["feature_plan"],
            request=base_request,
            strategy=base_draft["strategy"],
        )
        output_root = SERVER_ROOT / "tests" / ".tmp" / "part-context-pocket-hole"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            context_path = write_part_context(output_root / "part_context.json", context)
            result = draft_feature_plan_from_natural_language(
                "在口袋底部加一个中心孔直径6",
                context_file=context_path,
            )
            self.assertTrue(result["ready_for_compilation"])
            hole_feature = next(feature for feature in result["feature_plan"]["features"] if feature["kind"] == "hole")
            self.assertEqual(hole_feature["references"]["resolved_target"]["feature"], "拉伸切除_口袋1")
            self.assertEqual(hole_feature["references"]["target_inference_reason"], "structured_target_semantic_reference")
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_resolver_can_use_structured_target_semantic_without_request_keyword(self) -> None:
        plan = self._manual_prismatic_plan(
            "追加一个孔",
            features=[
                {
                    "id": "凸台",
                    "kind": "boss",
                    "method": "extrude",
                    "functional_role": "boss_or_standoff_interface",
                    "feature_intent": "provide a raised boss",
                    "mating_interfaces": ["boss_or_standoff_interface"],
                    "modeling_method": {"command": "extrude", "reason": "test"},
                    "sketch_strategy": {"type": "face_based_closed_profile"},
                    "parameters": {"diameter": 20.0, "height": 6.0, "center": [0.0, 0.0]},
                    "required_parameters": [],
                    "references": {"target_face": "base_top_face", "sketch_plane": "target_face"},
                },
                {
                    "id": "追加孔",
                    "kind": "threaded_hole",
                    "method": "cut_extrude",
                    "functional_role": "threaded_fastener_interface",
                    "feature_intent": "provide internal threads",
                    "mating_interfaces": ["threaded_fastener_interface"],
                    "modeling_method": {"command": "cut_extrude", "reason": "test"},
                    "sketch_strategy": {"type": "tap_drill_circle_layout"},
                    "parameters": {
                        "thread_size": 6.0,
                        "thread_standard": "ISO metric coarse",
                        "thread_pitch": 1.0,
                        "thread_depth": 8.0,
                        "drill_depth": 10.1,
                        "tap_drill_diameter": 5.0,
                    },
                    "required_parameters": [],
                    "references": {
                        "target_semantic": "boss_top_face",
                        "host_feature_selector": {"kind": "boss", "functional_role": "boss_or_standoff_interface"},
                    },
                },
            ],
        )
        resolved = resolve_feature_plan_references(plan)
        hole_feature = next(feature for feature in resolved["features"] if feature["kind"] == "threaded_hole")
        self.assertEqual(hole_feature["references"]["resolved_target"]["feature"], "拉伸_凸台1")
        self.assertEqual(hole_feature["references"]["target_inference_reason"], "structured_target_semantic_reference")

    def test_resolver_can_use_host_feature_selector_without_target_semantic(self) -> None:
        plan = self._manual_prismatic_plan(
            "追加一个孔",
            features=[
                {
                    "id": "凸台",
                    "kind": "boss",
                    "method": "extrude",
                    "functional_role": "boss_or_standoff_interface",
                    "feature_intent": "provide a raised boss",
                    "mating_interfaces": ["boss_or_standoff_interface"],
                    "modeling_method": {"command": "extrude", "reason": "test"},
                    "sketch_strategy": {"type": "face_based_closed_profile"},
                    "parameters": {"diameter": 20.0, "height": 6.0, "center": [0.0, 0.0]},
                    "required_parameters": [],
                    "references": {"target_face": "base_top_face", "sketch_plane": "target_face"},
                },
                {
                    "id": "追加孔",
                    "kind": "threaded_hole",
                    "method": "cut_extrude",
                    "functional_role": "threaded_fastener_interface",
                    "feature_intent": "provide internal threads",
                    "mating_interfaces": ["threaded_fastener_interface"],
                    "modeling_method": {"command": "cut_extrude", "reason": "test"},
                    "sketch_strategy": {"type": "tap_drill_circle_layout"},
                    "parameters": {
                        "thread_size": 6.0,
                        "thread_standard": "ISO metric coarse",
                        "thread_pitch": 1.0,
                        "thread_depth": 8.0,
                        "drill_depth": 10.1,
                        "tap_drill_diameter": 5.0,
                    },
                    "required_parameters": [],
                    "references": {
                        "host_feature_selector": {"kind": "boss", "functional_role": "boss_or_standoff_interface"},
                    },
                },
            ],
        )
        resolved = resolve_feature_plan_references(plan)
        hole_feature = next(feature for feature in resolved["features"] if feature["kind"] == "threaded_hole")
        self.assertEqual(hole_feature["references"]["resolved_target"]["feature"], "拉伸_凸台1")
        self.assertEqual(hole_feature["references"]["target_inference_reason"], "structured_host_feature_selector_reference")

    def test_context_rebuild_can_update_prismatic_base_dimensions(self) -> None:
        base_request = "做一个安装板，长120宽80厚8，中间凸台直径20高6，材料6061铝"
        base_draft = draft_primitive_job_from_natural_language(base_request)
        context = build_part_context(
            job=CadJob.from_dict(base_draft["job"]),
            feature_plan=base_draft["feature_plan"],
            request=base_request,
            strategy=base_draft["strategy"],
        )
        output_root = SERVER_ROOT / "tests" / ".tmp" / "part-context-dimension-update"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            context_path = write_part_context(output_root / "part_context.json", context)
            draft = draft_primitive_job_from_natural_language(
                "把长度改成140，厚度改成10",
                context_file=context_path,
            )
            self.assertTrue(draft["ready_for_execution"])
            update_actions = [
                action
                for action in draft["edit_plan"]["actions"]
                if action["action"] == "update_parameters" and action["target_scope"] == "part"
            ]
            self.assertTrue(update_actions)
            self.assertEqual(update_actions[0]["parameters"]["length"], 140.0)
            self.assertEqual(update_actions[0]["parameters"]["thickness"], 10.0)
            self.assertTrue(any(selector["parameter_path"] == ["length"] for selector in update_actions[0]["parameter_selectors"]))
            feature_update_actions = [
                action
                for action in draft["edit_plan"]["actions"]
                if action["action"] == "update_parameters" and action["target_scope"] == "feature"
            ]
            self.assertTrue(feature_update_actions)
            self.assertEqual(feature_update_actions[0]["target_feature_selector"]["kind"], "base_body")
            self.assertEqual(feature_update_actions[0]["selector_strategy"], "kind_and_functional_role")
            feature_plan = draft["feature_plan"]
            base_body = next(feature for feature in feature_plan["features"] if feature["kind"] == "base_body")
            self.assertEqual(base_body["parameters"]["length"], 140.0)
            self.assertEqual(base_body["parameters"]["thickness"], 10.0)

            job = CadJob.from_dict(draft["job"])
            validate_job(job)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 140.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 10.0)
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_context_rebuild_can_update_rotational_base_and_bore_dimensions(self) -> None:
        base_request = "做一个阶梯轴，总长120，最大直径40，中心孔直径10贯穿，材料45钢"
        base_draft = draft_primitive_job_from_natural_language(base_request)
        context = build_part_context(
            job=CadJob.from_dict(base_draft["job"]),
            feature_plan=base_draft["feature_plan"],
            request=base_request,
            strategy=base_draft["strategy"],
        )
        output_root = SERVER_ROOT / "tests" / ".tmp" / "part-context-rotational-update"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            context_path = write_part_context(output_root / "part_context.json", context)
            draft = draft_primitive_job_from_natural_language(
                "把总长改成130，中心孔直径改成12",
                context_file=context_path,
            )
            self.assertTrue(draft["ready_for_execution"])
            self.assertTrue(
                any(
                    action["action"] == "update_parameters" and action["target_scope"] == "part"
                    for action in draft["edit_plan"]["actions"]
                )
            )
            feature_plan = draft["feature_plan"]
            base_body = next(feature for feature in feature_plan["features"] if feature["kind"] == "base_body")
            center_bore = next(feature for feature in feature_plan["features"] if feature["functional_role"] == "center_bore_or_clearance_passage")
            self.assertEqual(base_body["parameters"]["total_length"], 130.0)
            self.assertEqual(center_bore["parameters"]["diameter"], 12.0)

            job = CadJob.from_dict(draft["job"])
            validate_job(job)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 130.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 40.0)
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_context_run_writes_revision_metadata_into_part_context(self) -> None:
        base_request = "做一个安装板，长120宽80厚8，中间凸台直径20高6，材料6061铝"
        base_draft = draft_primitive_job_from_natural_language(base_request)
        context = build_part_context(
            job=CadJob.from_dict(base_draft["job"]),
            feature_plan=base_draft["feature_plan"],
            request=base_request,
            strategy=base_draft["strategy"],
        )
        output_root = SERVER_ROOT / "tests" / ".tmp" / "part-context-revision-meta"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            context_path = write_part_context(output_root / "part_context.json", context)
            draft = draft_primitive_job_from_natural_language(
                "在凸台上加一个中心M6螺纹孔深8",
                context_file=context_path,
            )
            summary = run_job(CadJob.from_dict(draft["job"]), output_root=output_root, backend="preview")
            rebuilt_context = build_part_context(
                job=CadJob.from_dict(draft["job"]),
                feature_plan=draft["feature_plan"],
                request="在凸台上加一个中心M6螺纹孔深8",
                strategy=draft["strategy"],
                summary=summary,
                existing_part_context=context,
                edit_plan=draft["edit_plan"],
            )
            self.assertEqual(rebuilt_context["revision_index"], 2)
            self.assertEqual(rebuilt_context["parent_job_id"], context["job_id"])
            self.assertIn(context["job_id"], rebuilt_context["lineage"])
            self.assertEqual(rebuilt_context["edit_plan"]["output_revision"]["revision_index"], 2)
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_edit_plan_uses_replace_feature_for_family_change(self) -> None:
        existing_context = {
            "job_id": "demo-r1",
            "part_name": "demo",
            "revision_index": 1,
            "dominant_geometry": "prismatic",
            "feature_plan": {
                "features": [
                    {
                        "id": "旧接口区",
                        "kind": "boss",
                        "functional_role": "mounting_interface",
                        "parameters": {"diameter": 20.0, "height": 6.0},
                    }
                ],
                "parameters": {},
            },
        }
        updated_plan = {
            "request": "把原来的凸台改成异形过渡接口",
            "features": [
                {
                    "id": "新接口区",
                    "kind": "loft_transition",
                    "functional_role": "mounting_interface",
                    "parameters": {"profiles": ["a", "b"]},
                    "references": {"target_face": "base_top_face"},
                }
            ],
            "questions": [],
            "warnings": [],
        }
        edit_plan = build_edit_plan(
            request=updated_plan["request"],
            feature_plan=updated_plan,
            existing_part_context=existing_context,
        )
        replace_actions = [action for action in edit_plan["actions"] if action["action"] == "replace_feature"]
        self.assertTrue(replace_actions)
        self.assertEqual(replace_actions[0]["target_feature_selector"]["kind"], "boss")
        self.assertEqual(replace_actions[0]["replacement_feature"]["kind"], "loft_transition")
        self.assertEqual(replace_actions[0]["selector_strategy"], "functional_role_only")
        self.assertGreaterEqual(replace_actions[0]["match_confidence"], 0.8)
        self.assertEqual(replace_actions[0]["replacement_compatibility"]["classification"], "cross_modeling_family_replacement")
        self.assertTrue(replace_actions[0]["replacement_compatibility"]["requires_manual_confirmation"])
        self.assertEqual(replace_actions[0]["replacement_compatibility"]["transition_support"], "unsupported_in_current_compiler")
        self.assertEqual(replace_actions[0]["boundary"]["edit_scope"], "single_feature_replacement")
        self.assertTrue(replace_actions[0]["preflight"]["requires_unique_target_feature_selector"])
        self.assertTrue(replace_actions[0]["boundary"]["dependency_summary"]["affects_host_features"])
        self.assertTrue("same_plane_derived_feature_selectors" in replace_actions[0]["boundary"]["dependency_summary"])

    def test_edit_plan_marks_same_family_supported_transition(self) -> None:
        existing_context = {
            "job_id": "demo-r1",
            "part_name": "demo",
            "revision_index": 1,
            "dominant_geometry": "prismatic",
            "feature_plan": {
                "features": [
                    {
                        "id": "旧减料",
                        "kind": "slot_or_pocket",
                        "method": "cut_extrude",
                        "functional_role": "clearance_cut_or_relief_slot",
                        "parameters": {"length": 20.0, "width": 10.0, "depth": 3.0},
                    }
                ],
                "parameters": {},
            },
        }
        updated_plan = {
            "request": "把原来的避让口袋改成长圆槽",
            "features": [
                {
                    "id": "新减料",
                    "kind": "obround_slot",
                    "method": "cut_extrude",
                    "functional_role": "clearance_cut_or_relief_slot",
                    "parameters": {"length": 24.0, "width": 8.0},
                    "references": {"target_face": "base_top_face"},
                }
            ],
            "questions": [],
            "warnings": [],
        }
        edit_plan = build_edit_plan(
            request=updated_plan["request"],
            feature_plan=updated_plan,
            existing_part_context=existing_context,
        )
        replace_action = next(action for action in edit_plan["actions"] if action["action"] == "replace_feature")
        compatibility = replace_action["replacement_compatibility"]
        self.assertEqual(compatibility["classification"], "same_manufacturing_semantic_replacement")
        self.assertEqual(compatibility["transition_support"], "supported_with_manual_confirmation")
        self.assertTrue(compatibility["requires_manual_confirmation"])
        self.assertTrue(replace_action["preflight"]["supported_transition_for_execution"])
        self.assertEqual(compatibility["previous_compile_signature"], ["slot_or_pocket", "cut_extrude"])
        self.assertEqual(compatibility["replacement_compile_signature"], ["obround_slot", "cut_extrude"])

    def test_validate_edit_dsl_rejects_low_confidence_replace_feature(self) -> None:
        edit_dsl = {
            "version": "edit_part.v1",
            "mode": "rebuild_from_context",
            "request": "replace",
            "source_context": {"job_id": "demo"},
            "operations": [
                {
                    "type": "replace_feature",
                    "target_scope": "feature",
                    "target_feature_selector": {"kind": "boss"},
                    "replacement_feature": {"kind": "loft_transition"},
                    "match_confidence": 0.4,
                    "replacement_compatibility": {
                        "classification": "cross_modeling_family_replacement",
                        "requires_manual_confirmation": True,
                    },
                    "boundary": {
                        "edit_scope": "single_feature_replacement",
                        "dependency_summary": {
                            "affects_host_features": True,
                            "host_feature_selectors": [{"kind": "boss"}],
                            "affects_same_plane_derived_features": False,
                            "same_plane_derived_feature_selectors": [],
                            "affects_downstream_subtractive_features": False,
                            "downstream_feature_selectors": [],
                            "affects_base_body": False,
                            "rebuild_entry_nodes": [{"kind": "boss"}],
                        },
                    },
                    "preflight": {
                        "requires_unique_target_feature_selector": True,
                        "requires_compile_ready_replacement_feature": True,
                        "requires_supported_replacement_family": True,
                        "minimum_match_confidence": 0.75,
                        "current_match_confidence": 0.4,
                    },
                },
                {"type": "rebuild_revision", "revision_index": 2},
            ],
            "output_revision": {"revision_index": 2},
        }
        with self.assertRaises(ValueError):
            validate_edit_dsl(edit_dsl)

    def test_validate_edit_dsl_rejects_unsupported_replace_transition(self) -> None:
        edit_dsl = {
            "version": "edit_part.v1",
            "mode": "rebuild_from_context",
            "request": "replace",
            "source_context": {"job_id": "demo"},
            "operations": [
                {
                    "type": "replace_feature",
                    "target_scope": "feature",
                    "target_feature_selector": {"kind": "boss"},
                    "replacement_feature": {"kind": "loft_transition"},
                    "match_confidence": 0.95,
                    "replacement_compatibility": {
                        "classification": "cross_modeling_family_replacement",
                        "previous_supported_family": "prismatic_additive",
                        "replacement_supported_family": "unsupported",
                        "transition_support": "unsupported_in_current_compiler",
                        "requires_manual_confirmation": True,
                    },
                    "boundary": {
                        "edit_scope": "single_feature_replacement",
                        "dependency_summary": {
                            "affects_host_features": True,
                            "host_feature_selectors": [{"kind": "boss"}],
                            "affects_same_plane_derived_features": False,
                            "same_plane_derived_feature_selectors": [],
                            "affects_downstream_subtractive_features": False,
                            "downstream_feature_selectors": [],
                            "affects_base_body": False,
                            "rebuild_entry_nodes": [{"kind": "boss"}],
                        },
                    },
                    "preflight": {
                        "requires_unique_target_feature_selector": True,
                        "requires_compile_ready_replacement_feature": True,
                        "requires_supported_replacement_family": False,
                        "supported_transition_for_execution": False,
                        "requires_revision_output": True,
                        "minimum_match_confidence": 0.75,
                        "current_match_confidence": 0.95,
                    },
                },
                {"type": "rebuild_revision", "revision_index": 2},
            ],
            "output_revision": {"revision_index": 2},
        }
        with self.assertRaises(ValueError):
            validate_edit_dsl(edit_dsl)

    def test_validate_edit_dsl_requires_local_rebuild_boundary(self) -> None:
        edit_dsl = {
            "version": "edit_part.v1",
            "mode": "rebuild_from_context",
            "request": "rebuild",
            "source_context": {"job_id": "demo"},
            "operations": [
                {
                    "type": "local_rebuild",
                    "target_scope": "dependency_chain",
                    "affected_feature_selectors": [{"id": "孔1", "kind": "threaded_hole"}],
                    "boundary": {
                        "rebuild_scope": "affected_feature_dependency_chain",
                        "dependency_summary": {
                            "affects_host_features": True,
                            "host_feature_selectors": [{"kind": "boss"}],
                            "affects_same_plane_derived_features": False,
                            "same_plane_derived_feature_selectors": [],
                            "affects_downstream_subtractive_features": False,
                            "downstream_feature_selectors": [],
                            "affects_base_body": False,
                            "rebuild_entry_nodes": [{"kind": "threaded_hole"}],
                        },
                    },
                    "preflight": {
                        "requires_affected_feature_selectors": True,
                        "affected_feature_count": 1,
                    },
                },
                {"type": "rebuild_revision", "revision_index": 2},
            ],
            "output_revision": {"revision_index": 2},
        }
        with self.assertRaises(ValueError):
            validate_edit_dsl(edit_dsl)


if __name__ == "__main__":
    unittest.main()
