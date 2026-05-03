from __future__ import annotations

from pathlib import Path
from typing import Any

from core.dsl import CadJob
from core.job_runner import run_job
from core.validators import validate_job


def create_mounting_plate(spec: dict[str, Any], output_root: str | Path, backend: str = "auto") -> dict[str, object]:
    """Legacy compatibility helper for mounting_plate regression examples."""
    job = CadJob.from_dict(spec)
    validate_job(job)
    return run_job(job, output_root=Path(output_root), backend=backend)


def create_feature_part(spec: dict[str, Any], output_root: str | Path, backend: str = "auto") -> dict[str, object]:
    """Legacy compatibility helper for feature_part regression examples."""
    job = CadJob.from_dict(spec)
    validate_job(job)
    if job.kind != "feature_part":
        raise ValueError("create_feature_part expects kind=feature_part.")
    return run_job(job, output_root=Path(output_root), backend=backend)


def create_primitive_part(spec: dict[str, Any], output_root: str | Path, backend: str = "auto") -> dict[str, object]:
    """Primary helper for the primitive_part execution mainline."""
    job = CadJob.from_dict(spec)
    validate_job(job)
    if job.kind != "primitive_part":
        raise ValueError("create_primitive_part expects kind=primitive_part.")
    return run_job(job, output_root=Path(output_root), backend=backend)
