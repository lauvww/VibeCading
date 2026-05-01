from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

from adapters.base import BackendResult, BackendUnavailable
from adapters.preview_adapter import (
    primitive_bounds,
    primitive_hole_count,
    write_primitive_part_report_pdf,
    write_primitive_part_svg,
)
from adapters.solidworks_primitive_executor import SolidWorksPrimitiveExecutor
from core.dsl import CadJob
from core.template_compiler import compile_to_primitive_job


class SolidWorksComAdapter:
    name = "solidworks"
    server_root = Path(__file__).resolve().parents[1]

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("win32com") is not None

    @classmethod
    def template_candidates(cls) -> list[Path]:
        return sorted(cls.server_root.rglob("*.PRTDOT"), key=lambda path: (len(path.parts), str(path).lower()))

    @classmethod
    def find_part_template(cls) -> Path:
        for path in cls.template_candidates():
            if path.exists():
                return path
        raise BackendUnavailable(f"No SolidWorks part template was found under: {cls.server_root}")

    def check_connection(self, visible: bool = True) -> dict[str, object]:
        sw = self._connect(visible=visible)
        template = self.find_part_template()
        return {
            "ok": True,
            "backend": self.name,
            "revision": str(sw.RevisionNumber),
            "visible": bool(sw.Visible),
            "part_template": str(template),
            "part_template_exists": template.exists(),
            "active_doc": bool(sw.ActiveDoc),
        }

    def _connect(self, visible: bool = True):
        if not self.is_available():
            raise BackendUnavailable("pywin32/win32com is not available in this Python environment.")

        import win32com.client  # type: ignore[import-not-found]

        sw = win32com.client.Dispatch("SldWorks.Application")
        sw.Visible = visible
        return sw

    @staticmethod
    def _fresh_output_path(path: Path) -> Path:
        if path.exists():
            try:
                path.unlink()
            except OSError:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                return path.with_name(f"{path.stem}_{stamp}{path.suffix}")
        return path

    @staticmethod
    def _save_as(model, path: Path) -> bool:
        before_mtime = path.stat().st_mtime_ns if path.exists() else None
        try:
            model.SaveAs3(str(path), 0, 1)
        except Exception:
            try:
                model.SaveAs(str(path))
            except Exception:
                pass
        if not path.exists() or path.stat().st_size <= 0:
            return False
        if before_mtime is None:
            return True
        return path.stat().st_mtime_ns > before_mtime

    def run_mounting_plate(self, job: CadJob, output_dir: Path) -> BackendResult:
        return self.run_primitive_part(compile_to_primitive_job(job), output_dir)

    def run_feature_part(self, job: CadJob, output_dir: Path) -> BackendResult:
        return self.run_primitive_part(compile_to_primitive_job(job), output_dir)

    def run_primitive_part(self, job: CadJob, output_dir: Path) -> BackendResult:
        primitive_job = compile_to_primitive_job(job)
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        part = primitive_job.part
        sw = self._connect(visible=True)
        template_path = self.find_part_template()

        model = sw.NewDocument(str(template_path), 0, 0, 0)
        if model is None:
            raise BackendUnavailable(f"SolidWorks failed to create a part from template: {template_path}")

        result = BackendResult(backend=self.name, ok=True)
        result.metadata["solidworks_revision"] = str(sw.RevisionNumber)
        result.metadata["part_template"] = str(template_path)

        spec_path = output_dir / "job_spec.json"
        spec_path.write_text(json.dumps(primitive_job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        result.add_artifact(spec_path)

        operation_reports = SolidWorksPrimitiveExecutor(sw, model).execute(part)
        result.metadata["primitive_operations"] = operation_reports

        sldprt_path = self._fresh_output_path(output_dir / f"{part.name}.SLDPRT")
        if not self._save_as(model, sldprt_path):
            raise BackendUnavailable(f"SolidWorks failed to save part file: {sldprt_path}")
        result.add_artifact(sldprt_path)

        completed_exports = ["sldprt"]
        if "json" in part.export_formats:
            completed_exports.append("json")
        unsupported_exports: list[str] = []

        if "step" in part.export_formats:
            step_path = self._fresh_output_path(output_dir / f"{part.name}.STEP")
            if self._save_as(model, step_path):
                result.add_artifact(step_path)
                completed_exports.append("step")
            else:
                result.warnings.append("SolidWorks did not export STEP successfully.")
                unsupported_exports.append("step")

        if "stl" in part.export_formats:
            stl_path = self._fresh_output_path(output_dir / f"{part.name}.STL")
            if self._save_as(model, stl_path):
                result.add_artifact(stl_path)
                completed_exports.append("stl")
            else:
                result.warnings.append("SolidWorks did not export STL successfully.")
                unsupported_exports.append("stl")

        if "svg" in part.export_formats:
            svg_path = output_dir / f"{part.name}_primitive.svg"
            write_primitive_part_svg(primitive_job, svg_path)
            result.add_artifact(svg_path)
            completed_exports.append("svg")

        if "pdf" in part.export_formats:
            pdf_path = output_dir / f"{part.name}_report.pdf"
            write_primitive_part_report_pdf(
                primitive_job,
                pdf_path,
                backend=self.name,
                generated_step="step" in completed_exports,
            )
            result.add_artifact(pdf_path)
            completed_exports.append("pdf")

        for export_format in part.export_formats:
            if export_format not in {"json", "pdf", "svg", "step", "stl"}:
                result.warnings.append(f"SolidWorks adapter does not support {export_format.upper()} export yet.")
                unsupported_exports.append(export_format)

        bounds = primitive_bounds(part)
        primitive_types = [operation.type for operation in part.operations]
        result.metadata.update(
            {
                "source_kind": part.source_kind,
                "operation_count": len(part.operations),
                "operation_types": primitive_types,
                "primitive_operation_types": primitive_types,
                "bounding_box": {
                    "length": bounds["length"],
                    "width": bounds["width"],
                    "thickness": bounds["depth"],
                    "units": primitive_job.units,
                },
                "hole_count": primitive_hole_count(part),
                "completed_exports": completed_exports,
                "unsupported_exports": sorted(set(unsupported_exports)),
            }
        )
        return result
