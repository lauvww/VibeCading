from __future__ import annotations

from typing import Any

from core.dsl import CadJob
from core.validators import validate_job


def validate_cad_job(spec: dict[str, Any]) -> dict[str, object]:
    job = CadJob.from_dict(spec)
    validate_job(job)
    return {"ok": True, "job_id": job.job_id, "kind": job.kind}

