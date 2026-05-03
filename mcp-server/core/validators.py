from __future__ import annotations

from core.dsl import CadJob, FeatureOperation, FeaturePart, MountingPlate, PrimitiveOperation, PrimitivePart
from core.templates import MVP_EXPORT_FORMATS
from core.units import SUPPORTED_UNITS


class ValidationError(ValueError):
    pass


def _require_positive(value: float, field_name: str) -> None:
    if value <= 0:
        raise ValidationError(f"{field_name} must be greater than zero.")


def _validate_holes(part: MountingPlate) -> None:
    seen: set[tuple[float, float, float]] = set()
    for index, hole in enumerate(part.holes, start=1):
        _require_positive(hole.diameter, f"hole {index} diameter")
        radius = hole.diameter / 2
        if hole.x - radius < 0 or hole.x + radius > part.length:
            raise ValidationError(f"hole {index} is outside the plate length.")
        if hole.y - radius < 0 or hole.y + radius > part.width:
            raise ValidationError(f"hole {index} is outside the plate width.")
        key = (round(hole.x, 4), round(hole.y, 4), round(hole.diameter, 4))
        if key in seen:
            raise ValidationError(f"hole {index} duplicates another hole.")
        seen.add(key)


def validate_mounting_plate(part: MountingPlate) -> None:
    _require_positive(part.length, "length")
    _require_positive(part.width, "width")
    _require_positive(part.thickness, "thickness")
    if part.corner_radius < 0:
        raise ValidationError("corner_radius cannot be negative.")
    if part.corner_radius * 2 > min(part.length, part.width):
        raise ValidationError("corner_radius is too large for the plate size.")
    if not part.export_formats:
        raise ValidationError("At least one export format is required.")
    unsupported = sorted(set(part.export_formats) - MVP_EXPORT_FORMATS)
    if unsupported:
        raise ValidationError(f"Unsupported export formats: {', '.join(unsupported)}.")
    _validate_holes(part)


def _operation_float(operation: FeatureOperation, key: str) -> float:
    value = operation.parameters.get(key)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Operation {operation.id} field {key} must be a number.") from exc


def _validate_l_profile_extrude(operation: FeatureOperation) -> None:
    base_length = _operation_float(operation, "base_length")
    height = _operation_float(operation, "height")
    width = _operation_float(operation, "width")
    base_thickness = _operation_float(operation, "base_thickness")
    wall_thickness = _operation_float(operation, "wall_thickness")
    for field_name, value in [
        ("base_length", base_length),
        ("height", height),
        ("width", width),
        ("base_thickness", base_thickness),
        ("wall_thickness", wall_thickness),
    ]:
        _require_positive(value, f"{operation.id}.{field_name}")
    if wall_thickness >= base_length:
        raise ValidationError(f"Operation {operation.id} wall_thickness must be smaller than base_length.")
    if base_thickness >= height:
        raise ValidationError(f"Operation {operation.id} base_thickness must be smaller than height.")
    if operation.constraint_policy != "fully_constrained":
        raise ValidationError(f"Operation {operation.id} must use constraint_policy=fully_constrained.")


def validate_feature_part(part: FeaturePart) -> None:
    if not part.operations:
        raise ValidationError("feature_part requires at least one operation.")
    if not part.export_formats:
        raise ValidationError("At least one export format is required.")
    unsupported = sorted(set(part.export_formats) - MVP_EXPORT_FORMATS)
    if unsupported:
        raise ValidationError(f"Unsupported export formats: {', '.join(unsupported)}.")
    seen_ids: set[str] = set()
    for operation in part.operations:
        if operation.id in seen_ids:
            raise ValidationError(f"Duplicate operation id: {operation.id}.")
        seen_ids.add(operation.id)
        if operation.type == "l_profile_extrude":
            _validate_l_profile_extrude(operation)
        else:
            raise ValidationError(f"Unsupported feature operation type: {operation.type}.")


PRIMITIVE_OPERATION_REQUIRED_PARAMS = {
    "start_sketch": {"sketch", "plane"},
    "start_sketch_on_face": {"sketch", "target"},
    "finish_sketch": {"sketch"},
    "tag_face": {"name", "target"},
    "create_offset_plane": {"name", "offset"},
    "add_centerline": {"sketch", "start", "end"},
    "add_polyline": {"sketch", "points"},
    "add_arc": {"sketch", "center", "start", "end"},
    "add_center_rectangle": {"sketch", "center", "size"},
    "add_chamfered_rectangle": {"sketch", "center", "size", "chamfer"},
    "add_straight_slot": {"sketch", "center", "length", "width"},
    "add_polygon": {"sketch", "center", "radius", "sides"},
    "add_spline": {"sketch", "points"},
    "add_circle": {"sketch", "center", "diameter"},
    "add_mirrored_circle": {"sketch", "center", "diameter", "axis"},
    "add_circle_linear_pattern": {"sketch", "source", "count", "spacing"},
    "add_point": {"sketch", "point"},
    "add_axis_constraints": {"profile"},
    "add_relation": {"relation"},
    "add_dimensions": {"dimensions"},
    "fully_define_sketch": {"sketch"},
    "convert_entities": {"sketch", "target"},
    "offset_entities": {"sketch", "source", "offset"},
    "trim_entities": {"sketch"},
    "delete_entities": {"sketch", "entities"},
    "sketch_fillet": {"sketch", "entities", "radius"},
    "sketch_chamfer": {"sketch", "entities", "distance"},
    "validate_fully_constrained": {"sketch"},
    "extrude": {"sketch", "depth"},
    "cut_extrude": {"sketch", "depth"},
    "revolve": {"sketch", "axis"},
    "cut_revolve": {"sketch", "axis"},
    "sweep": {"profile", "path"},
    "cut_sweep": {"profile", "path"},
    "loft": {"profiles"},
    "cut_loft": {"profiles"},
    "hole_wizard": {"target", "locations", "hole_type", "size"},
}

