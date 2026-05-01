from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from adapters.base import BackendResult, BackendUnavailable
from adapters.freecad_adapter import FreeCadAdapter
from adapters.preview_adapter import PreviewAdapter
from adapters.solidworks_com import SolidWorksComAdapter
from core.dsl import CadJob
from core.validators import validate_job


def _select_backend(name: str, job_kind: str):
    if name == "preview":
        return PreviewAdapter()
    if name == "freecad":
        return FreeCadAdapter()
    if name == "solidworks":
        return SolidWorksComAdapter()
    if name != "auto":
        raise ValueError(f"Unsupported backend: {name}")

    solidworks = SolidWorksComAdapter()
    if solidworks.is_available():
        return solidworks

    if job_kind == "mounting_plate":
        freecad = FreeCadAdapter()
        if freecad.is_available():
            return freecad

    return PreviewAdapter()


def _artifact_status(paths: list[str]) -> dict[str, bool]:
    return {path: Path(path).exists() and Path(path).stat().st_size > 0 for path in paths}


def _infer_completed_exports(paths: list[str]) -> list[str]:
    suffix_map = {
        ".json": "json",
        ".pdf": "pdf",
        ".svg": "svg",
        ".step": "step",
        ".stp": "step",
        ".stl": "stl",
        ".dxf": "dxf",
    }
    completed = {suffix_map[Path(path).suffix.lower()] for path in paths if Path(path).suffix.lower() in suffix_map}
    return sorted(completed)


def _write_summary(output_dir: Path, job: CadJob, result: BackendResult, started_at: str) -> dict[str, object]:
    finished_at = datetime.now(timezone.utc).isoformat()
    artifact_status = _artifact_status(result.artifacts)
    requested_exports = list(job.part.export_formats)
    completed_exports = list(result.metadata.get("completed_exports", _infer_completed_exports(result.artifacts)))
    unsupported_exports = list(result.metadata.get("unsupported_exports", []))
    missing_exports = sorted(set(requested_exports) - set(completed_exports))
    ok = result.ok and all(artifact_status.values()) and not result.errors
    summary: dict[str, object] = {
        "ok": ok,
        "job_id": job.job_id,
        "kind": job.kind,
        "backend": result.backend,
        "started_at": started_at,
        "finished_at": finished_at,
        "output_dir": str(output_dir),
        "artifacts": result.artifacts,
        "artifact_status": artifact_status,
        "requested_exports": requested_exports,
        "completed_exports": completed_exports,
        "missing_exports": missing_exports,
        "unsupported_exports": unsupported_exports,
        "cad_outputs_complete": not missing_exports and not unsupported_exports,
        "warnings": result.warnings,
        "errors": result.errors,
        "metadata": result.metadata,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def run_job(job: CadJob, output_root: Path, backend: str | None = None) -> dict[str, object]:
    validate_job(job)
    selected = backend or job.backend
    started_at = datetime.now(timezone.utc).isoformat()
    output_dir = output_root / job.safe_name
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = _select_backend(selected, job.kind)

    try:
        if job.kind == "mounting_plate":
            result = adapter.run_mounting_plate(job, output_dir)
        elif job.kind == "feature_part":
            result = adapter.run_feature_part(job, output_dir)
        elif job.kind == "primitive_part":
            result = adapter.run_primitive_part(job, output_dir)
        else:
            raise ValueError(f"Unsupported CAD job kind: {job.kind}")
    except BackendUnavailable as exc:
        result = BackendResult(
            backend=getattr(adapter, "name", selected),
            ok=False,
            errors=[str(exc)],
        )

    return _write_summary(output_dir, job, result, started_at)
