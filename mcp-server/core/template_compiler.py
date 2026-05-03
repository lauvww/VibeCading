from __future__ import annotations

from typing import Any

from core.dsl import CadJob, FeaturePart, MountingPlate, PrimitiveOperation, PrimitivePart


LEGACY_COMPAT_JOB_KINDS = {"mounting_plate", "feature_part"}
LEGACY_COMPAT_FEATURE_OPERATIONS = {"l_profile_extrude"}


def _operation(
    operation_id: str,
    operation_type: str,
    parameters: dict[str, Any] | None = None,
) -> PrimitiveOperation:
    return PrimitiveOperation(
        id=operation_id,
        type=operation_type,
        parameters=parameters or {},
    )


def _profile_edge(profile_id: str, edge: str) -> dict[str, str]:
    return {"type": "profile_edge", "profile": profile_id, "edge": edge}


def _profile_segment(profile_id: str, index: int) -> dict[str, object]:
    return {"type": "profile_segment", "profile": profile_id, "index": index}


def _profile_point(profile_id: str, index: int, point: str) -> dict[str, object]:
    return {"type": "profile_point", "profile": profile_id, "index": index, "point": point}


def _point(point_id: str) -> dict[str, str]:
    return {"type": "point", "id": point_id}


def _circle(circle_id: str) -> dict[str, str]:
    return {"type": "circle", "id": circle_id}


def _circle_center(circle_id: str) -> dict[str, str]:
    return {"type": "circle_center", "circle": circle_id}


def _entity_dimension(label: str, entity: dict[str, object], position: list[float]) -> dict[str, object]:
    return {
        "id": label,
        "type": "entity",
        "entity": entity,
        "position": position,
    }


def _horizontal_dimension(
    label: str,
    first: dict[str, object],
    second: dict[str, object],
    position: list[float],
) -> dict[str, object]:
    return {
        "id": label,
        "type": "horizontal_between",
        "first": first,
        "second": second,
        "position": position,
    }


def _vertical_dimension(
    label: str,
    first: dict[str, object],
    second: dict[str, object],
    position: list[float],
) -> dict[str, object]:
    return {
        "id": label,
        "type": "vertical_between",
        "first": first,
        "second": second,
        "position": position,
    }


def _mounting_plate_to_primitives(part: MountingPlate) -> list[PrimitiveOperation]:
    # Legacy compatibility path: mounting_plate remains a supported regression example,
    # but execution should flow through primitive_part operations.
    sketch_id = "plate_sketch"
    profile_id = "plate_outline"
    center_ref_id = "plate_center_ref"
    half_length = part.length / 2
    half_width = part.width / 2

    operations = [
        _operation("start_plate_sketch", "start_sketch", {"sketch": sketch_id, "plane": "base"}),
        _operation(
            profile_id,
            "add_center_rectangle",
            {
                "sketch": sketch_id,
                "center": [0, 0],
                "size": [part.length, part.width],
            },
        ),
    ]

    for index, hole in enumerate(part.holes, start=1):
        operations.append(
            _operation(
                f"hole_{index}",
                "add_circle",
                {
                    "sketch": sketch_id,
                    "center": [hole.x - half_length, hole.y - half_width],
                    "diameter": hole.diameter,
                    "label": hole.label,
                },
            )
        )

    operations.extend(
        [
            _operation(center_ref_id, "add_point", {"sketch": sketch_id, "point": [0, 0]}),
            _operation("plate_axis_constraints", "add_axis_constraints", {"profile": profile_id}),
            _operation(
                "plate_center_fixed",
                "add_relation",
                {"entity": _point(center_ref_id), "relation": "fixed"},
            ),
        ]
    )

    dimensions: list[dict[str, object]] = [
        _entity_dimension("plate_length", _profile_edge(profile_id, "bottom"), [0, -half_width - 12]),
        _entity_dimension("plate_width", _profile_edge(profile_id, "left"), [-half_length - 12, 0]),
        _horizontal_dimension(
            "center_to_left_edge",
            _point(center_ref_id),
            _profile_edge(profile_id, "left"),
            [-half_length / 2, 12],
        ),
        _vertical_dimension(
            "center_to_bottom_edge",
            _point(center_ref_id),
            _profile_edge(profile_id, "bottom"),
            [12, -half_width / 2],
        ),
    ]

    for index, hole in enumerate(part.holes, start=1):
        circle_id = f"hole_{index}"
        center_x = hole.x - half_length
        center_y = hole.y - half_width
        dimensions.extend(
            [
                _entity_dimension(
                    f"{circle_id}_diameter",
                    _circle(circle_id),
                    [center_x + hole.diameter / 2 + 8, center_y + hole.diameter / 2 + 8],
                ),
                _horizontal_dimension(
                    f"{circle_id}_x_position",
                    _profile_edge(profile_id, "left"),
                    _circle_center(circle_id),
                    [(center_x - half_length) / 2, center_y + 8],
                ),
                _vertical_dimension(
                    f"{circle_id}_y_position",
                    _profile_edge(profile_id, "bottom"),
                    _circle_center(circle_id),
                    [center_x + 8, (center_y - half_width) / 2],
                ),
            ]
        )

    operations.extend(
        [
            _operation("plate_dimensions", "add_dimensions", {"dimensions": dimensions}),
            _operation("validate_plate_sketch", "validate_fully_constrained", {"sketch": sketch_id}),
            _operation("extrude_plate", "extrude", {"sketch": sketch_id, "depth": part.thickness}),
        ]
    )
    return operations


