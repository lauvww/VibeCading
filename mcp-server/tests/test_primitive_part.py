from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.dsl import CadJob
from core.job_runner import run_job
from core.validators import validate_job


class PrimitivePartTests(unittest.TestCase):
    def test_multi_feature_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "multi_feature_test_part.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        self.assertEqual(job.kind, "primitive_part")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("extrude"), 4)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 4)

    def test_preview_backend_generates_multi_feature_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "multi-feature-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "multi_feature_test_part.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 36)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("extrude"), 4)
            self.assertEqual(summary["metadata"]["hole_count"], 4)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_cut_extrude_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "multi_feature_cut_test_part.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("extrude"), 3)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 4)

    def test_preview_backend_generates_cut_extrude_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "multi-feature-cut-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "multi_feature_cut_test_part.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 34)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_extrude"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("extrude"), 3)
            self.assertEqual(summary["metadata"]["hole_count"], 4)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_complex_fixture_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "complex_fixture_plate.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("extrude"), 4)
        self.assertEqual(operation_types.count("cut_extrude"), 2)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 6)

    def test_preview_backend_generates_complex_fixture_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "complex-fixture-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "complex_fixture_plate.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 56)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("extrude"), 4)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_extrude"), 2)
            self.assertEqual(summary["metadata"]["hole_count"], 6)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_face_reference_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "face_reference_test_part.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("start_sketch_on_face"), 2)
        self.assertEqual(operation_types.count("tag_face"), 1)
        self.assertEqual(operation_types.count("extrude"), 2)
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 3)
        first_face_target = job.part.operations[8].parameters["target"]
        self.assertEqual(first_face_target["feature"], "extrude_base")
        self.assertEqual(first_face_target["area"], "largest")
        named_face_target = job.part.operations[17].parameters["target"]
        self.assertEqual(named_face_target["type"], "named_face")
        self.assertEqual(named_face_target["name"], "boss_top_face")

    def test_preview_backend_generates_face_reference_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "face-reference-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "face_reference_test_part.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 24)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("start_sketch_on_face"), 2)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("tag_face"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_extrude"), 1)
            self.assertEqual(summary["metadata"]["hole_count"], 1)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_chinese_offset_plane_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "中文命名偏置基准面测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        self.assertEqual(job.job_id, "中文命名-偏置基准面测试-001")
        self.assertEqual(job.part.name, "中文命名偏置孔测试件")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("tag_face"), 1)
        self.assertEqual(operation_types.count("create_offset_plane"), 1)
        self.assertEqual(operation_types.count("start_sketch"), 2)
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 2)

    def test_preview_backend_preserves_chinese_names(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "chinese-name-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "中文命名偏置基准面测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 17)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("create_offset_plane"), 1)
            self.assertEqual(summary["metadata"]["hole_count"], 1)
            self.assertIn("中文命名-偏置基准面测试-001", str(summary["output_dir"]))
            self.assertTrue(any("中文命名偏置孔测试件" in path for path in summary["artifacts"]))
            saved = json.loads(Path(str(summary["summary_path"])).read_text(encoding="utf-8"))
            self.assertEqual(saved["job_id"], "中文命名-偏置基准面测试-001")
            self.assertIn("中文命名偏置孔测试件", "\n".join(saved["artifacts"]))
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_revolve_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "中文旋转轴测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        self.assertEqual(job.job_id, "中文旋转轴测试-001")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("add_centerline"), 0)
        self.assertEqual(operation_types.count("revolve"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 1)

    def test_preview_backend_generates_revolve_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "revolve-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "中文旋转轴测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 8)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_centerline"), 0)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("revolve"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 50.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 40.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 40.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_cut_revolve_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "中文旋转切除测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        self.assertEqual(job.job_id, "中文旋转切除测试-001")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("start_sketch"), 2)
        self.assertEqual(operation_types.count("revolve"), 1)
        self.assertEqual(operation_types.count("cut_revolve"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 2)
        self.assertEqual(job.part.operations[0].parameters["plane"], "front")
        self.assertEqual(job.part.operations[8].parameters["plane"], "front")

    def test_preview_backend_generates_cut_revolve_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "cut-revolve-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "primitives" / "中文旋转切除测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 16)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("revolve"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_revolve"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 60.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 40.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 40.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_sweep_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文扫描把手测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        self.assertEqual(job.job_id, "中文扫描把手测试-001")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("finish_sketch"), 1)
        self.assertEqual(operation_types.count("sweep"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 2)
        self.assertEqual(job.part.operations[-1].parameters["profile"], "圆管截面草图")
        self.assertEqual(job.part.operations[-1].parameters["path"], "把手扫描路径草图")

    def test_preview_backend_generates_sweep_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "sweep-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文扫描把手测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 13)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("finish_sketch"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("sweep"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 132.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 52.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 12.0)
            self.assertEqual(summary["metadata"]["hole_count"], 0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_arc_cut_sweep_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文圆弧扫描切除测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("add_arc"), 2)
        self.assertEqual(operation_types.count("sweep"), 1)
        self.assertEqual(operation_types.count("cut_sweep"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 4)

    def test_preview_backend_generates_arc_cut_sweep_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "arc-cut-sweep-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文圆弧扫描切除测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 38)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_arc"), 2)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_sweep"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 124.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 54.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 14.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_twist_sweep_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文扭转扫描测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation = job.part.operations[-1]
        self.assertEqual(operation.type, "sweep")
        self.assertEqual(operation.parameters["twist_control"], "constant_twist")
        self.assertEqual(operation.parameters["twist_angle"], 90)

    def test_guide_variable_sweep_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文导向线变截面扫描测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation = job.part.operations[-1]
        self.assertEqual(operation.type, "sweep")
        self.assertEqual(operation.parameters["guide_curves"], ["扫描导向线草图"])
        self.assertEqual(operation.parameters["section_control"]["mode"], "guide_curves")
        relation_operations = [item for item in job.part.operations if item.type == "add_relation"]
        self.assertEqual(
            [item.parameters["relation"] for item in relation_operations].count("pierce"),
            2,
        )

    def test_loft_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文放样过渡管测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        self.assertEqual(job.job_id, "中文放样过渡管测试-001")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("create_offset_plane"), 2)
        self.assertEqual(operation_types.count("finish_sketch"), 3)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 3)
        self.assertEqual(operation_types.count("loft"), 1)
        loft_operation = job.part.operations[-1]
        self.assertEqual(
            loft_operation.parameters["profiles"],
            ["入口圆截面草图", "中间圆截面草图", "出口圆截面草图"],
        )

    def test_preview_backend_generates_loft_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "loft-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文放样过渡管测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 21)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("loft"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("create_offset_plane"), 2)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 30.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 30.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 80.0)
            self.assertEqual(summary["metadata"]["hole_count"], 0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_cut_loft_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文放样切除测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        self.assertEqual(job.job_id, "中文放样切除测试-001")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("extrude"), 1)
        self.assertEqual(operation_types.count("create_offset_plane"), 2)
        self.assertEqual(operation_types.count("finish_sketch"), 3)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 4)
        self.assertEqual(operation_types.count("cut_loft"), 1)
        cut_loft_operation = job.part.operations[-1]
        self.assertEqual(
            cut_loft_operation.parameters["profiles"],
            ["入口切除截面草图", "中间切除截面草图", "出口切除截面草图"],
        )

    def test_preview_backend_generates_cut_loft_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "cut-loft-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "advanced" / "中文放样切除测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 29)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_loft"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("create_offset_plane"), 2)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 100.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 60.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 90.0)
            self.assertEqual(summary["metadata"]["hole_count"], 0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_sketch_optimized_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文草图优化测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        self.assertEqual(job.job_id, "中文草图优化测试-001")
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("sketch_fillet"), 4)
        self.assertEqual(operation_types.count("sketch_chamfer"), 4)
        self.assertEqual(operation_types.count("add_chamfered_rectangle"), 0)
        self.assertEqual(operation_types.count("add_mirrored_circle"), 1)
        self.assertEqual(operation_types.count("add_circle_linear_pattern"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 3)
        self.assertEqual(operation_types.count("cut_extrude"), 2)
        pattern_operation = next(operation for operation in job.part.operations if operation.id == "右侧定位孔线性阵列")
        self.assertFalse(pattern_operation.parameters.get("fix_copies", False))

    def test_preview_backend_generates_sketch_optimized_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "sketch-optimized-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文草图优化测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 36)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("sketch_fillet"), 4)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("sketch_chamfer"), 4)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_chamfered_rectangle"), 0)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_mirrored_circle"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_circle_linear_pattern"), 1)
            self.assertEqual(summary["metadata"]["hole_count"], 4)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 100.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 60.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 10.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_slot_polygon_spline_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文槽口多边形样条测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("add_straight_slot"), 1)
        self.assertEqual(operation_types.count("add_polygon"), 1)
        self.assertEqual(operation_types.count("add_spline"), 1)
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("fully_define_sketch"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 3)
        self.assertEqual(operation_types.count("finish_sketch"), 1)

    def test_preview_backend_generates_slot_polygon_spline_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "slot-polygon-spline-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文槽口多边形样条测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 22)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_straight_slot"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_polygon"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("add_spline"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("fully_define_sketch"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("validate_fully_constrained"), 3)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_convert_offset_groove_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文转换实体等距切槽测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("convert_entities"), 1)
        self.assertEqual(operation_types.count("offset_entities"), 1)
        self.assertEqual(operation_types.count("fully_define_sketch"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 2)
        self.assertEqual(operation_types.count("cut_extrude"), 1)

    def test_preview_backend_generates_convert_offset_groove_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "convert-offset-groove-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文转换实体等距切槽测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 16)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("convert_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("offset_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("fully_define_sketch"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_extrude"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 100.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 60.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 10.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_trim_entities_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文草图剪裁测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("convert_entities"), 1)
        self.assertEqual(operation_types.count("trim_entities"), 1)
        self.assertEqual(operation_types.count("finish_sketch"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 1)

    def test_preview_backend_generates_trim_entities_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "trim-entities-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文草图剪裁测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 17)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("convert_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("trim_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("finish_sketch"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 100.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 60.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 8.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_complex_trim_entities_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文草图复杂剪裁测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("trim_entities"), 3)
        self.assertEqual(operation_types.count("delete_entities"), 1)
        self.assertEqual(operation_types.count("convert_entities"), 1)
        self.assertEqual(operation_types.count("finish_sketch"), 3)
        self.assertEqual(job.part.operations[15].parameters["mode"], "inside")
        self.assertEqual(job.part.operations[24].parameters["mode"], "outside")
        self.assertEqual(job.part.operations[32].parameters["mode"], "power")
        self.assertEqual(len(job.part.operations[15].parameters["boundary_entities"]), 2)
        self.assertEqual(len(job.part.operations[24].parameters["boundary_entities"]), 2)
        self.assertEqual(len(job.part.operations[32].parameters["trim_targets"]), 1)

    def test_preview_backend_generates_complex_trim_entities_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "complex-trim-entities-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文草图复杂剪裁测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 34)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("trim_entities"), 3)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("delete_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("convert_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("finish_sketch"), 3)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 120.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 70.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 8.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_open_slot_workflow_example_passes_validation(self) -> None:
        data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文开口槽工作流测试.json").read_text(encoding="utf-8"))
        job = CadJob.from_dict(data)
        validate_job(job)
        operation_types = [operation.type for operation in job.part.operations]
        self.assertEqual(operation_types.count("convert_entities"), 1)
        self.assertEqual(operation_types.count("offset_entities"), 1)
        self.assertEqual(operation_types.count("trim_entities"), 1)
        self.assertEqual(operation_types.count("delete_entities"), 1)
        self.assertEqual(operation_types.count("cut_extrude"), 1)
        self.assertEqual(operation_types.count("validate_fully_constrained"), 2)

    def test_preview_backend_generates_open_slot_workflow_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "open-slot-workflow-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads((PROJECT_ROOT / "examples" / "sketch" / "中文开口槽工作流测试.json").read_text(encoding="utf-8"))
            job = CadJob.from_dict(data)
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["operation_count"], 22)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("convert_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("offset_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("trim_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("delete_entities"), 1)
            self.assertEqual(summary["metadata"]["primitive_operation_types"].count("cut_extrude"), 1)
            self.assertEqual(summary["metadata"]["bounding_box"]["length"], 120.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["width"], 70.0)
            self.assertEqual(summary["metadata"]["bounding_box"]["thickness"], 8.0)
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
