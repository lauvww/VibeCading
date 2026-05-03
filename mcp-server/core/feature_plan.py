from __future__ import annotations

import copy
import math
from typing import Any


_BASE_BODY_FEATURE_ID = "拉伸_底板"
_BASE_TOP_FACE_ALIASES = {
    "",
    "base",
    "base_top_face",
    "top_face",
    "target_face",
    "to_be_selected",
    "same_hole_layout",
}
_TARGETABLE_FEATURE_KINDS = {
    "hole",
    "hole_pattern",
    "threaded_hole",
    "countersink",
    "counterbore",
    "obround_slot",
    "slot_or_pocket",
    "boss",
    "rib",
    "groove",
}


def _operation(operation_id: str, operation_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": operation_id,
        "type": operation_type,
        "parameters": parameters,
    }


def _profile_segment(profile: str, index: int) -> dict[str, Any]:
    return {
        "type": "profile_segment",
        "profile": profile,
        "index": index,
    }


def _fixed_point(point_id: str) -> dict[str, Any]:
    return {
        "type": "point",
        "id": point_id,
    }


def _circle_center(circle_id: str) -> dict[str, Any]:
    return {
        "type": "circle_center",
        "circle": circle_id,
    }


def _centerline_point(centerline_id: str, point: str) -> dict[str, Any]:
    return {
        "type": "centerline_point",
        "id": centerline_id,
        "point": point,
    }


def _profile_edge(profile: str, edge: str) -> dict[str, Any]:
    return {
        "type": "profile_edge",
        "profile": profile,
        "edge": edge,
    }


def feature_plan_to_dict(
    *,
    request: str,
    strategy: dict[str, Any],
    dominant_geometry: str,
    features: list[dict[str, Any]],
    parameters: dict[str, Any],
    engineering_context: dict[str, Any] | None = None,
    questions: list[str] | None = None,
    warnings: list[str] | None = None,
    missing_capabilities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "version": "feature_plan.v1",
        "source": "natural_language",
        "request": request,
        "units": "mm",
        "dominant_geometry": dominant_geometry,
        "strategy": {
            "chosen_strategy": strategy.get("chosen_strategy"),
            "selection_reason": strategy.get("selection_reason"),
            "alternatives_considered": list(strategy.get("alternatives_considered", [])),
        },
        "engineering_context": engineering_context
        or {
            "part_roles": [],
            "working_context": [],
            "mating_interfaces": [],
            "manufacturing_intent": [],
            "semantic_assumptions": [],
        },
        "features": features,
        "parameters": parameters,
        "questions": questions or [],
        "warnings": warnings or [],
        "missing_capabilities": missing_capabilities or [],
    }


def _segment_dimensions(profile: str, points: list[list[float]], prefix: str) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    last_index = len(points) - 1
    for index in range(last_index):
        start = points[index]
        end = points[index + 1]
        dx = abs(end[0] - start[0])
        dy = abs(end[1] - start[1])
        if dx <= 1e-9 and dy <= 1e-9:
            continue
        if index == last_index - 1:
            continue
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        if dx >= dy:
            position = [mid_x, max(start[1], end[1]) + 8]
        else:
            offset = -12 if start[0] <= 0 else 8
            position = [start[0] + offset, mid_y]
        dimensions.append(
            {
                "id": f"{prefix}段{index + 1}尺寸",
                "type": "entity",
                "entity": _profile_segment(profile, index),
                "position": position,
            }
        )
    return dimensions


def _anchor_dimensions(profile: str, point_id: str, axis_index: int, x_position: float, y_position: float) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{point_id}到左端",
            "type": "horizontal_between",
            "first": _fixed_point(point_id),
            "second": _profile_segment(profile, 0),
            "position": [x_position, y_position + 6],
        },
        {
            "id": f"{point_id}到轴线",
            "type": "vertical_between",
            "first": _fixed_point(point_id),
            "second": _profile_segment(profile, axis_index),
            "position": [x_position + 8, y_position],
        },
    ]


def _outer_profile_points(parameters: dict[str, Any]) -> list[list[float]]:
    total_length = float(parameters["total_length"])
    outer_radius = float(parameters["outer_diameter"]) / 2
    left_diameter = parameters.get("left_diameter")
    right_diameter = parameters.get("right_diameter")
    left_length = parameters.get("left_length")
    right_length = parameters.get("right_length")

    if left_diameter is None or right_diameter is None or left_length is None or right_length is None:
        return [
            [0, 0],
            [0, outer_radius],
            [total_length, outer_radius],
            [total_length, 0],
        ]

    left_radius = float(left_diameter) / 2
    right_radius = float(right_diameter) / 2
    left_end = float(left_length)
    right_start = total_length - float(right_length)
    points = [
        [0, 0],
        [0, left_radius],
        [left_end, left_radius],
        [left_end, outer_radius],
        [right_start, outer_radius],
        [right_start, right_radius],
        [total_length, right_radius],
        [total_length, 0],
    ]
    compacted: list[list[float]] = []
    for point in points:
        if not compacted or compacted[-1] != point:
            compacted.append(point)
    return compacted