def _l_profile_to_primitives(operation_id: str, params: dict[str, Any]) -> list[PrimitiveOperation]:
    # Legacy compatibility path: l_profile_extrude stays as a narrow regression example,
    # not as a product expansion direction.
    sketch_id = f"{operation_id}_sketch"
    profile_id = operation_id
    base_length = float(params["base_length"])
    height = float(params["height"])
    width = float(params["width"])
    base_thickness = float(params["base_thickness"])
    wall_thickness = float(params["wall_thickness"])

    points = [
        [0, 0],
        [base_length, 0],
        [base_length, base_thickness],
        [wall_thickness, base_thickness],
        [wall_thickness, height],
        [0, height],
    ]
    dimensions = [
        _entity_dimension("base_length", _profile_segment(profile_id, 0), [base_length / 2, -12]),
        _entity_dimension("base_thickness", _profile_segment(profile_id, 1), [base_length + 12, base_thickness / 2]),
        _entity_dimension("wall_thickness", _profile_segment(profile_id, 4), [wall_thickness / 2, height + 12]),
        _entity_dimension("height", _profile_segment(profile_id, 5), [-12, height / 2]),
    ]

    return [
        _operation(f"start_{sketch_id}", "start_sketch", {"sketch": sketch_id, "plane": "base"}),
        _operation(profile_id, "add_polyline", {"sketch": sketch_id, "points": points, "closed": True}),
        _operation(f"{profile_id}_axis_constraints", "add_axis_constraints", {"profile": profile_id}),
        _operation(
            f"{profile_id}_origin_fixed",
            "add_relation",
            {"entity": _profile_point(profile_id, 0, "start"), "relation": "fixed"},
        ),
        _operation(f"{profile_id}_dimensions", "add_dimensions", {"dimensions": dimensions}),
        _operation(f"validate_{sketch_id}", "validate_fully_constrained", {"sketch": sketch_id}),
        _operation(f"extrude_{profile_id}", "extrude", {"sketch": sketch_id, "depth": width}),
    ]


def _feature_part_to_primitives(part: FeaturePart) -> list[PrimitiveOperation]:
    operations: list[PrimitiveOperation] = []
    for operation in part.operations:
        if operation.type == "l_profile_extrude":
            operations.extend(_l_profile_to_primitives(operation.id, operation.parameters))
        else:
            raise ValueError(f"Unsupported feature operation type: {operation.type}")
    return operations


def compile_to_primitive_job(job: CadJob) -> CadJob:
    """Compile legacy compatibility jobs into the primitive_part execution mainline."""
    if job.kind == "primitive_part":
        return job
    if isinstance(job.part, MountingPlate):
        primitive_part = PrimitivePart(
            name=job.part.name,
            material=job.part.material,
            export_formats=list(job.part.export_formats),
            source_kind=job.kind,
            operations=_mounting_plate_to_primitives(job.part),
        )
    elif isinstance(job.part, FeaturePart):
        primitive_part = PrimitivePart(
            name=job.part.name,
            material=job.part.material,
            export_formats=list(job.part.export_formats),
            source_kind=job.kind,
            operations=_feature_part_to_primitives(job.part),
        )
    else:
        raise ValueError(f"Unsupported job kind for primitive compilation: {job.kind}")

    return CadJob(
        job_id=job.job_id,
        kind="primitive_part",
        units=job.units,
        backend=job.backend,
        part=primitive_part,
    )
