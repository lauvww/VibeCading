from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from adapters.base import BackendResult, BackendUnavailable
from adapters.preview_adapter import write_report_pdf, write_top_view_svg
from core.dsl import CadJob


class FreeCadAdapter:
    name = "freecad"

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("FreeCAD") is not None

    def run_mounting_plate(self, job: CadJob, output_dir: Path) -> BackendResult:
        if not self.is_available():
            raise BackendUnavailable("FreeCAD Python modules are not available in this environment.")

        import FreeCAD as App  # type: ignore[import-not-found]
        import Import  # type: ignore[import-not-found]
        import Part  # type: ignore[import-not-found]

        output_dir.mkdir(parents=True, exist_ok=True)
        part = job.part
        doc = App.newDocument(job.safe_name)

        shape = Part.makeBox(part.length, part.width, part.thickness)
        for hole in part.holes:
            cylinder = Part.makeCylinder(
                hole.diameter / 2,
                part.thickness + 2,
                App.Vector(hole.x, hole.y, -1),
                App.Vector(0, 0, 1),
            )
            shape = shape.cut(cylinder)

        obj = doc.addObject("Part::Feature", part.name)
        obj.Shape = shape
        doc.recompute()

        result = BackendResult(backend=self.name, ok=True)
        spec_path = output_dir / "job_spec.json"
        spec_path.write_text(json.dumps(job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        result.add_artifact(spec_path)

        if "step" in part.export_formats:
            step_path = output_dir / f"{part.name}.step"
            Import.export([obj], str(step_path))
            result.add_artifact(step_path)

        if "svg" in part.export_formats:
            svg_path = output_dir / f"{part.name}_top.svg"
            write_top_view_svg(job, svg_path)
            result.add_artifact(svg_path)

        if "pdf" in part.export_formats:
            pdf_path = output_dir / f"{part.name}_report.pdf"
            write_report_pdf(job, pdf_path, backend=self.name, generated_step="step" in part.export_formats)
            result.add_artifact(pdf_path)

        result.metadata.update(
            {
                "completed_exports": list(part.export_formats),
                "unsupported_exports": [],
            }
        )
        return result

    def run_feature_part(self, job: CadJob, output_dir: Path) -> BackendResult:
        raise BackendUnavailable("FreeCAD feature_part execution is not implemented yet.")

    def run_primitive_part(self, job: CadJob, output_dir: Path) -> BackendResult:
        raise BackendUnavailable("FreeCAD primitive_part execution is not implemented yet.")