def _compile_rotational_operations(feature_plan: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = dict(feature_plan["parameters"])
    total_length = float(parameters["total_length"])
    outer_radius = float(parameters["outer_diameter"]) / 2
    outer_sketch = "外形旋转草图"
    outer_profile = "外形旋转截面"
    outer_anchor = "外形定位点"
    outer_points = _outer_profile_points(parameters)
    axis_index = len(outer_points) - 1
    operations = [
        _operation("开始_外形旋转草图", "start_sketch", {"sketch": outer_sketch, "plane": "front"}),
        _operation("外形旋转截面", "add_polyline", {"sketch": outer_sketch, "points": outer_points, "closed": True}),
        _operation("外形定位点", "add_point", {"sketch": outer_sketch, "point": [total_length / 2, outer_radius / 2]}),
        _operation("外形截面水平垂直约束", "add_axis_constraints", {"profile": outer_profile}),
        _operation("外形定位点固定", "add_relation", {"entity": _fixed_point(outer_anchor), "relation": "fixed"}),
        _operation(
            "外形截面尺寸",
            "add_dimensions",
            {
                "dimensions": _segment_dimensions(outer_profile, outer_points, "外形")
                + _anchor_dimensions(
                    outer_profile,
                    outer_anchor,
                    axis_index,
                    total_length / 2,
                    outer_radius / 2,
                )
            },
        ),
        _operation("检查_外形旋转草图完全定义", "validate_fully_constrained", {"sketch": outer_sketch}),
        _operation(
            "旋转_外形成型",
            "revolve",
            {
                "sketch": outer_sketch,
                "axis": _profile_segment(outer_profile, axis_index),
                "angle": 360,
            },
        ),
    ]

    groove_features = [
        feature
        for feature in feature_plan["features"]
        if feature.get("kind") == "groove"
        and feature.get("method") == "cut_revolve"
        and not feature.get("required_parameters")
    ]

    center_bore = next(
        (
            feature
            for feature in feature_plan["features"]
            if feature.get("kind") == "hole" and feature.get("method") == "cut_revolve"
        ),
        None,
    )
    if center_bore is None and not groove_features:
        return operations

    if center_bore is not None:
        bore_diameter = center_bore["parameters"].get("diameter")
        if bore_diameter is not None:
            bore_radius = float(bore_diameter) / 2
            bore_sketch = "中心孔旋转切除草图"
            bore_profile = "中心孔切除截面"
            bore_anchor = "中心孔定位点"
            bore_points = [
                [0, 0],
                [0, bore_radius],
                [total_length, bore_radius],
                [total_length, 0],
            ]
            bore_axis_index = 3
            operations.extend(
                [
                    _operation("开始_中心孔旋转切除草图", "start_sketch", {"sketch": bore_sketch, "plane": "front"}),
                    _operation("中心孔切除截面", "add_polyline", {"sketch": bore_sketch, "points": bore_points, "closed": True}),
                    _operation("中心孔定位点", "add_point", {"sketch": bore_sketch, "point": [total_length / 2, bore_radius / 2]}),
                    _operation("中心孔截面水平垂直约束", "add_axis_constraints", {"profile": bore_profile}),
                    _operation("中心孔定位点固定", "add_relation", {"entity": _fixed_point(bore_anchor), "relation": "fixed"}),
                    _operation(
                        "中心孔切除尺寸",
                        "add_dimensions",
                        {
                            "dimensions": _segment_dimensions(bore_profile, bore_points, "中心孔")
                            + _anchor_dimensions(
                                bore_profile,
                                bore_anchor,
                                bore_axis_index,
                                total_length / 2,
                                bore_radius / 2,
                            )
                        },
                    ),
                    _operation("检查_中心孔旋转切除草图完全定义", "validate_fully_constrained", {"sketch": bore_sketch}),
                    _operation(
                        "旋转切除_中心孔",
                        "cut_revolve",
                        {
                            "sketch": bore_sketch,
                            "axis": _profile_segment(bore_profile, bore_axis_index),
                            "angle": 360,
                        },
                    ),
                ]
            )
    for index, feature in enumerate(groove_features, start=1):
        groove = dict(feature.get("parameters", {}))
        groove_width = float(groove["width"])
        bottom_radius = float(groove["bottom_diameter"]) / 2
        position = float(groove["position"])
        if bottom_radius >= outer_radius:
            raise ValueError("Groove bottom diameter must be smaller than outer diameter.")
        x0 = position - groove_width / 2
        x1 = position + groove_width / 2
        if x0 <= 0 or x1 >= total_length:
            raise ValueError("Groove position and width must stay inside the rotational body length.")
        groove_sketch = f"环形槽旋转切除草图{index}"
        groove_profile = f"环形槽切除截面{index}"
        groove_axis = f"环形槽旋转轴{index}"
        groove_anchor = f"环形槽定位点{index}"
        radial_clearance = max(outer_radius + 1, bottom_radius + 1)
        groove_points = [
            [x0, bottom_radius],
            [x0, radial_clearance],
            [x1, radial_clearance],
            [x1, bottom_radius],
        ]
        operations.extend(
            [
                _operation(f"开始_环形槽旋转切除草图{index}", "start_sketch", {"sketch": groove_sketch, "plane": "front"}),
                _operation(groove_axis, "add_centerline", {"sketch": groove_sketch, "start": [0, 0], "end": [total_length, 0]}),
                _operation(groove_profile, "add_polyline", {"sketch": groove_sketch, "points": groove_points, "closed": True}),
                _operation(groove_anchor, "add_point", {"sketch": groove_sketch, "point": [position, bottom_radius]}),
                _operation(f"环形槽截面水平垂直约束{index}", "add_axis_constraints", {"profile": groove_profile}),
                _operation(f"环形槽定位点固定{index}", "add_relation", {"entity": _fixed_point(groove_anchor), "relation": "fixed"}),
                _operation(
                    f"环形槽切除尺寸{index}",
                    "add_dimensions",
                    {
                        "dimensions": _segment_dimensions(groove_profile, groove_points + [groove_points[0]], "环形槽")
                        + [
                            {
                                "id": f"环形槽{index}_距左端",
                                "type": "horizontal_between",
                                "first": _fixed_point(groove_anchor),
                                "second": _profile_segment(groove_profile, 0),
                                "position": [position / 2, bottom_radius - 8],
                            },
                            {
                                "id": f"环形槽{index}_底径",
                                "type": "vertical_between",
                                "first": _fixed_point(groove_anchor),
                                "second": {"type": "centerline", "id": groove_axis},
                                "position": [position + 8, bottom_radius / 2],
                            },
                        ]
                    },
                ),
                _operation(f"检查_环形槽旋转切除草图{index}", "validate_fully_constrained", {"sketch": groove_sketch}),
                _operation(
                    f"旋转切除_环形槽{index}",
                    "cut_revolve",
                    {
                        "sketch": groove_sketch,
                        "axis": {"type": "centerline", "id": groove_axis},
                        "angle": 360,
                    },
                ),
            ]
        )
    return operations


def _base_rectangle_dimensions(profile: str, point_id: str, length: float, width: float, label: str = "底板") -> list[dict[str, Any]]:
    return [
        {
            "id": f"{label}长度",
            "type": "entity",
            "entity": _profile_edge(profile, "bottom"),
            "position": [0, -width / 2 - 12],
        },
        {
            "id": f"{label}宽度",
            "type": "entity",
            "entity": _profile_edge(profile, "left"),
            "position": [-length / 2 - 12, 0],
        },
        {
            "id": f"{label}中心到左边",
            "type": "horizontal_between",
            "first": _fixed_point(point_id),
            "second": _profile_edge(profile, "left"),
            "position": [-length / 4, 10],
        },
        {
            "id": f"{label}中心到底边",
            "type": "vertical_between",
            "first": _fixed_point(point_id),
            "second": _profile_edge(profile, "bottom"),
            "position": [10, -width / 4],
        },
    ]


def _hole_dimensions(hole: dict[str, Any], origin_id: str) -> list[dict[str, Any]]:
    hole_id = str(hole["id"])
    center_x, center_y = [float(item) for item in hole["center"]]
    dimensions: list[dict[str, Any]] = [
        {
            "id": f"{hole_id}_孔径",
            "type": "entity",
            "entity": {
                "type": "circle",
                "id": hole_id,
            },
            "position": [center_x + float(hole["diameter"]), center_y + float(hole["diameter"])],
        }
    ]
    if abs(center_x) > 1e-9:
        dimensions.append(
            {
                "id": f"{hole_id}_x定位",
                "type": "horizontal_between",
                "first": _fixed_point(origin_id),
                "second": _circle_center(hole_id),
                "position": [center_x / 2, center_y - 8],
            }
        )
    if abs(center_y) > 1e-9:
        dimensions.append(
            {
                "id": f"{hole_id}_y定位",
                "type": "vertical_between",
                "first": _fixed_point(origin_id),
                "second": _circle_center(hole_id),
                "position": [center_x + 8, center_y / 2],
            }
        )
    return dimensions


def _slot_centers(feature: dict[str, Any], plate_length: float, plate_width: float) -> list[list[float]]:
    parameters = dict(feature.get("parameters", {}))
    count = int(parameters.get("count") or 1)
    slot_length = float(parameters["length"])
    slot_width = float(parameters["width"])
    angle = float(parameters.get("angle") or 0)
    spacing = parameters.get("spacing")
    if count == 1:
        centers = [[0.0, 0.0]]
    elif count == 2:
        slot_spacing = float(spacing) if spacing is not None else max(slot_width * 3, min(plate_width * 0.4, plate_width - slot_width * 3))
        if abs(angle - 90) <= 1e-9:
            centers = [[-slot_spacing / 2, 0.0], [slot_spacing / 2, 0.0]]
        else:
            centers = [[0.0, -slot_spacing / 2], [0.0, slot_spacing / 2]]
    else:
        raise ValueError("Obround slot compiler currently supports one or two slots without explicit coordinates.")

    half_length = slot_length / 2
    half_width = slot_width / 2
    for center_x, center_y in centers:
        if abs(angle - 90) <= 1e-9:
            x_extent = half_width
            y_extent = half_length
        else:
            x_extent = half_length
            y_extent = half_width
        if abs(center_x) + x_extent > plate_length / 2 or abs(center_y) + y_extent > plate_width / 2:
            raise ValueError("Obround slot default placement exceeds the base body boundary.")
    return centers


def _compile_obround_slot_operations(features: list[dict[str, Any]], *, length: float, width: float, thickness: float) -> list[dict[str, Any]]:
    slot_features = [
        feature
        for feature in features
        if feature.get("kind") == "obround_slot"
        and feature.get("method") == "cut_extrude"
        and not feature.get("required_parameters")
    ]
    if not slot_features:
        return []

    slot_sketch = "长圆孔切除草图"
    target = _feature_face_target(slot_features[0], "target_face", "sketch_plane")
    operations = [_operation("开始_长圆孔切除草图", "start_sketch_on_face", {"sketch": slot_sketch, "target": target})]
    slot_index = 1
    for feature in slot_features:
        parameters = dict(feature.get("parameters", {}))
        slot_length = float(parameters["length"])
        slot_width = float(parameters["width"])
        angle = float(parameters.get("angle") or 0)
        for center in _slot_centers(feature, length, width):
            operations.append(
                _operation(
                    f"调节长圆孔{slot_index}",
                    "add_straight_slot",
                    {
                        "sketch": slot_sketch,
                        "center": center,
                        "length": slot_length,
                        "width": slot_width,
                        "angle": angle,
                        "definition_mode": "dimensioned_geometry",
                        "fully_define": True,
                    },
                )
            )
            slot_index += 1
    operations.extend(
        [
            _operation("检查_长圆孔切除草图完全定义", "validate_fully_constrained", {"sketch": slot_sketch}),
            _operation(
                "拉伸切除_长圆孔",
                "cut_extrude",
                {
                    "sketch": slot_sketch,
                    "depth": thickness + 2,
                    "reverse_direction": False,
                    "feature_metadata": {
                        "kind": "obround_slot",
                        **_target_resolution_metadata(slot_features[0], "target_face", "sketch_plane", resolved_target=target),
                    },
                },
            ),
        ]
    )
    return operations


def _top_face_target(feature_id: str = _BASE_BODY_FEATURE_ID) -> dict[str, Any]:
    return {
        "type": "body_face",
        "feature": feature_id,
        "normal": [0, 0, 1],
        "position": "max",
        "area": "largest",
        "area_rank": 0,
    }


def _bottom_face_target(feature_id: str = _BASE_BODY_FEATURE_ID) -> dict[str, Any]:
    return {
        "type": "body_face",
        "feature": feature_id,
        "normal": [0, 0, -1],
        "position": "max",
        "area": "largest",
        "area_rank": 0,
    }


def _side_face_targets(feature_id: str = _BASE_BODY_FEATURE_ID) -> list[dict[str, Any]]:
    return [
        {"type": "body_face", "feature": feature_id, "normal": [1, 0, 0], "position": "max", "area": "largest", "area_rank": 0},
        {"type": "body_face", "feature": feature_id, "normal": [-1, 0, 0], "position": "max", "area": "largest", "area_rank": 0},
        {"type": "body_face", "feature": feature_id, "normal": [0, 1, 0], "position": "max", "area": "largest", "area_rank": 0},
        {"type": "body_face", "feature": feature_id, "normal": [0, -1, 0], "position": "max", "area": "largest", "area_rank": 0},
    ]


def _rotational_front_end_face_target(feature_id: str = "旋转_外形成型") -> dict[str, Any]:
    return {
        "type": "body_face",
        "feature": feature_id,
        "normal": [-1, 0, 0],
        "position": "max",
        "area": "largest",
        "area_rank": 0,
    }


def _rotational_back_end_face_target(feature_id: str = "旋转_外形成型") -> dict[str, Any]:
    return {
        "type": "body_face",
        "feature": feature_id,
        "normal": [1, 0, 0],
        "position": "max",
        "area": "largest",
        "area_rank": 0,
    }


def _face_target_from_reference(reference: object | None, *, default_feature_id: str = _BASE_BODY_FEATURE_ID) -> dict[str, Any]:
    if reference is None:
        return _top_face_target(default_feature_id)
    if isinstance(reference, dict):
        target_type = str(reference.get("type", "body_face")).lower()
        if target_type in {"body_face", "named_face"}:
            return copy.deepcopy(reference)
        if target_type in {"top_face", "base_top_face"}:
            return _top_face_target(str(reference.get("feature") or default_feature_id))
        if target_type in {"bottom_face", "base_bottom_face"}:
            return _bottom_face_target(str(reference.get("feature") or default_feature_id))
        feature_id = reference.get("feature") or reference.get("feature_id")
        if feature_id:
            target = _top_face_target(str(feature_id))
            for key in ("normal", "position", "area", "area_rank", "min_dot", "position_tolerance"):
                if key in reference:
                    target[key] = copy.deepcopy(reference[key])
            return target
        return _top_face_target(default_feature_id)

    reference_text = str(reference).strip()
    normalized = reference_text.lower()
    if normalized in _BASE_TOP_FACE_ALIASES:
        return _top_face_target(default_feature_id)
    if normalized in {"bottom_face", "base_bottom_face"}:
        return _bottom_face_target(default_feature_id)
    if normalized.startswith("named_face:"):
        name = reference_text.split(":", 1)[1].strip()
        return {"type": "named_face", "name": name}
    if normalized.startswith("feature:"):
        feature_id = reference_text.split(":", 1)[1].strip()
        return _top_face_target(feature_id or default_feature_id)
    return {"type": "named_face", "name": reference_text}


def _feature_reference(feature: dict[str, Any], *keys: str) -> object | None:
    references = feature.get("references", {})
    if not isinstance(references, dict):
        return None
    for key in keys:
        value = references.get(key)
        if value is not None:
            return value
    return None


def _feature_face_target(feature: dict[str, Any], *keys: str) -> dict[str, Any]:
    reference = _feature_reference(feature, "resolved_target", *keys)
    return _face_target_from_reference(reference)


def _target_resolution_metadata(feature: dict[str, Any], *keys: str, resolved_target: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = {
        "original_target_reference": _feature_reference(feature, "original_target_reference", *keys),
        "target_face": _feature_reference(feature, *keys),
        "resolved_target": resolved_target or _feature_reference(feature, "resolved_target"),
        "target_inference_reason": _feature_reference(feature, "target_inference_reason"),
        "target_inference_confidence": _feature_reference(feature, "target_inference_confidence"),
        "target_assumption": _feature_reference(feature, "target_assumption"),
    }
    return metadata


def _merge_target_metadata(target_metadata: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(extra)
    merged.update(target_metadata)
    return merged


def _reference_registry_add(
    registry: dict[str, list[dict[str, Any]]],
    semantic: str,
    target: dict[str, Any],
    *,
    source_feature_id: str,
    source_kind: str,
    source_functional_role: str = "",
) -> None:
    registry.setdefault(semantic, []).append(
        {
            "semantic": semantic,
            "target": copy.deepcopy(target),
            "source_feature_id": source_feature_id,
            "source_kind": source_kind,
            "source_functional_role": source_functional_role,
        }
    )


def _predicted_feature_ids(feature_plan: dict[str, Any]) -> dict[str, dict[int, str]]:
    ids: dict[str, dict[int, str]] = {"slot_or_pocket": {}, "boss": {}, "rib": {}}
    pocket_index = 0
    boss_rib_index = 0
    for feature in feature_plan.get("features", []):
        if feature.get("required_parameters"):
            continue
        kind = str(feature.get("kind", ""))
        if kind == "slot_or_pocket":
            pocket_index += 1
            ids["slot_or_pocket"][pocket_index] = f"拉伸切除_口袋{pocket_index}"
        elif kind in {"boss", "rib"}:
            boss_rib_index += 1
            if kind == "boss":
                ids["boss"][boss_rib_index] = f"拉伸_凸台{boss_rib_index}"
            else:
                ids["rib"][boss_rib_index] = f"拉伸_加强筋{boss_rib_index}"
    return ids


def _build_reference_registry(feature_plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    registry: dict[str, list[dict[str, Any]]] = {}
    dominant_geometry = str(feature_plan.get("dominant_geometry", ""))
    features = list(feature_plan.get("features", []))
    predicted_ids = _predicted_feature_ids(feature_plan)

    if dominant_geometry == "prismatic":
        _reference_registry_add(registry, "base_top_face", _top_face_target(), source_feature_id=_BASE_BODY_FEATURE_ID, source_kind="base_body", source_functional_role="mounting_plate_body")
        _reference_registry_add(registry, "mounting_face", _top_face_target(), source_feature_id=_BASE_BODY_FEATURE_ID, source_kind="base_body", source_functional_role="mounting_plate_body")
        _reference_registry_add(registry, "base_bottom_face", _bottom_face_target(), source_feature_id=_BASE_BODY_FEATURE_ID, source_kind="base_body", source_functional_role="mounting_plate_body")
        for target in _side_face_targets():
            _reference_registry_add(registry, "base_side_faces", target, source_feature_id=_BASE_BODY_FEATURE_ID, source_kind="base_body", source_functional_role="mounting_plate_body")

        pocket_index = 0
        boss_rib_index = 0
        for feature in features:
            if feature.get("required_parameters"):
                continue
            kind = str(feature.get("kind", ""))
            if kind == "slot_or_pocket":
                pocket_index += 1
                feature_id = predicted_ids["slot_or_pocket"][pocket_index]
                _reference_registry_add(registry, "pocket_floor_face", _top_face_target(feature_id), source_feature_id=feature_id, source_kind=kind, source_functional_role=str(feature.get("functional_role", "")))
                opening_target = _feature_face_target(feature, "resolved_target", "target_face", "sketch_plane")
                _reference_registry_add(registry, "pocket_opening_face", opening_target, source_feature_id=feature_id, source_kind=kind, source_functional_role=str(feature.get("functional_role", "")))
            elif kind in {"boss", "rib"}:
                boss_rib_index += 1
                feature_id = predicted_ids[kind][boss_rib_index]
                target = _feature_face_target(feature, "resolved_target", "target_face", "supporting_faces", "sketch_plane")
                if kind == "boss":
                    _reference_registry_add(registry, "boss_top_face", _top_face_target(feature_id), source_feature_id=feature_id, source_kind=kind, source_functional_role=str(feature.get("functional_role", "")))
                    _reference_registry_add(
                        registry,
                        "boss_axis",
                        {"type": "feature_axis", "feature": feature_id},
                        source_feature_id=feature_id,
                        source_kind=kind,
                        source_functional_role=str(feature.get("functional_role", "")),
                    )
                else:
                    _reference_registry_add(registry, "rib_support_face", target, source_feature_id=feature_id, source_kind=kind, source_functional_role=str(feature.get("functional_role", "")))
            elif kind in {"hole", "hole_pattern"}:
                target = _feature_face_target(feature, "resolved_target", "target_face", "sketch_plane")
                _reference_registry_add(registry, "hole_entry_face", target, source_feature_id="拉伸切除_安装孔", source_kind=kind, source_functional_role=str(feature.get("functional_role", "")))
                _reference_registry_add(
                    registry,
                    "hole_axis",
                    {"type": "hole_axis", "feature": "拉伸切除_安装孔"},
                    source_feature_id="拉伸切除_安装孔",
                    source_kind=kind,
                    source_functional_role=str(feature.get("functional_role", "")),
                )
            elif kind in {"threaded_hole", "countersink", "counterbore"} and _feature_uses_hole_wizard(feature):
                feature_id = f"孔向导_{feature.get('id', kind)}"
                target = _feature_face_target(feature, "resolved_target", "target_face", "sketch_plane")
                _reference_registry_add(registry, "hole_entry_face", target, source_feature_id=feature_id, source_kind=kind, source_functional_role=str(feature.get("functional_role", "")))
                _reference_registry_add(
                    registry,
                    "hole_axis",
                    {"type": "hole_axis", "feature": feature_id},
                    source_feature_id=feature_id,
                    source_kind=kind,
                    source_functional_role=str(feature.get("functional_role", "")),
                )

    elif dominant_geometry == "rotational":
        _reference_registry_add(registry, "rotational_front_end_face", _rotational_front_end_face_target(), source_feature_id="旋转_外形成型", source_kind="base_body", source_functional_role="stepped_rotational_body")
        _reference_registry_add(registry, "rotational_back_end_face", _rotational_back_end_face_target(), source_feature_id="旋转_外形成型", source_kind="base_body", source_functional_role="stepped_rotational_body")
        _reference_registry_add(
            registry,
            "revolve_axis",
            {"type": "revolve_axis", "feature": "旋转_外形成型"},
            source_feature_id="旋转_外形成型",
            source_kind="base_body",
            source_functional_role="stepped_rotational_body",
        )
    return registry


def build_feature_plan_reference_registry(feature_plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    resolved_plan = resolve_feature_plan_references(feature_plan)
    return copy.deepcopy(_build_reference_registry(resolved_plan))


def _is_placeholder_reference(reference: object | None) -> bool:
    if reference is None:
        return True
    if isinstance(reference, dict):
        target_type = str(reference.get("type", "")).lower()
        if target_type in {"body_face", "named_face"}:
            return False
        if target_type in {"top_face", "base_top_face", "bottom_face", "base_bottom_face"}:
            return True
        feature_id = reference.get("feature") or reference.get("feature_id")
        return not bool(feature_id)
    normalized = str(reference).strip().lower()
    return normalized in _BASE_TOP_FACE_ALIASES or normalized in {"bottom_face", "base_bottom_face", "supporting_faces"}


def _single_registry_target(
    registry: dict[str, list[dict[str, Any]]],
    semantic: str,
    *,
    confidence: float,
    reason: str,
    assumption: str | None,
    ambiguous_question: str,
) -> dict[str, Any]:
    candidates = list(registry.get(semantic, []))
    if not candidates:
        return {"target": None, "questions": [], "reason": reason, "confidence": confidence, "assumption": assumption}
    if len(candidates) > 1:
        return {"target": None, "questions": [ambiguous_question], "reason": reason, "confidence": 0.0, "assumption": assumption}
    return {
        "target": copy.deepcopy(candidates[0]["target"]),
        "questions": [],
        "reason": reason,
        "confidence": confidence,
        "assumption": assumption,
    }


def _registry_candidate_matches_selector(candidate: dict[str, Any], selector: dict[str, Any]) -> bool:
    if not isinstance(selector, dict):
        return False
    feature_id = str(selector.get("id", "")).strip()
    kind = str(selector.get("kind", "")).strip()
    functional_role = str(selector.get("functional_role", "")).strip()
    if feature_id and str(candidate.get("source_feature_id", "")).strip() != feature_id:
        return False
    if kind and str(candidate.get("source_kind", "")).strip() != kind:
        return False
    candidate_role = str(candidate.get("source_functional_role", "")).strip()
    if functional_role and candidate_role and candidate_role != functional_role:
        return False
    return True


def _structured_registry_target(
    registry: dict[str, list[dict[str, Any]]],
    semantic: str,
    *,
    selector: dict[str, Any] | None = None,
    confidence: float,
    reason: str,
    ambiguous_question: str,
) -> dict[str, Any]:
    candidates = list(registry.get(semantic, []))
    if selector:
        filtered = [candidate for candidate in candidates if _registry_candidate_matches_selector(candidate, selector)]
        if filtered:
            candidates = filtered
    if not candidates:
        return {"target": None, "questions": [], "reason": reason, "confidence": confidence, "assumption": None}
    if len(candidates) > 1:
        return {"target": None, "questions": [ambiguous_question], "reason": reason, "confidence": 0.0, "assumption": None}
    return {
        "target": copy.deepcopy(candidates[0]["target"]),
        "questions": [],
        "reason": reason,
        "confidence": confidence,
        "assumption": None,
    }


def _resolve_target_from_semantics(
    feature: dict[str, Any],
    feature_plan: dict[str, Any],
    registry: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    request_text = str(feature_plan.get("request", "")).lower()
    kind = str(feature.get("kind", ""))
    functional_role = str(feature.get("functional_role", ""))
    references = dict(feature.get("references", {}))
    hole_like_kinds = {"hole", "hole_pattern", "threaded_hole", "countersink", "counterbore"}
    if kind not in _TARGETABLE_FEATURE_KINDS:
        return {"target": None, "questions": [], "reason": "", "confidence": 0.0, "assumption": None}

    target_semantic = str(references.get("target_semantic", "")).strip()
    host_selector = references.get("host_feature_selector")
    if target_semantic:
        return _structured_registry_target(
            registry,
            target_semantic,
            selector=host_selector if isinstance(host_selector, dict) else None,
            confidence=0.94,
            reason="structured_target_semantic_reference",
            ambiguous_question=f"当前零件里有多个候选 {target_semantic}，无法仅凭现有上下文确定目标。",
        )

    if isinstance(host_selector, dict):
        host_kind = str(host_selector.get("kind", "")).strip().lower()
        semantic_by_host_kind = {
            "boss": "boss_top_face",
            "slot_or_pocket": "pocket_floor_face",
            "rib": "rib_support_face",
        }
        inferred_semantic = semantic_by_host_kind.get(host_kind)
        if inferred_semantic:
            return _structured_registry_target(
                registry,
                inferred_semantic,
                selector=host_selector,
                confidence=0.88,
                reason="structured_host_feature_selector_reference",
                ambiguous_question=f"当前零件里有多个候选 {inferred_semantic}，无法仅凭 host feature selector 确定目标。",
            )

    if kind in hole_like_kinds and ("凸台上" in request_text or "凸台顶部" in request_text or "凸台顶面" in request_text):
        return _single_registry_target(
            registry,
            "boss_top_face",
            confidence=0.92,
            reason="single_boss_top_face_inferred_from_request",
            assumption=None,
            ambiguous_question="已有多个凸台，无法判断这个追加特征应该落在哪个凸台上。",
        )

    if kind in hole_like_kinds and ("口袋底部" in request_text or "口袋底" in request_text):
        return _single_registry_target(
            registry,
            "pocket_floor_face",
            confidence=0.92,
            reason="single_pocket_floor_face_inferred_from_request",
            assumption=None,
            ambiguous_question="已有多个口袋底部可选，无法判断这个追加特征应该落在哪个口袋底部。",
        )

    if "侧面" in request_text and kind in {"hole", "hole_pattern", "threaded_hole", "countersink", "counterbore", "obround_slot", "slot_or_pocket"}:
        side_candidates = registry.get("base_side_faces", [])
        if len(side_candidates) != 1:
            return {
                "target": None,
                "questions": ["当前零件存在多个侧面，无法仅根据“侧面”自动判断追加特征应该落在哪个侧面。"],
                "reason": "side_face_ambiguous",
                "confidence": 0.0,
                "assumption": None,
            }

    if "安装面" in request_text:
        mounting_candidates = registry.get("mounting_face", [])
        if len(mounting_candidates) != 1:
            return {
                "target": None,
                "questions": ["“安装面”在当前零件里可能对应多个面，请补充方向或目标特征。"],
                "reason": "mounting_face_ambiguous",
                "confidence": 0.0,
                "assumption": None,
            }
        return {
            "target": copy.deepcopy(mounting_candidates[0]["target"]),
            "questions": [],
            "reason": "single_mounting_face_inferred_from_request",
            "confidence": 0.78,
            "assumption": "inferred_mounting_face",
        }

    if kind == "groove" and str(feature.get("method", "")) == "cut_revolve":
        end_face = None
        if "端面" in request_text:
            front_faces = registry.get("rotational_front_end_face", [])
            if len(front_faces) == 1:
                end_face = copy.deepcopy(front_faces[0]["target"])
        return {
            "target": end_face,
            "questions": [],
            "reason": "rotational_feature_uses_revolve_axis",
            "confidence": 1.0,
            "assumption": "revolve_axis_for_rotational_groove",
        }

    if functional_role in {"fastener_hole_pattern", "through_hole_feature", "center_clearance_or_mounting_hole", "general_hole_pattern"} or kind in {
        "hole",
        "hole_pattern",
        "threaded_hole",
        "countersink",
        "counterbore",
        "obround_slot",
        "slot_or_pocket",
        "boss",
        "rib",
    }:
        default_semantic = "base_top_face"
        if "底部" in request_text and functional_role == "fastener_hole_pattern":
            default_semantic = "base_bottom_face"
        resolved = _single_registry_target(
            registry,
            default_semantic,
            confidence=0.58,
            reason="single_main_function_face_default",
            assumption=f"inferred_default_{default_semantic}",
            ambiguous_question="当前零件没有唯一明确的主功能面，无法自动决定追加特征应落在哪个面上。",
        )
        if resolved["target"] is not None:
            return resolved

    return {
        "target": None,
        "questions": [],
        "reason": "no_target_inference_rule_matched",
        "confidence": 0.0,
        "assumption": None,
    }


def resolve_feature_plan_references(
    feature_plan: dict[str, Any],
    additional_registry: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    resolved_plan = copy.deepcopy(feature_plan)
    features = list(resolved_plan.get("features", []))
    registry = _build_reference_registry(resolved_plan)
    if additional_registry:
        for semantic, candidates in additional_registry.items():
            if semantic not in registry:
                registry[semantic] = []
            registry[semantic].extend(copy.deepcopy(candidates))
    questions = list(resolved_plan.get("questions", []))

    for feature in features:
        kind = str(feature.get("kind", ""))
        if kind not in _TARGETABLE_FEATURE_KINDS:
            continue
        references = feature.setdefault("references", {})
        original_reference = _feature_reference(feature, "target_face", "supporting_faces", "base_hole", "sketch_plane")
        references["original_target_reference"] = copy.deepcopy(original_reference)
        if not _is_placeholder_reference(original_reference):
            references["resolved_target"] = _face_target_from_reference(original_reference)
            references["target_inference_reason"] = "explicit_target_reference"
            references["target_inference_confidence"] = 1.0
            references["target_assumption"] = None
            continue

        existing_resolved_target = references.get("resolved_target")
        if isinstance(existing_resolved_target, dict) and existing_resolved_target:
            references["target_inference_reason"] = str(
                references.get("target_inference_reason", "preserved_resolved_target")
            )
            references["target_inference_confidence"] = float(
                references.get("target_inference_confidence", 1.0)
            )
            references["target_assumption"] = references.get("target_assumption")
            continue

        resolution = _resolve_target_from_semantics(feature, resolved_plan, registry)
        if resolution["questions"]:
            questions.extend(item for item in resolution["questions"] if item not in questions)
            continue
        if resolution["target"] is not None:
            references["resolved_target"] = resolution["target"]
        references["target_inference_reason"] = resolution["reason"]
        references["target_inference_confidence"] = resolution["confidence"]
        references["target_assumption"] = resolution["assumption"]

    resolved_plan["features"] = features
    resolved_plan["questions"] = questions
    return resolved_plan


def _circle_cut_dimensions(circle_id: str, origin_id: str, center: list[float], diameter: float) -> list[dict[str, Any]]:
    return _hole_dimensions({"id": circle_id, "center": center, "diameter": diameter}, origin_id)


def _point_position_dimensions(point_id: str, origin_id: str, center: list[float], prefix: str) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    center_x = float(center[0])
    center_y = float(center[1])
    if abs(center_x) > 1e-9:
        dimensions.append(
            {
                "id": f"{prefix}_x定位",
                "type": "horizontal_between",
                "first": _fixed_point(origin_id),
                "second": _fixed_point(point_id),
                "position": [center_x / 2, center_y + 10],
            }
        )
    if abs(center_y) > 1e-9:
        dimensions.append(
            {
                "id": f"{prefix}_y定位",
                "type": "vertical_between",
                "first": _fixed_point(origin_id),
                "second": _fixed_point(point_id),
                "position": [center_x + 10, center_y / 2],
            }
        )
    return dimensions


def _axis_locator_operations(
    target: dict[str, Any],
    *,
    sketch: str,
    origin_id: str,
    center: list[float],
    prefix: str,
) -> list[dict[str, Any]]:
    center_x = float(center[0])
    center_y = float(center[1])
    if abs(center_x) <= 1e-9 and abs(center_y) <= 1e-9:
        return [
            _operation(
                f"{prefix}中心重合原点",
                "add_relation",
                {"entities": [_fixed_point(origin_id), target], "relation": "coincident"},
            )
        ]
    if abs(center_y) <= 1e-9:
        axis_line_id = f"{prefix}中心水平定位辅助线"
        return [
            _operation(axis_line_id, "add_centerline", {"sketch": sketch, "start": [0, 0], "end": [center_x, 0]}),
            _operation(
                f"{prefix}水平定位线起点重合",
                "add_relation",
                {"entities": [_fixed_point(origin_id), _centerline_point(axis_line_id, "start")], "relation": "coincident"},
            ),
            _operation(
                f"{prefix}水平定位线终点重合",
                "add_relation",
                {"entities": [target, _centerline_point(axis_line_id, "end")], "relation": "coincident"},
            ),
            _operation(f"{prefix}水平定位线约束", "add_relation", {"entity": {"type": "centerline", "id": axis_line_id}, "relation": "horizontal"}),
        ]
    if abs(center_x) <= 1e-9:
        axis_line_id = f"{prefix}中心竖直定位辅助线"
        return [
            _operation(axis_line_id, "add_centerline", {"sketch": sketch, "start": [0, 0], "end": [0, center_y]}),
            _operation(
                f"{prefix}竖直定位线起点重合",
                "add_relation",
                {"entities": [_fixed_point(origin_id), _centerline_point(axis_line_id, "start")], "relation": "coincident"},
            ),
            _operation(
                f"{prefix}竖直定位线终点重合",
                "add_relation",
                {"entities": [target, _centerline_point(axis_line_id, "end")], "relation": "coincident"},
            ),
            _operation(f"{prefix}竖直定位线约束", "add_relation", {"entity": {"type": "centerline", "id": axis_line_id}, "relation": "vertical"}),
        ]
    return []


def _point_zero_coordinate_relations(point_id: str, origin_id: str, center: list[float], prefix: str, sketch: str) -> list[dict[str, Any]]:
    return _axis_locator_operations(_fixed_point(point_id), sketch=sketch, origin_id=origin_id, center=center, prefix=prefix)


def _circle_zero_coordinate_relations(circle_id: str, origin_id: str, center: list[float], prefix: str, sketch: str) -> list[dict[str, Any]]:
    return _axis_locator_operations(_circle_center(circle_id), sketch=sketch, origin_id=origin_id, center=center, prefix=prefix)


def _compile_circle_cut_operations(
    *,
    sketch: str,
    operation_prefix: str,
    holes: list[dict[str, Any]],
    diameter: float,
    depth: float,
    reverse_direction: bool,
    draft_angle: float | None = None,
    draft_outward: bool = False,
    hole_metadata: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    origin_id = f"{operation_prefix}定位原点"
    face_target = copy.deepcopy(target) if target is not None else _top_face_target()
    operations = [
        _operation(f"开始_{operation_prefix}草图", "start_sketch_on_face", {"sketch": sketch, "target": face_target}),
        _operation(origin_id, "add_point", {"sketch": sketch, "point": [0, 0]}),
    ]
    position_operations: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    for index, hole in enumerate(holes, start=1):
        center = [float(item) for item in hole["center"]]
        circle_id = f"{operation_prefix}{index}"
        operations.append(
            _operation(
                circle_id,
                "add_circle",
                {
                    "sketch": sketch,
                    "center": center,
                    "diameter": diameter,
                },
            )
        )
        position_operations.extend(_circle_zero_coordinate_relations(circle_id, origin_id, center, circle_id, sketch))
        dimensions.extend(_circle_cut_dimensions(circle_id, origin_id, center, diameter))
    operations.append(_operation(f"{operation_prefix}定位原点固定", "add_relation", {"entity": _fixed_point(origin_id), "relation": "fixed"}))
    operations.extend(position_operations)
    cut_parameters: dict[str, Any] = {
        "sketch": sketch,
        "depth": depth,
        "reverse_direction": reverse_direction,
    }
    if draft_angle is not None:
        cut_parameters["draft_angle"] = draft_angle
        cut_parameters["draft_outward"] = draft_outward
    if hole_metadata:
        cut_parameters["hole_metadata"] = hole_metadata
    operations.extend(
        [
            _operation(f"{operation_prefix}尺寸", "add_dimensions", {"dimensions": dimensions}),
            _operation(f"检查_{operation_prefix}草图完全定义", "validate_fully_constrained", {"sketch": sketch}),
            _operation(f"拉伸切除_{operation_prefix}", "cut_extrude", cut_parameters),
        ]
    )
    return operations


def _feature_uses_hole_wizard(feature: dict[str, Any]) -> bool:
    parameters = dict(feature.get("parameters", {}))
    return str(feature.get("method", "")).lower() == "hole_wizard" or bool(parameters.get("use_hole_wizard", False))


def _hole_wizard_size(parameters: dict[str, Any], holes: list[dict[str, Any]]) -> str:
    size_label = parameters.get("size_label")
    if size_label is not None:
        return str(size_label).strip()
    size = parameters.get("size") or parameters.get("thread_size") or parameters.get("nominal_size")
    if size is None and holes:
        size = holes[0].get("nominal_size") or holes[0].get("diameter")
    if size is None:
        raise ValueError("Hole Wizard operation needs size or nominal_size.")
    if isinstance(size, str):
        normalized = size.strip()
        if str(parameters.get("hole_type", "")).lower() == "simple":
            return normalized
        return normalized if normalized.upper().startswith("M") else f"M{normalized}"
    if str(parameters.get("hole_type", "")).lower() == "simple":
        return f"{float(size):g}"
    return f"M{float(size):g}"


def _hole_wizard_diameter(kind: str, parameters: dict[str, Any], holes: list[dict[str, Any]]) -> float:
    if kind in {"threaded_hole", "threaded", "tapped"} and parameters.get("tap_drill_diameter") is not None:
        return float(parameters["tap_drill_diameter"])
    if parameters.get("clearance_diameter") is not None:
        return float(parameters["clearance_diameter"])
    if parameters.get("diameter") is not None:
        return float(parameters["diameter"])
    if holes:
        return float(holes[0].get("finished_diameter") or holes[0]["diameter"])
    nominal = parameters.get("thread_size") or parameters.get("nominal_size")
    if nominal is None:
        raise ValueError("Hole Wizard operation needs a diameter or nominal size.")
    return float(nominal)


def _compile_hole_wizard_operation(feature: dict[str, Any], holes: list[dict[str, Any]], *, thickness: float) -> dict[str, Any]:
    if not holes:
        raise ValueError("Hole Wizard operation needs at least one hole location.")
    kind = str(feature.get("kind", "")).lower()
    parameters = dict(feature.get("parameters", {}))
    hole_type_by_kind = {
        "hole": "clearance",
        "hole_pattern": "clearance",
        "countersink": "countersink",
        "counterbore": "counterbore",
        "threaded_hole": "threaded",
    }
    hole_type = str(parameters.get("hole_type") or hole_type_by_kind.get(kind, "clearance")).lower()
    diameter = _hole_wizard_diameter(kind, parameters, holes)
    end_condition = str(parameters.get("end_condition") or ("blind" if kind == "threaded_hole" else "through_all")).lower()
    depth = parameters.get("thread_depth") or parameters.get("drill_depth") or parameters.get("depth")
    if depth is None:
        depth = thickness + 2 if end_condition in {"through", "through_all"} else thickness
    target = _feature_face_target(feature, "target_face", "sketch_plane")

    operation_parameters: dict[str, Any] = {
        "target": target,
        "locations": [
            {
                "id": str(hole.get("id", f"孔{i}")),
                "center": [float(item) for item in hole["center"]],
            }
            for i, hole in enumerate(holes, start=1)
        ],
        "hole_type": hole_type,
        "standard": parameters.get("hole_wizard_standard", "iso"),
        "size": _hole_wizard_size(parameters, holes),
        "diameter": diameter,
        "depth": float(depth),
        "end_condition": end_condition,
        "holes": holes,
        "hole_metadata": {
            "kind": kind,
            "nominal_size": parameters.get("nominal_size") or parameters.get("thread_size") or (holes[0].get("nominal_size") if holes else None),
            "clearance_diameter": parameters.get("clearance_diameter") or diameter,
            "clearance_class": parameters.get("clearance_class"),
            "standard": parameters.get("standard"),
            "callout": parameters.get("callout"),
            "holes": holes,
            **_target_resolution_metadata(feature, "target_face", "sketch_plane", resolved_target=target),
        },
    }
    if kind == "counterbore":
        operation_parameters.update(
            {
                "counterbore_diameter": float(parameters["head_diameter"]),
                "counterbore_depth": float(parameters["seat_depth"]),
            }
        )
    elif kind == "countersink":
        operation_parameters.update(
            {
                "countersink_diameter": float(parameters["head_diameter"]),
                "countersink_angle": float(parameters.get("seat_angle") or 90),
                "counterbore_depth": float(parameters["seat_depth"]),
            }
        )
    elif kind == "threaded_hole":
        operation_parameters.update(
            {
                "thread_size": parameters.get("thread_size"),
                "thread_pitch": parameters.get("thread_pitch"),
                "thread_depth": float(parameters["thread_depth"]),
                "drill_depth": float(parameters.get("drill_depth") or depth),
                "tap_drill_diameter": float(parameters["tap_drill_diameter"]),
                "thread_standard": parameters.get("thread_standard"),
                "thread_metadata": {
                    "thread_size": parameters.get("thread_size"),
                    "thread_standard": parameters.get("thread_standard"),
                    "thread_pitch": parameters.get("thread_pitch"),
                    "thread_depth": parameters.get("thread_depth"),
                    "drill_depth": parameters.get("drill_depth"),
                    "tap_drill_diameter": parameters.get("tap_drill_diameter"),
                    "thread_modeling": "solidworks_hole_wizard",
                    "callout": parameters.get("callout"),
                    "holes": holes,
                    **_target_resolution_metadata(feature, "target_face", "sketch_plane", resolved_target=target),
                },
            }
        )
    return _operation(f"孔向导_{feature.get('id', kind)}", "hole_wizard", operation_parameters)


def _compile_hole_treatment_operations(features: list[dict[str, Any]], holes: list[dict[str, Any]], *, thickness: float) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    if not holes:
        return operations
    for feature in features:
        if feature.get("required_parameters"):
            continue
        kind = str(feature.get("kind"))
        if kind not in {"countersink", "counterbore", "threaded_hole"}:
            continue
        parameters = dict(feature.get("parameters", {}))
        if _feature_uses_hole_wizard(feature):
            operations.append(_compile_hole_wizard_operation(feature, holes, thickness=thickness))
            continue
        if kind in {"countersink", "counterbore"}:
            target = _feature_face_target(feature, "target_face", "base_hole", "sketch_plane")
            draft_angle = None
            if kind == "countersink":
                base_diameter = float(parameters.get("clearance_diameter") or parameters["nominal_size"])
                head_diameter = float(parameters["head_diameter"])
                seat_depth = float(parameters["seat_depth"])
                radial_delta = max((head_diameter - base_diameter) / 2, 0.0)
                draft_angle = math.degrees(math.atan(radial_delta / seat_depth)) if seat_depth > 0 and radial_delta > 0 else None
            operations.extend(
                _compile_circle_cut_operations(
                    sketch="沉头沉孔座切除草图" if kind == "countersink" else "沉孔座切除草图",
                    operation_prefix="沉头座" if kind == "countersink" else "沉孔座",
                    holes=holes,
                    diameter=float(parameters["head_diameter"]),
                    depth=float(parameters["seat_depth"]),
                    reverse_direction=False,
                    draft_angle=draft_angle,
                    draft_outward=False,
                    hole_metadata={
                        "kind": kind,
                        "nominal_size": parameters.get("nominal_size"),
                        "clearance_diameter": parameters.get("clearance_diameter"),
                        "clearance_class": parameters.get("clearance_class"),
                        "head_diameter": parameters.get("head_diameter"),
                        "seat_depth": parameters.get("seat_depth"),
                        "seat_angle": parameters.get("seat_angle"),
                        "standard": parameters.get("standard"),
                        "callout": parameters.get("callout"),
                        "holes": holes,
                        **_target_resolution_metadata(feature, "target_face", "base_hole", "sketch_plane", resolved_target=target),
                    },
                    target=target,
                )
            )
        elif kind == "threaded_hole":
            target = _feature_face_target(feature, "target_face", "base_hole", "sketch_plane")
            operations.extend(
                _compile_circle_cut_operations(
                    sketch="螺纹底孔切除草图",
                    operation_prefix="螺纹底孔",
                    holes=holes,
                    diameter=float(parameters["tap_drill_diameter"]),
                    depth=float(parameters["thread_depth"]),
                    reverse_direction=False,
                    target=target,
                )
            )
            operations[-1]["parameters"]["thread_metadata"] = {
                "thread_size": parameters.get("thread_size"),
                "thread_standard": parameters.get("thread_standard"),
                "thread_pitch": parameters.get("thread_pitch"),
                "thread_depth": parameters.get("thread_depth"),
                "drill_depth": parameters.get("drill_depth"),
                "tap_drill_diameter": parameters.get("tap_drill_diameter"),
                "thread_modeling": parameters.get("thread_modeling"),
                "callout": parameters.get("callout"),
                "holes": holes,
                **_target_resolution_metadata(feature, "target_face", "base_hole", "sketch_plane", resolved_target=target),
            }
    return operations


def _compile_slot_or_pocket_operations(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    pocket_features = [feature for feature in features if feature.get("kind") == "slot_or_pocket"]
    for index, feature in enumerate(pocket_features, start=1):
        if feature.get("required_parameters"):
            continue
        parameters = dict(feature.get("parameters", {}))
        pocket_length = float(parameters["length"])
        pocket_width = float(parameters["width"])
        pocket_depth = float(parameters["depth"])
        center = [float(item) for item in parameters.get("center", [0, 0])]
        target = _feature_face_target(feature, "target_face", "sketch_plane")
        sketch = f"口袋切除草图{index}"
        profile = f"口袋轮廓{index}"
        anchor = f"口袋中心点{index}"
        origin = f"口袋定位原点{index}"
        dimensions = _base_rectangle_dimensions(profile, anchor, pocket_length, pocket_width, f"口袋{index}")
        dimensions.extend(_point_position_dimensions(anchor, origin, center, f"口袋{index}"))
        position_relations = [_operation(f"口袋定位原点固定{index}", "add_relation", {"entity": _fixed_point(origin), "relation": "fixed"})]
        position_relations.extend(_point_zero_coordinate_relations(anchor, origin, center, f"口袋{index}", sketch))
        operations.extend(
            [
                _operation(f"开始_口袋切除草图{index}", "start_sketch_on_face", {"sketch": sketch, "target": target}),
                _operation(origin, "add_point", {"sketch": sketch, "point": [0, 0]}),
                _operation(profile, "add_center_rectangle", {"sketch": sketch, "center": center, "size": [pocket_length, pocket_width]}),
                _operation(anchor, "add_point", {"sketch": sketch, "point": center}),
                _operation(f"口袋轮廓水平垂直约束{index}", "add_axis_constraints", {"profile": profile}),
                *position_relations,
                _operation(f"口袋尺寸{index}", "add_dimensions", {"dimensions": dimensions}),
                _operation(f"检查_口袋切除草图{index}", "validate_fully_constrained", {"sketch": sketch}),
                _operation(
                    f"拉伸切除_口袋{index}",
                    "cut_extrude",
                    {
                        "sketch": sketch,
                        "depth": pocket_depth,
                        "reverse_direction": False,
                        "draft_angle": parameters.get("draft_angle"),
                        "feature_metadata": {
                            "kind": feature.get("kind"),
                            "functional_role": feature.get("functional_role"),
                            "center": center,
                            "draft_angle": parameters.get("draft_angle"),
                            "corner_radius": parameters.get("corner_radius"),
                            **_target_resolution_metadata(feature, "target_face", "sketch_plane", resolved_target=target),
                        },
                    },
                ),
            ]
        )
    return operations


def _compile_boss_or_rib_operations(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    boss_or_rib_features = [feature for feature in features if feature.get("kind") in {"boss", "rib"}]
    for index, feature in enumerate(boss_or_rib_features, start=1):
        if feature.get("required_parameters"):
            continue
        kind = str(feature.get("kind"))
        parameters = dict(feature.get("parameters", {}))
        if kind == "boss":
            diameter = float(parameters["diameter"])
            height = float(parameters["height"])
            center = [float(item) for item in parameters.get("center", [0, 0])]
            target = _feature_face_target(feature, "target_face", "sketch_plane")
            sketch = f"凸台草图{index}"
            circle_id = f"凸台轮廓{index}"
            origin_id = f"凸台定位原点{index}"
            center_id = f"凸台中心点{index}"
            position_dimensions = _circle_cut_dimensions(circle_id, origin_id, center, diameter)
            center_relations = [_operation(f"凸台定位原点固定{index}", "add_relation", {"entity": _fixed_point(origin_id), "relation": "fixed"})]
            center_relations.extend(_point_zero_coordinate_relations(center_id, origin_id, center, f"凸台{index}", sketch))
            operations.extend(
                [
                    _operation(f"开始_凸台草图{index}", "start_sketch_on_face", {"sketch": sketch, "target": target}),
                    _operation(origin_id, "add_point", {"sketch": sketch, "point": [0, 0]}),
                    _operation(center_id, "add_point", {"sketch": sketch, "point": center}),
                    _operation(circle_id, "add_circle", {"sketch": sketch, "center": center, "diameter": diameter}),
                    _operation(
                        f"凸台中心重合{index}",
                        "add_relation",
                        {"entities": [_fixed_point(center_id), _circle_center(circle_id)], "relation": "coincident"},
                    ),
                    *center_relations,
                    _operation(f"凸台尺寸{index}", "add_dimensions", {"dimensions": position_dimensions}),
                    _operation(f"检查_凸台草图{index}", "validate_fully_constrained", {"sketch": sketch}),
                    _operation(
                        f"拉伸_凸台{index}",
                        "extrude",
                        {
                            "sketch": sketch,
                            "depth": height,
                            "draft_angle": parameters.get("draft_angle"),
                            "feature_metadata": {
                                "kind": "boss",
                                "functional_role": feature.get("functional_role"),
                                "center": center,
                                "draft_angle": parameters.get("draft_angle"),
                                "fillet_radius": parameters.get("fillet_radius"),
                                **_target_resolution_metadata(feature, "target_face", "sketch_plane", resolved_target=target),
                            },
                        },
                    ),
                ]
            )
        elif kind == "rib":
            rib_length = float(parameters["length"])
            rib_thickness = float(parameters["thickness"])
            rib_height = float(parameters["height"])
            center = [float(item) for item in parameters.get("center", [0, 0])]
            target = _feature_face_target(feature, "target_face", "supporting_faces", "sketch_plane")
            sketch = f"加强筋草图{index}"
            profile = f"加强筋轮廓{index}"
            anchor = f"加强筋中心点{index}"
            origin = f"加强筋定位原点{index}"
            dimensions = _base_rectangle_dimensions(profile, anchor, rib_length, rib_thickness, f"加强筋{index}")
            dimensions.extend(_point_position_dimensions(anchor, origin, center, f"加强筋{index}"))
            position_relations = [_operation(f"加强筋定位原点固定{index}", "add_relation", {"entity": _fixed_point(origin), "relation": "fixed"})]
            position_relations.extend(_point_zero_coordinate_relations(anchor, origin, center, f"加强筋{index}", sketch))
            operations.extend(
                [
                    _operation(f"开始_加强筋草图{index}", "start_sketch_on_face", {"sketch": sketch, "target": target}),
                    _operation(origin, "add_point", {"sketch": sketch, "point": [0, 0]}),
                    _operation(profile, "add_center_rectangle", {"sketch": sketch, "center": center, "size": [rib_length, rib_thickness]}),
                    _operation(anchor, "add_point", {"sketch": sketch, "point": center}),
                    _operation(f"加强筋轮廓水平垂直约束{index}", "add_axis_constraints", {"profile": profile}),
                    *position_relations,
                    _operation(f"加强筋尺寸{index}", "add_dimensions", {"dimensions": dimensions}),
                    _operation(f"检查_加强筋草图{index}", "validate_fully_constrained", {"sketch": sketch}),
                    _operation(
                        f"拉伸_加强筋{index}",
                        "extrude",
                        {
                            "sketch": sketch,
                            "depth": rib_height,
                            "draft_angle": parameters.get("draft_angle"),
                            "feature_metadata": {
                                "kind": "rib",
                                "functional_role": feature.get("functional_role"),
                                "center": center,
                                "direction": parameters.get("direction"),
                                "draft_angle": parameters.get("draft_angle"),
                                "fillet_radius": parameters.get("fillet_radius"),
                                "supporting_faces": _feature_reference(feature, "supporting_faces", "target_face", "sketch_plane"),
                                **_target_resolution_metadata(feature, "supporting_faces", "target_face", "sketch_plane", resolved_target=target),
                            },
                        },
                    ),
                ]
            )
    return operations


def _compile_prismatic_operations(feature_plan: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = dict(feature_plan["parameters"])
    length = float(parameters["length"])
    width = float(parameters["width"])
    thickness = float(parameters["thickness"])
    base_sketch = "底板草图"
    base_profile = "底板轮廓"
    base_anchor = "底板中心点"
    operations = [
        _operation("开始_底板草图", "start_sketch", {"sketch": base_sketch, "plane": "base"}),
        _operation("底板轮廓", "add_center_rectangle", {"sketch": base_sketch, "center": [0, 0], "size": [length, width]}),
        _operation("底板中心点", "add_point", {"sketch": base_sketch, "point": [0, 0]}),
        _operation("底板轮廓水平垂直约束", "add_axis_constraints", {"profile": base_profile}),
        _operation("底板中心点固定", "add_relation", {"entity": _fixed_point(base_anchor), "relation": "fixed"}),
        _operation(
            "底板尺寸",
            "add_dimensions",
            {"dimensions": _base_rectangle_dimensions(base_profile, base_anchor, length, width)},
        ),
        _operation("检查_底板草图完全定义", "validate_fully_constrained", {"sketch": base_sketch}),
        _operation(_BASE_BODY_FEATURE_ID, "extrude", {"sketch": base_sketch, "depth": thickness}),
    ]

    hole_features = [
        feature
        for feature in feature_plan["features"]
        if feature.get("kind") in {"hole", "hole_pattern"} and not _feature_uses_hole_wizard(feature)
    ]
    hole_wizard_features = [
        feature
        for feature in feature_plan["features"]
        if feature.get("kind") in {"hole", "hole_pattern"} and _feature_uses_hole_wizard(feature)
    ]
    holes = [
        hole
        for feature in hole_features
        for hole in feature.get("parameters", {}).get("holes", [])
    ]
    layout_holes = list(parameters.get("holes", holes))
    operations.extend(_compile_slot_or_pocket_operations(feature_plan["features"]))
    operations.extend(_compile_boss_or_rib_operations(feature_plan["features"]))
    operations.extend(_compile_obround_slot_operations(feature_plan["features"], length=length, width=width, thickness=thickness))

    if holes:
        hole_sketch = "孔切除草图"
        origin_id = "孔定位原点"
        hole_target = _feature_face_target(hole_features[0], "target_face", "sketch_plane")
        operations.extend(
            [
                _operation("开始_孔切除草图", "start_sketch_on_face", {"sketch": hole_sketch, "target": hole_target}),
                _operation("孔定位原点", "add_point", {"sketch": hole_sketch, "point": [0, 0]}),
            ]
        )
        position_operations: list[dict[str, Any]] = []
        dimensions: list[dict[str, Any]] = []
        for hole in holes:
            operations.append(
                _operation(
                    str(hole["id"]),
                    "add_circle",
                    {
                        "sketch": hole_sketch,
                        "center": hole["center"],
                        "diameter": hole["diameter"],
                    },
                )
            )
            center_x, center_y = [float(item) for item in hole["center"]]
            position_operations.extend(_circle_zero_coordinate_relations(str(hole["id"]), origin_id, [center_x, center_y], str(hole["id"]), hole_sketch))
            dimensions.extend(_hole_dimensions(hole, origin_id))
        operations.append(_operation("孔定位原点固定", "add_relation", {"entity": _fixed_point(origin_id), "relation": "fixed"}))
        operations.extend(position_operations)
        operations.extend(
            [
                _operation("孔切除尺寸", "add_dimensions", {"dimensions": dimensions}),
                _operation("检查_孔切除草图完全定义", "validate_fully_constrained", {"sketch": hole_sketch}),
                _operation(
                    "拉伸切除_安装孔",
                    "cut_extrude",
                    {
                        "sketch": hole_sketch,
                        "depth": thickness + 2,
                        "reverse_direction": False,
                        "hole_metadata": {
                            "kind": "through_hole",
                            "holes": holes,
                            **_target_resolution_metadata(hole_features[0], "target_face", "sketch_plane", resolved_target=hole_target),
                        },
                    },
                ),
            ]
        )
    for feature in hole_wizard_features:
        feature_holes = list(feature.get("parameters", {}).get("holes", []))
        if feature_holes:
            operations.append(_compile_hole_wizard_operation(feature, feature_holes, thickness=thickness))
    operations.extend(
        _compile_hole_treatment_operations(
            feature_plan["features"],
            layout_holes,
            thickness=thickness,
        )
    )
    return operations


def compile_feature_plan_to_primitive_job(
    feature_plan: dict[str, Any],
    *,
    job_id: str,
    part_name: str,
    material: str,
    export_formats: list[str],
) -> dict[str, Any]:
    feature_plan = resolve_feature_plan_references(feature_plan)
    if feature_plan.get("questions") or feature_plan.get("missing_capabilities"):
        raise ValueError("Feature plan has unresolved questions or missing capabilities.")

    dominant_geometry = str(feature_plan.get("dominant_geometry", ""))
    if dominant_geometry == "rotational":
        operations = _compile_rotational_operations(feature_plan)
        source_kind = "feature_plan_rotational"
    elif dominant_geometry == "prismatic":
        operations = _compile_prismatic_operations(feature_plan)
        source_kind = "feature_plan_prismatic"
    else:
        raise ValueError(f"Unsupported feature plan dominant geometry: {dominant_geometry}")

    return {
        "job_id": job_id,
        "kind": "primitive_part",
        "backend": "auto",
        "units": str(feature_plan.get("units", "mm")),
        "part": {
            "name": part_name,
            "source_kind": source_kind,
            "material": material,
            "export_formats": export_formats,
            "operations": operations,
        },
    }
