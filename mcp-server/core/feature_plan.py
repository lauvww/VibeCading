from __future__ import annotations

import math
from typing import Any


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
    operations = [_operation("开始_长圆孔切除草图", "start_sketch", {"sketch": slot_sketch, "plane": "base"})]
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
                    "reverse_direction": True,
                },
            ),
        ]
    )
    return operations


def _top_face_target(feature_id: str = "拉伸_底板") -> dict[str, Any]:
    return {
        "type": "body_face",
        "feature": feature_id,
        "normal": [0, 0, 1],
        "position": "max",
        "area": "largest",
        "area_rank": 0,
    }


def _circle_cut_dimensions(circle_id: str, origin_id: str, center: list[float], diameter: float) -> list[dict[str, Any]]:
    return _hole_dimensions({"id": circle_id, "center": center, "diameter": diameter}, origin_id)


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
) -> list[dict[str, Any]]:
    origin_id = f"{operation_prefix}定位原点"
    operations = [
        _operation(f"开始_{operation_prefix}草图", "start_sketch_on_face", {"sketch": sketch, "target": _top_face_target()}),
        _operation(origin_id, "add_point", {"sketch": sketch, "point": [0, 0]}),
    ]
    coincident_entities: list[dict[str, Any]] = []
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
        if abs(center[0]) <= 1e-9 and abs(center[1]) <= 1e-9:
            coincident_entities.extend([_fixed_point(origin_id), _circle_center(circle_id)])
        dimensions.extend(_circle_cut_dimensions(circle_id, origin_id, center, diameter))
    operations.append(_operation(f"{operation_prefix}定位原点固定", "add_relation", {"entity": _fixed_point(origin_id), "relation": "fixed"}))
    if coincident_entities:
        operations.append(
            _operation(
                f"{operation_prefix}中心重合",
                "add_relation",
                {"entities": coincident_entities, "relation": "coincident"},
            )
        )
    cut_parameters: dict[str, Any] = {
        "sketch": sketch,
        "depth": depth,
        "reverse_direction": reverse_direction,
    }
    if draft_angle is not None:
        cut_parameters["draft_angle"] = draft_angle
        cut_parameters["draft_outward"] = draft_outward
    operations.extend(
        [
            _operation(f"{operation_prefix}尺寸", "add_dimensions", {"dimensions": dimensions}),
            _operation(f"检查_{operation_prefix}草图完全定义", "validate_fully_constrained", {"sketch": sketch}),
            _operation(f"拉伸切除_{operation_prefix}", "cut_extrude", cut_parameters),
        ]
    )
    return operations


