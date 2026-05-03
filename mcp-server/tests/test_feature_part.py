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


def valid_feature_job_dict() -> dict:
    return {
        "job_id": "test-l-bracket",
        "kind": "feature_part",
        "backend": "preview",
        "units": "mm",
        "part": {
            "name": "test_l_bracket",
            "export_formats": ["pdf", "svg", "step"],
            "operations": [
                {
                    "id": "main_l_profile",
                    "type": "l_profile_extrude",
                    "constraint_policy": "fully_constrained",
                    "parameters": {
                        "base_length": 120,
                        "height": 90,
                        "width": 50,
                        "base_thickness": 10,
                        "wall_thickness": 10,
                    },
                }
            ],
        },
    }


class FeaturePartTests(unittest.TestCase):
    def test_feature_part_job_passes_validation(self) -> None:
        job = CadJob.from_dict(valid_feature_job_dict())
        validate_job(job)
        self.assertEqual(job.kind, "feature_part")
        self.assertEqual(job.part.operations[0].type, "l_profile_extrude")

    def test_l_profile_bad_wall_thickness_fails_validation(self) -> None:
        data = valid_feature_job_dict()
        data["part"]["operations"][0]["parameters"]["wall_thickness"] = 120
        job = CadJob.from_dict(data)
        with self.assertRaises(ValidationError):
            validate_job(job)

    def test_l_profile_template_compiles_to_primitives(self) -> None:
        job = CadJob.from_dict(valid_feature_job_dict())
        primitive_job = compile_to_primitive_job(job)
        self.assertEqual(primitive_job.kind, "primitive_part")
        self.assertEqual(primitive_job.part.source_kind, "feature_part")
        operation_types = [operation.type for operation in primitive_job.part.operations]
        self.assertEqual(operation_types[0], "start_sketch")
        self.assertIn("add_polyline", operation_types)
        self.assertIn("validate_fully_constrained", operation_types)
        self.assertEqual(operation_types[-1], "extrude")

    def test_preview_backend_generates_feature_part_outputs(self) -> None:
        output_root = SERVER_ROOT / "tests" / ".tmp" / "feature-job"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            job = CadJob.from_dict(valid_feature_job_dict())
            summary = run_job(job, output_root=output_root, backend="preview")
            self.assertTrue(summary["ok"])
            artifacts = [Path(path) for path in summary["artifacts"]]
            self.assertTrue(any(path.suffix == ".pdf" for path in artifacts))
            self.assertTrue(any(path.suffix == ".svg" for path in artifacts))
            self.assertFalse(summary["cad_outputs_complete"])
            self.assertEqual(summary["unsupported_exports"], ["step"])
            saved = json.loads(Path(str(summary["summary_path"])).read_text(encoding="utf-8"))
            self.assertEqual(saved["kind"], "feature_part")
            self.assertEqual(saved["metadata"]["source_kind"], "feature_part")
            self.assertIn("add_polyline", saved["metadata"]["primitive_operation_types"])
        finally:
            shutil.rmtree(output_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