SWEEP_TWIST_CONTROL_ALIASES = {
    "follow_path",
    "keep_normal_constant",
    "follow_path_first_guide_curve",
    "follow_first_second_guide_curves",
    "constant_twist",
    "normal_constant_twist",
}

SWEEP_PATH_ALIGN_ALIASES = {
    "none",
    "normal_to_profile",
    "direction_vector",
    "all_faces",
    "minimum_twist",
}

LOFT_GUIDE_CURVE_INFLUENCE_ALIASES = {
    "next_guide",
    "next_sharp",
    "next_edge",
    "next_global",
    "swguidecurveinfluencenextguide",
    "swguidecurveinfluencenextsharp",
    "swguidecurveinfluencenextedge",
    "swguidecurveinfluencenextglobal",
}

SKETCH_FILLET_CORNER_ACTIONS = {
    "interact": 0,
    "keep_geometry": 1,
    "delete_geometry": 2,
    "stop_processing": 3,
}

SKETCH_CHAMFER_TYPES = {
    "distance_angle": 0,
    "distance_distance": -1,
    "distance_equal": 2,
}

SKETCH_TRIM_MODES = {
    "closest",
    "trim_to_closest",
    "corner",
    "two_entities",
    "to_entity",
    "entity_point",
    "point",
    "power",
    "power_trim",
    "entities",
    "outside",
    "trim_away_outside",
    "inside",
    "trim_away_inside",
}


def _require_numeric_pair(value: object, field_name: str) -> None:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise ValidationError(f"{field_name} must be a two-number list.")
    for index, item in enumerate(value):
        try:
            float(item)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field_name}[{index}] must be a number.") from exc


def _require_numeric_vector(value: object, field_name: str, length: int) -> None:
    if not isinstance(value, list | tuple) or len(value) != length:
        raise ValidationError(f"{field_name} must be a {length}-number list.")
    for index, item in enumerate(value):
        try:
            float(item)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field_name}[{index}] must be a number.") from exc


def _require_numeric_point2_or_3(value: object, field_name: str) -> None:
    if not isinstance(value, list | tuple) or len(value) not in {2, 3}:
        raise ValidationError(f"{field_name} must be a two- or three-number list.")
    for index, item in enumerate(value):
        try:
            float(item)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field_name}[{index}] must be a number.") from exc


def _require_params(operation: PrimitiveOperation, required: set[str]) -> None:
    missing = sorted(required - set(operation.parameters))
    if missing:
        raise ValidationError(f"Primitive operation {operation.id} missing parameters: {', '.join(missing)}.")


