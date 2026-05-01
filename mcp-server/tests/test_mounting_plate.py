from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.dsl import CadJob
from core.job_runner import run_job
from core.template_compiler import compile_to_primitive_job
from core.validators import ValidationError, validate_job


def valid_job_dict() -> dict:
    return {
        "job_id": "test-mounting-plate",
        "kind": "mounting_plate",
        "backend": "preview",
        "units": "mm",
        "part": {
            "name": "test_plate",
            "length": 100,
            "width": 60,
            "thickness": 6,
            "corner_radius": 3,
            "holes": [
                {"x": 15, "y": 15, "diameter": 6},
                {"x": 85, "y": 45, "diameter": 6},
            ],
            "export_formats": ["pdf", "svg", "step"],
        },
    }


class MountingPlateTests(unittest.TestCase):
    def test_valid_job_passes_validation(self) -> None:
        job = CadJob.from_dict(valid_job_dict())
        validate_job(job)
        self.assertEqual(job.part.length, 100)

    def test_hole_outside_plate_fails_validation(self) -> None:
        data = valid_job_dict()
        data["part"]["holes"][0]["x"] = 2
        job = CadJob.from_dict(data)
        with self.assertRaises(ValidationError):
            validate_job(job)

    def test_mounting_plate_template_compiles_to_primitives(self) -> None:
        job = CadJob.from_dict(valid_job_dict())
        primitive_job = compile_to_primitive_job(job)
        self.assertEqual(primitive_job.kind, "primitive_part")
        self.assertEqual(primitive_job.part.source_kind, "mounting_plate")
        operation_types = [operation.type for operation in primitive_job.part.operations]
        self.assertIn("add_center_rectangle", operation_types)
        self.assertEqual(operation_types.count("add_circle"), 2)
        self.assertIn("validate_fully_constrained", operation_types)
        self.assertEqual(operation_types[-1], "extrude")

    def test_preview_backend_generates_verifiable_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "preview-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            job = CadJob.from_dict(valid_job_dict())
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            artifacts = [Path(path) for path in summary["artifacts"]]
            self.assertTrue(any(path.suffix == ".pdf" for path in artifacts))
            self.assertTrue(any(path.suffix == ".svg" for path in artifacts))
            self.assertTrue(summary["warnings"])
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
            self.assertTrue(Path(str(summary["summary_path"])).exists())
            saved = json.loads(Path(str(summary["summary_path"])).read_text(encoding="utf-8"))
            self.assertEqual(saved["backend"], "preview")
            self.assertEqual(saved["metadata"]["source_kind"], "mounting_plate")
            self.assertIn("add_center_rectangle", saved["metadata"]["primitive_operation_types"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