def _compile_hole_treatment_operations(features: list[dict[str, Any]], holes: list[dict[str, Any]], *, thickness: float) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    if not holes:
        return operations
    for feature in features:
        if feature.get("required_parameters"):
            continue
        kind = str(feature.get("kind"))
        parameters = dict(feature.get("parameters", {}))
        if kind in {"countersink", "counterbore"}:
            draft_angle = None
            if kind == "countersink":
                nominal_size = float(parameters["nominal_size"])
                head_diameter = float(parameters["head_diameter"])
                seat_depth = float(parameters["seat_depth"])
                radial_delta = max((head_diameter - nominal_size) / 2, 0.0)
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
                )
            )
        elif kind == "threaded_hole":
            operations.extend(
                _compile_circle_cut_operations(
                    sketch="螺纹底孔切除草图",
                    operation_prefix="螺纹底孔",
                    holes=holes,
                    diameter=float(parameters["tap_drill_diameter"]),
                    depth=float(parameters["thread_depth"]),
                    reverse_direction=False,
                )
            )
            operations[-1]["parameters"]["thread_metadata"] = {
                "thread_size": parameters.get("thread_size"),
                "thread_standard": parameters.get("thread_standard"),
                "thread_modeling": parameters.get("thread_modeling"),
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
        sketch = f"口袋切除草图{index}"
        profile = f"口袋轮廓{index}"
        anchor = f"口袋中心点{index}"
        operations.extend(
            [
                _operation(f"开始_口袋切除草图{index}", "start_sketch_on_face", {"sketch": sketch, "target": _top_face_target()}),
                _operation(profile, "add_center_rectangle", {"sketch": sketch, "center": [0, 0], "size": [pocket_length, pocket_width]}),
                _operation(anchor, "add_point", {"sketch": sketch, "point": [0, 0]}),
                _operation(f"口袋轮廓水平垂直约束{index}", "add_axis_constraints", {"profile": profile}),
                _operation(f"口袋中心点固定{index}", "add_relation", {"entity": _fixed_point(anchor), "relation": "fixed"}),
                _operation(f"口袋尺寸{index}", "add_dimensions", {"dimensions": _base_rectangle_dimensions(profile, anchor, pocket_length, pocket_width, f"口袋{index}")}),
                _operation(f"检查_口袋切除草图{index}", "validate_fully_constrained", {"sketch": sketch}),
                _operation(f"拉伸切除_口袋{index}", "cut_extrude", {"sketch": sketch, "depth": pocket_depth, "reverse_direction": False}),
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
            sketch = f"凸台草图{index}"
            circle_id = f"凸台轮廓{index}"
            origin_id = f"凸台中心点{index}"
            operations.extend(
                [
                    _operation(f"开始_凸台草图{index}", "start_sketch_on_face", {"sketch": sketch, "target": _top_face_target()}),
                    _operation(origin_id, "add_point", {"sketch": sketch, "point": [0, 0]}),
                    _operation(circle_id, "add_circle", {"sketch": sketch, "center": [0, 0], "diameter": diameter}),
                    _operation(f"凸台中心点固定{index}", "add_relation", {"entity": _fixed_point(origin_id), "relation": "fixed"}),
                    _operation(
                        f"凸台中心重合{index}",
                        "add_relation",
                        {"entities": [_fixed_point(origin_id), _circle_center(circle_id)], "relation": "coincident"},
                    ),
                    _operation(f"凸台尺寸{index}", "add_dimensions", {"dimensions": _circle_cut_dimensions(circle_id, origin_id, [0, 0], diameter)}),
                    _operation(f"检查_凸台草图{index}", "validate_fully_constrained", {"sketch": sketch}),
                    _operation(f"拉伸_凸台{index}", "extrude", {"sketch": sketch, "depth": height}),
                ]
            )
        elif kind == "rib":
            rib_length = float(parameters["length"])
            rib_thickness = float(parameters["thickness"])
            rib_height = float(parameters["height"])
            sketch = f"加强筋草图{index}"
            profile = f"加强筋轮廓{index}"
            anchor = f"加强筋中心点{index}"
            operations.extend(
                [
                    _operation(f"开始_加强筋草图{index}", "start_sketch_on_face", {"sketch": sketch, "target": _top_face_target()}),
                    _operation(profile, "add_center_rectangle", {"sketch": sketch, "center": [0, 0], "size": [rib_length, rib_thickness]}),
                    _operation(anchor, "add_point", {"sketch": sketch, "point": [0, 0]}),
                    _operation(f"加强筋轮廓水平垂直约束{index}", "add_axis_constraints", {"profile": profile}),
                    _operation(f"加强筋中心点固定{index}", "add_relation", {"entity": _fixed_point(anchor), "relation": "fixed"}),
                    _operation(f"加强筋尺寸{index}", "add_dimensions", {"dimensions": _base_rectangle_dimensions(profile, anchor, rib_length, rib_thickness, f"加强筋{index}")}),
                    _operation(f"检查_加强筋草图{index}", "validate_fully_constrained", {"sketch": sketch}),
                    _operation(f"拉伸_加强筋{index}", "extrude", {"sketch": sketch, "depth": rib_height}),
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
        _operation("拉伸_底板", "extrude", {"sketch": base_sketch, "depth": thickness}),
    ]

    hole_features = [
        feature
        for feature in feature_plan["features"]
        if feature.get("kind") in {"hole", "hole_pattern"} and feature.get("method") == "cut_extrude"
    ]
    holes = [
        hole
        for feature in hole_features
        for hole in feature.get("parameters", {}).get("holes", [])
    ]
    layout_holes = list(parameters.get("holes", holes))
    if holes:
        hole_sketch = "孔切除草图"
        origin_id = "孔定位原点"
        operations.extend(
            [
                _operation("开始_孔切除草图", "start_sketch", {"sketch": hole_sketch, "plane": "base"}),
                _operation("孔定位原点", "add_point", {"sketch": hole_sketch, "point": [0, 0]}),
            ]
        )
        coincident_entities: list[dict[str, Any]] = []
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
            if abs(center_x) <= 1e-9 and abs(center_y) <= 1e-9:
                coincident_entities.extend([_fixed_point(origin_id), _circle_center(str(hole["id"]))])
            dimensions.extend(_hole_dimensions(hole, origin_id))
        operations.append(_operation("孔定位原点固定", "add_relation", {"entity": _fixed_point(origin_id), "relation": "fixed"}))
        if coincident_entities:
            operations.append(
                _operation(
                    "中心孔与原点重合",
                    "add_relation",
                    {"entities": coincident_entities, "relation": "coincident"},
                )
            )
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
                        "reverse_direction": True,
                    },
                ),
            ]
        )
    operations.extend(
        _compile_hole_treatment_operations(
            feature_plan["features"],
            layout_holes,
            thickness=thickness,
        )
    )
    operations.extend(_compile_obround_slot_operations(feature_plan["features"], length=length, width=width, thickness=thickness))
    operations.extend(_compile_slot_or_pocket_operations(feature_plan["features"]))
    operations.extend(_compile_boss_or_rib_operations(feature_plan["features"]))
    return operations


def compile_feature_plan_to_primitive_job(
    feature_plan: dict[str, Any],
    *,
    job_id: str,
    part_name: str,
    material: str,
    export_formats: list[str],
) -> dict[str, Any]:
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
