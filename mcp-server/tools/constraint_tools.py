from __future__ import annotations

from typing import Any

from core.dsl import CadJob
from core.validators import validate_job


def mounting_plate_constraint_plan(spec: dict[str, Any]) -> dict[str, object]:
    job = CadJob.from_dict(spec)
    validate_job(job)
    hole_count = len(job.part.holes)
    return {
        "ok": True,
        "job_id": job.job_id,
        "kind": job.kind,
        "relations": [
            "bottom edge horizontal",
            "top edge horizontal",
            "left edge vertical",
            "right edge vertical",
            "center reference point fixed at sketch origin",
        ],
        "dimensions": {
            "plate": ["overall length", "overall width", "center-to-left edge", "center-to-bottom edge"],
            "holes_per_hole": ["diameter", "x position from left edge", "y position from bottom edge"],
            "expected_total": 4 + hole_count * 3,
        },
        "target_status": "fully_constrained",
    }