def _require_number(value: object, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a number.") from exc


def _require_non_negative_int(value: object, field_name: str) -> int:
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a non-negative integer.") from exc
    if integer < 0:
        raise ValidationError(f"{field_name} must be a non-negative integer.")
    return integer


def _validate_face_target(operation_id: str, target: object, *, allow_named_face: bool) -> None:
    if not isinstance(target, dict):
        raise ValidationError(f"{operation_id}.target must be an object.")

    target_type = str(target.get("type", "body_face"))
    if target_type == "named_face":
        if not allow_named_face:
            raise ValidationError(f"{operation_id}.target.type cannot be named_face here.")
        name = str(target.get("name", "")).strip()
        if not name:
            raise ValidationError(f"{operation_id}.target.name is required for named_face.")
        return

    if target_type != "body_face":
        raise ValidationError(f"{operation_id}.target.type must be body_face or named_face.")
    _require_numeric_vector(target.get("normal"), f"{operation_id}.target.normal", 3)
    position = str(target.get("position", "")).lower()
    if position not in {"min", "max"}:
        raise ValidationError(f"{operation_id}.target.position must be min or max.")

    for key in ["feature", "feature_id"]:
        if key in target and not str(target[key]).strip():
            raise ValidationError(f"{operation_id}.target.{key} must not be empty.")

    if "area" in target and str(target["area"]).lower() not in {"largest", "smallest"}:
        raise ValidationError(f"{operation_id}.target.area must be largest or smallest.")
    if "area_rank" in target:
        _require_non_negative_int(target["area_rank"], f"{operation_id}.target.area_rank")
    if "min_dot" in target:
        min_dot = _require_number(target["min_dot"], f"{operation_id}.target.min_dot")
        if min_dot <= 0 or min_dot > 1:
            raise ValidationError(f"{operation_id}.target.min_dot must be greater than 0 and at most 1.")
    if "position_tolerance" in target:
        tolerance = _require_number(target["position_tolerance"], f"{operation_id}.target.position_tolerance")
        if tolerance < 0:
            raise ValidationError(f"{operation_id}.target.position_tolerance cannot be negative.")


def _sketch_ref_to_id(ref: object) -> str:
    if isinstance(ref, dict):
        sketch = str(ref.get("sketch", "")).strip()
    else:
        sketch = str(ref).strip()
    return sketch


def _validate_plane_or_face_target(operation_id: str, target: object) -> None:
    if isinstance(target, str):
        if not target.strip():
            raise ValidationError(f"{operation_id}.base must not be empty.")
        return

    if not isinstance(target, dict):
        raise ValidationError(f"{operation_id}.base must be a plane reference or face target object.")

    target_type = str(target.get("type", "body_face")).lower()
    if target_type in {"plane", "reference_plane", "datum_plane"}:
        plane_ref = (
            target.get("name")
            or target.get("plane")
            or target.get("ref")
            or target.get("id")
        )
        if not str(plane_ref or "").strip():
            raise ValidationError(f"{operation_id}.base plane target must include name, plane, ref, or id.")
        return

    _validate_face_target(operation_id, target, allow_named_face=True)


def _validate_primitive_operation(operation: PrimitiveOperation) -> None:
    if operation.type not in PRIMITIVE_OPERATION_REQUIRED_PARAMS:
        raise ValidationError(f"Unsupported primitive operation type: {operation.type}.")
    _require_params(operation, PRIMITIVE_OPERATION_REQUIRED_PARAMS[operation.type])

    if operation.type == "start_sketch_on_face":
        _validate_face_target(operation.id, operation.parameters["target"], allow_named_face=True)
    elif operation.type == "tag_face":
        if not str(operation.parameters["name"]).strip():
            raise ValidationError(f"{operation.id}.name must not be empty.")
        _validate_face_target(operation.id, operation.parameters["target"], allow_named_face=False)
    elif operation.type == "create_offset_plane":
        if not str(operation.parameters["name"]).strip():
            raise ValidationError(f"{operation.id}.name must not be empty.")
        _require_positive(float(operation.parameters["offset"]), f"{operation.id}.offset")
        base_target = operation.parameters.get("base", operation.parameters.get("target"))
        if base_target is None:
            raise ValidationError(f"{operation.id} must include base or target.")
        _validate_plane_or_face_target(operation.id, base_target)
    elif operation.type == "add_centerline":
        _require_numeric_pair(operation.parameters["start"], f"{operation.id}.start")
        _require_numeric_pair(operation.parameters["end"], f"{operation.id}.end")
        if list(operation.parameters["start"]) == list(operation.parameters["end"]):
            raise ValidationError(f"{operation.id}.start and {operation.id}.end must be different.")
    elif operation.type == "add_polyline":
        points = operation.parameters["points"]
        if not isinstance(points, list) or len(points) < 2:
            raise ValidationError(f"Primitive operation {operation.id} requires at least two polyline points.")
        if bool(operation.parameters.get("closed", False)) and len(points) < 3:
            raise ValidationError(f"Primitive operation {operation.id} requires at least three closed polyline points.")
        for index, point in enumerate(points):
            _require_numeric_pair(point, f"{operation.id}.points[{index}]")
    elif operation.type == "add_arc":
        _require_numeric_pair(operation.parameters["center"], f"{operation.id}.center")
        _require_numeric_pair(operation.parameters["start"], f"{operation.id}.start")
        _require_numeric_pair(operation.parameters["end"], f"{operation.id}.end")
        if list(operation.parameters["start"]) == list(operation.parameters["end"]):
            raise ValidationError(f"{operation.id}.start and {operation.id}.end must be different.")
        if list(operation.parameters["center"]) == list(operation.parameters["start"]):
            raise ValidationError(f"{operation.id}.center and {operation.id}.start must be different.")
        direction = str(operation.parameters.get("direction", "counterclockwise")).lower()
        if direction not in {"counterclockwise", "ccw", "clockwise", "cw", "1", "-1"}:
            raise ValidationError(f"{operation.id}.direction must be counterclockwise/ccw or clockwise/cw.")
    elif operation.type == "add_center_rectangle":
        _require_numeric_pair(operation.parameters["center"], f"{operation.id}.center")
        _require_numeric_pair(operation.parameters["size"], f"{operation.id}.size")
        width, height = [float(item) for item in operation.parameters["size"]]
        _require_positive(width, f"{operation.id}.size[0]")
        _require_positive(height, f"{operation.id}.size[1]")
    elif operation.type == "add_chamfered_rectangle":
        _require_numeric_pair(operation.parameters["center"], f"{operation.id}.center")
        _require_numeric_pair(operation.parameters["size"], f"{operation.id}.size")
        width, height = [float(item) for item in operation.parameters["size"]]
        chamfer = float(operation.parameters["chamfer"])
        _require_positive(width, f"{operation.id}.size[0]")
        _require_positive(height, f"{operation.id}.size[1]")
        _require_positive(chamfer, f"{operation.id}.chamfer")
        if chamfer * 2 >= min(width, height):
            raise ValidationError(f"{operation.id}.chamfer is too large for the rectangle size.")
    elif operation.type == "add_straight_slot":
        _require_numeric_pair(operation.parameters["center"], f"{operation.id}.center")
        length = float(operation.parameters["length"])
        width = float(operation.parameters["width"])
        _require_positive(length, f"{operation.id}.length")
        _require_positive(width, f"{operation.id}.width")
        if length <= width:
            raise ValidationError(f"{operation.id}.length must be greater than width for a straight slot.")
        float(operation.parameters.get("angle", 0))
    elif operation.type == "add_polygon":
        _require_numeric_pair(operation.parameters["center"], f"{operation.id}.center")
        _require_positive(float(operation.parameters["radius"]), f"{operation.id}.radius")
        sides = _require_non_negative_int(operation.parameters["sides"], f"{operation.id}.sides")
        if sides < 3:
            raise ValidationError(f"{operation.id}.sides must be at least 3.")
        float(operation.parameters.get("angle", 0))
    elif operation.type == "add_spline":
        points = operation.parameters["points"]
        if not isinstance(points, list) or len(points) < 2:
            raise ValidationError(f"{operation.id}.points must contain at least two points.")
        for index, point in enumerate(points):
            _require_numeric_pair(point, f"{operation.id}.points[{index}]")
    elif operation.type == "add_circle":
        _require_numeric_pair(operation.parameters["center"], f"{operation.id}.center")
        _require_positive(float(operation.parameters["diameter"]), f"{operation.id}.diameter")
    elif operation.type == "add_mirrored_circle":
        _require_numeric_pair(operation.parameters["center"], f"{operation.id}.center")
        _require_positive(float(operation.parameters["diameter"]), f"{operation.id}.diameter")
        axis = operation.parameters["axis"]
        if not isinstance(axis, dict) or str(axis.get("type", "")).lower() not in {"line", "centerline", "axis"}:
            raise ValidationError(f"{operation.id}.axis must reference a line, centerline, or axis.")
        if not str(axis.get("id", "")).strip():
            raise ValidationError(f"{operation.id}.axis.id must not be empty.")
    elif operation.type == "add_circle_linear_pattern":
        if not str(operation.parameters["source"]).strip():
            raise ValidationError(f"{operation.id}.source must not be empty.")
        count = _require_non_negative_int(operation.parameters["count"], f"{operation.id}.count")
        if count < 2:
            raise ValidationError(f"{operation.id}.count must be at least 2.")
        _require_numeric_pair(operation.parameters["spacing"], f"{operation.id}.spacing")
        dx, dy = [float(item) for item in operation.parameters["spacing"]]
        if dx == 0 and dy == 0:
            raise ValidationError(f"{operation.id}.spacing must not be [0, 0].")
    elif operation.type == "add_point":
        _require_numeric_pair(operation.parameters["point"], f"{operation.id}.point")
    elif operation.type == "add_relation":
        if str(operation.parameters["relation"]).lower() not in {
            "fixed",
            "horizontal",
            "vertical",
            "coincident",
            "tangent",
            "curvature",
            "equal_curvature",
            "pierce",
        }:
            raise ValidationError(
                "Primitive operation "
                f"{operation.id} currently supports fixed, horizontal, vertical, coincident, tangent, curvature, equal_curvature, or pierce relations."
            )
        if "entity" not in operation.parameters and "entities" not in operation.parameters:
            raise ValidationError(f"Primitive operation {operation.id} must include entity or entities.")
        if "entities" in operation.parameters:
            entities = operation.parameters["entities"]
            if not isinstance(entities, list) or not entities:
                raise ValidationError(f"{operation.id}.entities must be a non-empty list.")
    elif operation.type == "add_dimensions":
        dimensions = operation.parameters["dimensions"]
        if not isinstance(dimensions, list) or not dimensions:
            raise ValidationError(f"Primitive operation {operation.id} requires at least one dimension.")
        for index, dimension in enumerate(dimensions):
            if not isinstance(dimension, dict):
                raise ValidationError(f"{operation.id}.dimensions[{index}] must be an object.")
            if "type" not in dimension or "position" not in dimension:
                raise ValidationError(f"{operation.id}.dimensions[{index}] must include type and position.")
            _require_numeric_pair(dimension["position"], f"{operation.id}.dimensions[{index}].position")
    elif operation.type == "fully_define_sketch":
        if not str(operation.parameters["sketch"]).strip():
            raise ValidationError(f"{operation.id}.sketch must not be empty.")
        for datum_key in ("datum", "horizontal_datum", "vertical_datum"):
            if datum_key in operation.parameters and not isinstance(operation.parameters[datum_key], dict):
                raise ValidationError(f"{operation.id}.{datum_key} must be an entity reference object.")
    elif operation.type == "convert_entities":
        if not str(operation.parameters["sketch"]).strip():
            raise ValidationError(f"{operation.id}.sketch must not be empty.")
        target = operation.parameters["target"]
        if not isinstance(target, dict):
            raise ValidationError(f"{operation.id}.target must be an object.")
        target_type = str(target.get("type", "body_face")).lower()
        if target_type in {"body_face", "named_face"}:
            _validate_face_target(operation.id, target, allow_named_face=True)
        elif target_type in {"body_face_edges", "face_edges"}:
            face_target = dict(target)
            face_target["type"] = "body_face"
            _validate_face_target(operation.id, face_target, allow_named_face=False)
        elif target_type == "named_face_edges":
            if not str(target.get("name", "")).strip():
                raise ValidationError(f"{operation.id}.target.name is required for named_face_edges.")
        elif target_type == "entities":
            entities = target.get("entities")
            if not isinstance(entities, list) or not entities:
                raise ValidationError(f"{operation.id}.target.entities must be a non-empty list.")
        else:
            raise ValidationError(
                f"{operation.id}.target.type must be body_face, named_face, body_face_edges, named_face_edges, or entities."
            )
        loop = str(operation.parameters.get("loop", target.get("loop", "outer"))).lower()
        if loop not in {"outer", "inner", "all"}:
            raise ValidationError(f"{operation.id}.loop must be outer, inner, or all.")
    elif operation.type == "offset_entities":
        if not str(operation.parameters["sketch"]).strip():
            raise ValidationError(f"{operation.id}.sketch must not be empty.")
        _require_positive(float(operation.parameters["offset"]), f"{operation.id}.offset")
        source = operation.parameters["source"]
        if not isinstance(source, dict):
            raise ValidationError(f"{operation.id}.source must be an entity reference object.")
        direction = str(operation.parameters.get("direction", "default")).lower()
        if direction not in {"default", "outside", "inside", "inward", "outward", "positive", "negative", "reverse"}:
            raise ValidationError(f"{operation.id}.direction is not supported.")
    elif operation.type == "trim_entities":
        if not str(operation.parameters["sketch"]).strip():
            raise ValidationError(f"{operation.id}.sketch must not be empty.")
        has_flat_entities = "entities" in operation.parameters
        has_structured_entities = "boundary_entities" in operation.parameters or "trim_targets" in operation.parameters
        if has_flat_entities and has_structured_entities:
            raise ValidationError(f"{operation.id} must use either entities or boundary_entities/trim_targets, not both.")
        if not has_flat_entities and not has_structured_entities:
            raise ValidationError(f"{operation.id} must include entities or boundary_entities/trim_targets.")
        if has_structured_entities:
            boundary_entities = operation.parameters.get("boundary_entities", [])
            trim_targets = operation.parameters.get("trim_targets", [])
            if not isinstance(boundary_entities, list):
                raise ValidationError(f"{operation.id}.boundary_entities must be a list.")
            if not isinstance(trim_targets, list) or not trim_targets:
                raise ValidationError(f"{operation.id}.trim_targets must be a non-empty list.")
            for index, entity in enumerate(boundary_entities):
                if not isinstance(entity, dict):
                    raise ValidationError(f"{operation.id}.boundary_entities[{index}] must be an entity reference object.")
            for index, entity in enumerate(trim_targets):
                if not isinstance(entity, dict):
                    raise ValidationError(f"{operation.id}.trim_targets[{index}] must be an entity reference object.")
            entities = boundary_entities + trim_targets
        else:
            entities = operation.parameters["entities"]
            if not isinstance(entities, list) or not entities:
                raise ValidationError(f"{operation.id}.entities must be a non-empty list.")
            for index, entity in enumerate(entities):
                if not isinstance(entity, dict):
                    raise ValidationError(f"{operation.id}.entities[{index}] must be an entity reference object.")
        mode = str(operation.parameters.get("mode", "closest")).lower()
        if mode not in SKETCH_TRIM_MODES:
            raise ValidationError(f"{operation.id}.mode is not supported.")
        raw_pick_points = operation.parameters.get("pick_points")
        if raw_pick_points is not None:
            if not isinstance(raw_pick_points, list):
                raise ValidationError(f"{operation.id}.pick_points must be a list.")
            for index, point in enumerate(raw_pick_points):
                _require_numeric_point2_or_3(point, f"{operation.id}.pick_points[{index}]")
        for points_key in ("boundary_pick_points", "trim_pick_points"):
            points = operation.parameters.get(points_key)
            if points is not None:
                if not isinstance(points, list):
                    raise ValidationError(f"{operation.id}.{points_key} must be a list.")
                for index, point in enumerate(points):
                    _require_numeric_point2_or_3(point, f"{operation.id}.{points_key}[{index}]")
        if "pick_point" in operation.parameters:
            _require_numeric_point2_or_3(operation.parameters["pick_point"], f"{operation.id}.pick_point")
        if "trim_point" in operation.parameters:
            _require_numeric_point2_or_3(operation.parameters["trim_point"], f"{operation.id}.trim_point")
        if "point" in operation.parameters:
            _require_numeric_point2_or_3(operation.parameters["point"], f"{operation.id}.point")
        if has_structured_entities:
            if raw_pick_points is not None:
                raise ValidationError(f"{operation.id}.pick_points is only supported with flat entities.")
            if mode not in {"inside", "trim_away_inside", "outside", "trim_away_outside", "power", "power_trim", "entities"}:
                raise ValidationError(
                    f"{operation.id}.boundary_entities/trim_targets is only supported for inside/outside or power trim."
                )
            if "boundary_pick_points" in operation.parameters:
                boundary_points = operation.parameters["boundary_pick_points"]
                if len(boundary_points) != len(operation.parameters.get("boundary_entities", [])):
                    raise ValidationError(f"{operation.id}.boundary_pick_points must match boundary_entities count.")
            if "trim_pick_points" in operation.parameters:
                trim_points = operation.parameters["trim_pick_points"]
                if len(trim_points) != len(operation.parameters.get("trim_targets", [])):
                    raise ValidationError(f"{operation.id}.trim_pick_points must match trim_targets count.")
        if mode in {"closest", "trim_to_closest", "entity_point", "point"}:
            if len(entities) != 1:
                raise ValidationError(f"{operation.id}.entities must contain exactly one entity for {mode} trim.")
            if not any(key in operation.parameters for key in ("trim_point", "point", "pick_point", "pick_points")):
                raise ValidationError(f"{operation.id} must include trim_point or pick_point for {mode} trim.")
        elif mode in {"corner", "two_entities", "to_entity"}:
            if len(entities) != 2:
                raise ValidationError(f"{operation.id}.entities must contain exactly two entities for {mode} trim.")
            if raw_pick_points is not None and len(raw_pick_points) != 2:
                raise ValidationError(f"{operation.id}.pick_points must contain two points for {mode} trim.")
        elif mode in {"power", "power_trim", "entities"}:
            if has_structured_entities:
                if operation.parameters.get("boundary_entities"):
                    raise ValidationError(f"{operation.id}.boundary_entities is not used for power trim.")
                if "trim_pick_points" not in operation.parameters:
                    raise ValidationError(f"{operation.id}.trim_pick_points is required for power trim.")
            else:
                if raw_pick_points is None:
                    raise ValidationError(f"{operation.id}.pick_points is required for power trim.")
                if len(raw_pick_points) != len(entities):
                    raise ValidationError(f"{operation.id}.pick_points must match entities count for power trim.")
        elif mode in {"inside", "trim_away_inside", "outside", "trim_away_outside"}:
            if has_structured_entities:
                if len(operation.parameters.get("boundary_entities", [])) != 2:
                    raise ValidationError(f"{operation.id}.boundary_entities must contain exactly two entities for inside/outside trim.")
            else:
                if len(entities) < 3:
                    raise ValidationError(f"{operation.id}.entities must contain at least three entities for inside/outside trim.")
                if raw_pick_points is not None and len(raw_pick_points) != len(entities):
                    raise ValidationError(f"{operation.id}.pick_points must match entities count for inside/outside trim.")
    elif operation.type == "delete_entities":
        if not str(operation.parameters["sketch"]).strip():
            raise ValidationError(f"{operation.id}.sketch must not be empty.")
        entities = operation.parameters["entities"]
        if not isinstance(entities, list) or not entities:
            raise ValidationError(f"{operation.id}.entities must be a non-empty list.")
        for index, entity in enumerate(entities):
            if not isinstance(entity, dict):
                raise ValidationError(f"{operation.id}.entities[{index}] must be an entity reference object.")
    elif operation.type == "sketch_fillet":
        entities = operation.parameters["entities"]
        if not isinstance(entities, list) or len(entities) != 2:
            raise ValidationError(f"{operation.id}.entities must contain exactly two sketch entity references.")
        _require_positive(float(operation.parameters["radius"]), f"{operation.id}.radius")
        action = str(operation.parameters.get("constrained_corner_action", "keep_geometry")).lower()
        if action not in SKETCH_FILLET_CORNER_ACTIONS:
            raise ValidationError(f"{operation.id}.constrained_corner_action is not supported.")
    elif operation.type == "sketch_chamfer":
        entities = operation.parameters["entities"]
        if not isinstance(entities, list) or len(entities) != 2:
            raise ValidationError(f"{operation.id}.entities must contain exactly two sketch entity references.")
        _require_positive(float(operation.parameters["distance"]), f"{operation.id}.distance")
        chamfer_type = str(operation.parameters.get("chamfer_type", "distance_equal")).lower()
        if chamfer_type not in SKETCH_CHAMFER_TYPES:
            raise ValidationError(f"{operation.id}.chamfer_type is not supported.")
        if chamfer_type == "distance_distance":
            _require_positive(float(operation.parameters.get("distance2", 0)), f"{operation.id}.distance2")
        if chamfer_type == "distance_angle":
            angle = float(operation.parameters.get("angle", 0))
            if angle <= 0 or angle >= 180:
                raise ValidationError(f"{operation.id}.angle must be greater than 0 and smaller than 180.")
    elif operation.type in {"extrude", "cut_extrude"}:
        _require_positive(float(operation.parameters["depth"]), f"{operation.id}.depth")
    elif operation.type == "hole_wizard":
        _validate_face_target(operation.id, operation.parameters["target"], allow_named_face=True)
        hole_type = str(operation.parameters["hole_type"]).strip().lower()
        if hole_type not in {"simple", "clearance", "counterbore", "countersink", "threaded", "tapped"}:
            raise ValidationError(f"{operation.id}.hole_type is not supported.")
        if not str(operation.parameters["size"]).strip():
            raise ValidationError(f"{operation.id}.size must not be empty.")
        locations = operation.parameters["locations"]
        if not isinstance(locations, list) or not locations:
            raise ValidationError(f"{operation.id}.locations must be a non-empty list.")
        for index, location in enumerate(locations):
            if not isinstance(location, dict):
                raise ValidationError(f"{operation.id}.locations[{index}] must be an object.")
            _require_numeric_pair(location.get("center"), f"{operation.id}.locations[{index}].center")
            if "id" in location and not str(location["id"]).strip():
                raise ValidationError(f"{operation.id}.locations[{index}].id must not be empty.")
        for field_name in [
            "diameter",
            "depth",
            "thread_depth",
            "drill_depth",
            "tap_drill_diameter",
            "counterbore_diameter",
            "counterbore_depth",
            "countersink_diameter",
        ]:
            if field_name in operation.parameters and operation.parameters[field_name] is not None:
                _require_positive(float(operation.parameters[field_name]), f"{operation.id}.{field_name}")
        if "countersink_angle" in operation.parameters and operation.parameters["countersink_angle"] is not None:
            angle = float(operation.parameters["countersink_angle"])
            if angle <= 0 or angle >= 180:
                raise ValidationError(f"{operation.id}.countersink_angle must be greater than 0 and smaller than 180.")
        end_condition = str(operation.parameters.get("end_condition", "blind")).strip().lower()
        if end_condition not in {"blind", "through", "through_all"}:
            raise ValidationError(f"{operation.id}.end_condition is not supported.")
    elif operation.type in {"revolve", "cut_revolve"}:
        axis = operation.parameters["axis"]
        if not isinstance(axis, dict) or str(axis.get("type", "")).lower() not in {
            "line",
            "centerline",
            "axis",
            "profile_segment",
        }:
            raise ValidationError(f"{operation.id}.axis must reference a line, centerline, axis, or profile_segment.")
        axis_type = str(axis.get("type", "")).lower()
        if axis_type == "profile_segment":
            if not str(axis.get("profile", "")).strip():
                raise ValidationError(f"{operation.id}.axis.profile must not be empty.")
            _require_non_negative_int(axis.get("index"), f"{operation.id}.axis.index")
        elif not str(axis.get("id", "")).strip():
            raise ValidationError(f"{operation.id}.axis.id must not be empty.")
        if "angle" in operation.parameters:
            angle = float(operation.parameters["angle"])
            if angle <= 0 or angle > 360:
                raise ValidationError(f"{operation.id}.angle must be greater than 0 and at most 360.")
    elif operation.type in {"sweep", "cut_sweep"}:
        for key in ["profile", "path"]:
            sketch = _sketch_ref_to_id(operation.parameters[key])
            if not sketch:
                raise ValidationError(f"{operation.id}.{key} must reference a sketch.")
        if operation.parameters["profile"] == operation.parameters["path"]:
            raise ValidationError(f"{operation.id}.profile and {operation.id}.path must reference different sketches.")
        guide_curves = operation.parameters.get("guide_curves", [])
        if guide_curves is None:
            guide_curves = []
        if not isinstance(guide_curves, list):
            raise ValidationError(f"{operation.id}.guide_curves must be a list.")
        for index, guide in enumerate(guide_curves):
            if isinstance(guide, dict):
                guide_sketch = str(guide.get("sketch", "")).strip()
            else:
                guide_sketch = str(guide).strip()
            if not guide_sketch:
                raise ValidationError(f"{operation.id}.guide_curves[{index}] must reference a sketch.")
        twist_control = operation.parameters.get("twist_control")
        if twist_control is not None:
            if isinstance(twist_control, int):
                if twist_control not in {0, 1, 2, 3, 8, 9}:
                    raise ValidationError(f"{operation.id}.twist_control has an unsupported numeric value.")
            elif str(twist_control).lower() not in SWEEP_TWIST_CONTROL_ALIASES:
                raise ValidationError(f"{operation.id}.twist_control is not supported.")
        path_align = operation.parameters.get("path_align")
        if path_align is not None:
            if isinstance(path_align, int):
                if path_align not in {0, 1, 2, 3, 10}:
                    raise ValidationError(f"{operation.id}.path_align has an unsupported numeric value.")
            elif str(path_align).lower() not in SWEEP_PATH_ALIGN_ALIASES:
                raise ValidationError(f"{operation.id}.path_align is not supported.")
        if "twist_angle" in operation.parameters:
            float(operation.parameters["twist_angle"])
        section_control = operation.parameters.get("section_control")
        if section_control is not None:
            if not isinstance(section_control, dict):
                raise ValidationError(f"{operation.id}.section_control must be an object.")
            mode = str(section_control.get("mode", "constant")).lower()
            if mode not in {"constant", "guide_curves", "variable_by_guides"}:
                raise ValidationError(f"{operation.id}.section_control.mode is not supported.")
    elif operation.type in {"loft", "cut_loft"}:
        profiles = operation.parameters["profiles"]
        if not isinstance(profiles, list) or len(profiles) < 2:
            raise ValidationError(f"{operation.id}.profiles must include at least two sketch references.")
        profile_ids = [_sketch_ref_to_id(profile) for profile in profiles]
        if any(not profile_id for profile_id in profile_ids):
            raise ValidationError(f"{operation.id}.profiles must only contain non-empty sketch references.")
        if len(set(profile_ids)) != len(profile_ids):
            raise ValidationError(f"{operation.id}.profiles must not contain duplicate sketches.")

        guide_curves = operation.parameters.get("guide_curves", [])
        if guide_curves is None:
            guide_curves = []
        if not isinstance(guide_curves, list):
            raise ValidationError(f"{operation.id}.guide_curves must be a list.")
        for index, guide in enumerate(guide_curves):
            if not _sketch_ref_to_id(guide):
                raise ValidationError(f"{operation.id}.guide_curves[{index}] must reference a sketch.")

        centerline = operation.parameters.get("centerline")
        if centerline is not None and not _sketch_ref_to_id(centerline):
            raise ValidationError(f"{operation.id}.centerline must reference a sketch.")

        if bool(operation.parameters.get("closed", False)) and len(profile_ids) < 3 and not guide_curves:
            raise ValidationError(f"{operation.id}.closed loft/cut_loft requires at least three profiles or closed guide curves.")

        for key in ["start_matching_type", "end_matching_type"]:
            if key in operation.parameters:
                value = int(operation.parameters[key])
                if value not in {0, 1, 2, 3, 4}:
                    raise ValidationError(f"{operation.id}.{key} must be between 0 and 4.")

        guide_influence = operation.parameters.get("guide_curve_influence")
        if guide_influence is not None:
            if operation.type == "cut_loft":
                raise ValidationError(f"{operation.id}.guide_curve_influence is only supported for loft.")
            if isinstance(guide_influence, int):
                if guide_influence not in {0, 1, 2, 3}:
                    raise ValidationError(f"{operation.id}.guide_curve_influence has an unsupported numeric value.")
            elif str(guide_influence).lower() not in LOFT_GUIDE_CURVE_INFLUENCE_ALIASES:
                raise ValidationError(f"{operation.id}.guide_curve_influence is not supported.")

        if bool(operation.parameters.get("is_thin_body", False)):
            _require_positive(float(operation.parameters.get("thickness1", 0)), f"{operation.id}.thickness1")
            if "thickness2" in operation.parameters:
                _require_positive(float(operation.parameters["thickness2"]), f"{operation.id}.thickness2")


def validate_primitive_part(part: PrimitivePart) -> None:
    if not part.operations:
        raise ValidationError("primitive_part requires at least one operation.")
    if not part.export_formats:
        raise ValidationError("At least one export format is required.")
    unsupported = sorted(set(part.export_formats) - MVP_EXPORT_FORMATS)
    if unsupported:
        raise ValidationError(f"Unsupported export formats: {', '.join(unsupported)}.")
    seen_ids: set[str] = set()
    for operation in part.operations:
        if operation.id in seen_ids:
            raise ValidationError(f"Duplicate primitive operation id: {operation.id}.")
        seen_ids.add(operation.id)
        _validate_primitive_operation(operation)


def validate_job(job: CadJob) -> None:
    if job.units not in SUPPORTED_UNITS:
        raise ValidationError(f"Unsupported units: {job.units}. MVP-0 supports mm only.")
    if job.kind == "mounting_plate":
        if not isinstance(job.part, MountingPlate):
            raise ValidationError("mounting_plate job requires a mounting plate part.")
        validate_mounting_plate(job.part)
    elif job.kind == "feature_part":
        if not isinstance(job.part, FeaturePart):
            raise ValidationError("feature_part job requires a feature part.")
        validate_feature_part(job.part)
    elif job.kind == "primitive_part":
        if not isinstance(job.part, PrimitivePart):
            raise ValidationError("primitive_part job requires a primitive part.")
        validate_primitive_part(job.part)
    else:
        raise ValidationError(f"Unsupported job kind: {job.kind}.")
