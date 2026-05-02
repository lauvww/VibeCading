from __future__ import annotations

import hashlib
import re
from typing import Any

from core.feature_plan import compile_feature_plan_to_primitive_job, feature_plan_to_dict
from core.strategy_planner import plan_modeling_strategy_dict


NUMBER = r"(\d+(?:\.\d+)?)"


def _normalized_text(request: str) -> str:
    return request.replace("×", "x").replace("X", "x").lower()


def _first_number(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _all_numbers(pattern: str, text: str) -> list[float]:
    return [float(match.group(1)) for match in re.finditer(pattern, text, re.IGNORECASE)]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _contains_slot_word_outside_obround_dimensions(text: str) -> bool:
    if not _contains_any(text, ("槽", "口袋", "窗口", "避让")):
        return False
    if _contains_any(text, ("开槽", "调节槽", "避让槽", "密封槽", "导向槽", "槽口", "口袋", "窗口", "凹槽")):
        return True
    if _contains_any(text, ("长圆孔", "腰形孔")):
        stripped = text.replace("槽长", "").replace("槽宽", "")
        return "槽" in stripped
    return "槽" in text


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _stable_job_suffix(request: str) -> str:
    return hashlib.sha1(request.encode("utf-8")).hexdigest()[:8]


def _material_from_request(request: str, default: str = "") -> str:
    match = re.search(r"材料\s*[:：为是]?\s*([0-9A-Za-z#\-\u4e00-\u9fff]+)", request)
    if not match:
        return default
    return match.group(1)


def _feature_dimension(text: str, feature_keywords: tuple[str, ...], dimension_keywords: tuple[str, ...]) -> float | None:
    feature_pattern = "|".join(re.escape(keyword) for keyword in feature_keywords)
    dimension_pattern = "|".join(re.escape(keyword) for keyword in dimension_keywords)
    return _first_number(
        [
            rf"(?:{feature_pattern})[^，,。；;]{{0,24}}?(?:{dimension_pattern})\s*[:：为是]?\s*{NUMBER}",
            rf"(?:{dimension_pattern})\s*[:：为是]?\s*{NUMBER}[^，,。；;]{{0,24}}?(?:{feature_pattern})",
        ],
        text,
    )


def _slot_parameters_from_request(text: str) -> dict[str, Any]:
    return {
        "length": _feature_dimension(text, ("长圆孔", "腰形孔", "调节槽", "开槽", "避让槽", "口袋", "凹槽", "窗口", "槽"), ("槽长", "长度", "长")),
        "width": _feature_dimension(text, ("长圆孔", "腰形孔", "调节槽", "开槽", "避让槽", "口袋", "凹槽", "窗口", "槽"), ("槽宽", "宽度", "宽")),
        "depth": _feature_dimension(text, ("口袋", "凹槽", "避让槽", "窗口", "槽"), ("深度", "槽深", "深")),
        "count": _slot_count_from_request(text),
        "spacing": _feature_dimension(text, ("长圆孔", "腰形孔", "调节槽", "槽"), ("槽间距", "中心距", "间距")),
        "angle": _slot_angle_from_request(text),
    }


def _groove_parameters_from_request(text: str) -> dict[str, Any]:
    return {
        "width": _feature_dimension(text, ("环形槽", "退刀槽", "密封槽"), ("槽宽", "宽度", "宽")),
        "bottom_diameter": _feature_dimension(text, ("环形槽", "退刀槽", "密封槽"), ("槽底直径", "底径", "直径")),
        "position": _feature_dimension(text, ("环形槽", "退刀槽", "密封槽"), ("位置", "距左端", "距离")),
    }


def _slot_count_from_request(text: str) -> int:
    chinese_counts = {
        "一": 1,
        "一个": 1,
        "一条": 1,
        "单个": 1,
        "两": 2,
        "两个": 2,
        "两条": 2,
        "二": 2,
        "四": 4,
        "四个": 4,
        "四条": 4,
    }
    match = re.search(r"(\d+)\s*(?:个|条)?\s*(?:长圆孔|腰形孔|调节槽)", text)
    if match:
        return int(match.group(1))
    for label, count in chinese_counts.items():
        if f"{label}长圆孔" in text or f"{label}腰形孔" in text or f"{label}调节槽" in text:
            return count
    return 1


def _slot_angle_from_request(text: str) -> float:
    if _contains_any(text, ("竖向", "纵向", "沿y", "y方向", "上下调节")):
        return 90.0
    return 0.0


def _metric_tap_drill(thread_size: float | None) -> float | None:
    if thread_size is None:
        return None
    standard_sizes = {
        3.0: 2.5,
        4.0: 3.3,
        5.0: 4.2,
        6.0: 5.0,
        8.0: 6.8,
        10.0: 8.5,
        12.0: 10.2,
    }
    rounded = round(float(thread_size), 1)
    if rounded in standard_sizes:
        return standard_sizes[rounded]
    return round(float(thread_size) * 0.85, 2)


def _hole_treatment_defaults(text: str, *, is_countersink: bool) -> dict[str, Any]:
    nominal = _hole_diameter_from_request(text)
    head_diameter = _feature_dimension(
        text,
        ("沉头孔", "沉头", "沉孔"),
        ("头部直径", "沉头直径", "沉孔直径", "座孔直径", "大径"),
    )
    if head_diameter is None and nominal is not None:
        head_diameter = nominal * 2
    seat_angle = _feature_dimension(text, ("沉头孔", "沉头"), ("角度", "锥角"))
    if seat_angle is None and is_countersink:
        seat_angle = 90.0
    seat_depth = _feature_dimension(text, ("沉头孔", "沉头", "沉孔"), ("沉头深", "沉孔深", "深度", "深"))
    if seat_depth is None and nominal is not None and head_diameter is not None:
        if is_countersink:
            seat_depth = max((head_diameter - nominal) / 2, 0.5)
        else:
            seat_depth = max(nominal * 0.6, 1.0)
    return {
        "nominal_size": nominal,
        "head_diameter": head_diameter,
        "seat_depth": seat_depth,
        "seat_angle": seat_angle if is_countersink else None,
        "standard": "metric_clearance_default",
    }


def _threaded_hole_defaults(text: str) -> dict[str, Any]:
    thread_size = _hole_diameter_from_request(text)
    thread_depth = _feature_dimension(text, ("螺纹孔", "螺纹"), ("深度", "孔深", "螺纹深", "深"))
    return {
        "thread_size": thread_size,
        "thread_standard": "ISO metric coarse",
        "thread_depth": thread_depth,
        "tap_drill_diameter": _metric_tap_drill(thread_size),
        "thread_modeling": "tap_drill_geometry_with_thread_metadata",
    }


def _compile_ready_keyword(text: str, keyword: str) -> bool:
    if keyword in {"腰形孔", "长圆孔"}:
        params = _slot_parameters_from_request(text)
        return params.get("length") is not None and params.get("width") is not None
    if keyword in {"槽", "口袋", "窗口"}:
        params = _slot_parameters_from_request(text)
        return params.get("length") is not None and params.get("width") is not None and params.get("depth") is not None
    if keyword == "避让":
        params = _slot_parameters_from_request(text)
        has_position_strategy = _contains_any(text, ("中间", "中心", "居中"))
        return (
            params.get("length") is not None
            and params.get("width") is not None
            and params.get("depth") is not None
            and has_position_strategy
        )
    if keyword in {"沉头", "沉孔"}:
        defaults = _hole_treatment_defaults(text, is_countersink=keyword == "沉头")
        return all(defaults.get(name) is not None for name in ("nominal_size", "head_diameter", "seat_depth"))
    if keyword == "螺纹":
        defaults = _threaded_hole_defaults(text)
        return defaults.get("thread_size") is not None and defaults.get("thread_depth") is not None
    if keyword == "凸台":
        return _feature_dimension(text, ("凸台",), ("直径", "外径", "宽")) is not None and _feature_dimension(text, ("凸台",), ("高度", "高")) is not None
    if keyword in {"加强筋", "筋板"}:
        return (
            _feature_dimension(text, ("加强筋", "筋板"), ("长度", "长")) is not None
            and _feature_dimension(text, ("加强筋", "筋板"), ("厚度", "厚")) is not None
            and _feature_dimension(text, ("加强筋", "筋板"), ("高度", "高")) is not None
        )
    return False


def _infer_engineering_context(request: str, dominant_geometry: str) -> dict[str, Any]:
    text = _normalized_text(request)
    part_roles: list[str] = []
    working_context: list[str] = []
    mating_interfaces: list[str] = []
    manufacturing_intent: list[str] = []
    assumptions = ["units_mm"]

    if _contains_any(text, ("安装", "固定", "底板", "安装板", "支架")):
        part_roles.append("mounting_support")
        working_context.append("fixed_mounting")
        mating_interfaces.append("mounting_face")
    if "支架" in text:
        part_roles.append("support_bracket")
    if _contains_any(text, ("轴", "阶梯轴", "圆柱", "皮带轮", "旋钮")):
        part_roles.append("rotational_part")
        mating_interfaces.append("rotational_outer_surface")
        manufacturing_intent.append("lathe_like")
    if "垫圈" in text:
        part_roles.append("spacer_or_fastener_load_distribution")
        mating_interfaces.extend(["flat_clamping_face", "center_bore"])
        manufacturing_intent.append("lathe_like")
    if "法兰" in text:
        part_roles.append("flanged_connection")
        mating_interfaces.append("bolt_circle_or_flange_face")
    if _contains_any(text, ("孔", "螺栓", "螺钉", "安装孔", "通孔", "m3", "m4", "m5", "m6", "m8", "m10")):
        mating_interfaces.append("fastener_or_clearance_hole")
    if _contains_any(text, ("四角孔", "四个安装孔", "四角安装孔")) or ("四角" in text and "孔" in text):
        mating_interfaces.append("four_corner_fastener_pattern")
    if _contains_any(text, ("定位孔", "定位销", "销孔")):
        mating_interfaces.append("locating_pin_interface")
    if _contains_any(text, ("中心孔", "内孔", "内径")):
        mating_interfaces.append("center_bore")
    if _contains_any(text, ("轴承", "轴承座")):
        part_roles.append("bearing_support")
        working_context.append("bearing_mounting")
        mating_interfaces.append("bearing_seat")
    if _contains_any(text, ("密封", "密封槽")):
        part_roles.append("sealing")
        mating_interfaces.append("seal_groove_or_sealing_face")
    if _contains_any(text, ("退刀槽", "环形槽")):
        manufacturing_intent.append("turned_groove_or_relief")
    if _contains_any(text, ("导向", "滑动", "滑轨")):
        part_roles.append("guiding")
        working_context.append("sliding_or_guiding_motion")
    if _contains_any(text, ("调节", "张紧", "腰形孔", "长圆孔")):
        working_context.append("adjustable_mounting")
        mating_interfaces.append("adjustment_slot")
    if "沉头" in text:
        mating_interfaces.append("countersunk_fastener_interface")
    if "沉孔" in text:
        mating_interfaces.append("counterbored_fastener_interface")
    if _contains_any(text, ("螺纹", "螺纹孔")):
        mating_interfaces.append("threaded_fastener_interface")
    if _contains_any(text, ("加强筋", "筋板")):
        part_roles.append("reinforcement")
    if _contains_any(text, ("凸台", "boss")):
        mating_interfaces.append("boss_or_standoff_interface")
    if _contains_any(text, ("圆角", "倒角")):
        manufacturing_intent.append("edge_treatment")
    if _contains_any(text, ("风道", "管路", "过渡")):
        part_roles.append("flow_transition")
        working_context.append("fluid_or_air_path")
        mating_interfaces.append("inlet_outlet_sections")
    if dominant_geometry == "prismatic":
        manufacturing_intent.append("milled_or_plate_like")
    elif dominant_geometry == "rotational":
        manufacturing_intent.append("turning_or_axisymmetric")
    elif dominant_geometry == "multi_section_transition":
        manufacturing_intent.append("lofted_transition")

    if not part_roles:
        part_roles.append("unknown_part_role")
        assumptions.append("part_role_requires_user_alignment")
    if not mating_interfaces:
        assumptions.append("mating_interfaces_not_specified")

    return {
        "part_roles": _dedupe(part_roles),
        "working_context": _dedupe(working_context),
        "mating_interfaces": _dedupe(mating_interfaces),
        "manufacturing_intent": _dedupe(manufacturing_intent),
        "semantic_assumptions": _dedupe(assumptions),
    }


def _unsupported_feature_plan(
    request: str,
    *,
    strategy: dict[str, Any],
    questions: list[str],
    feature: str,
    needed_method: str,
    reason: str,
) -> dict[str, Any]:
    return feature_plan_to_dict(
        request=request,
        strategy=strategy,
        dominant_geometry=strategy.get("dominant_geometry", "unknown"),
        features=[],
        parameters={},
        engineering_context=_infer_engineering_context(
            request,
            str(strategy.get("dominant_geometry", "unknown")),
        ),
        questions=questions,
        missing_capabilities=[
            {
                "feature": feature,
                "needed_method": needed_method,
                "reason": reason,
            }
        ],
    )


def _parse_rotational_parameters(request: str) -> tuple[dict[str, Any], list[str], list[str]]:
    text = _normalized_text(request)
    questions: list[str] = []
    warnings: list[str] = []

    total_lengths = _all_numbers(r"(?:总长|全长|长度|长)\s*[:：为是]?\s*" + NUMBER, text)
    total_length = _first_number([r"(?:总长|全长)\s*[:：为是]?\s*" + NUMBER], text)
    if total_length is None and total_lengths:
        total_length = max(total_lengths)
    if total_length is None and _contains_any(
        text,
        ("垫圈", "法兰", "圆盘", "圆柱", "washer", "flange", "disk", "cylinder"),
    ):
        total_length = _first_number(
            [
                r"(?:厚度|(?<!槽)(?<!孔)厚|高度|(?<!槽)(?<!孔)高)\s*[:：为是]?\s*" + NUMBER,
            ],
            text,
        )

    diameters = _all_numbers(r"(?:最大直径|外径|直径|d|φ|Φ)\s*[:：为是]?\s*" + NUMBER, text)
    outer_diameter = _first_number(
        [
            r"(?:最大直径|最大外径|外径)\s*[:：为是]?\s*" + NUMBER,
            r"(?:直径|d|φ|Φ)\s*[:：为是]?\s*" + NUMBER,
        ],
        text,
    )
    if diameters:
        outer_diameter = max(diameters)

    left_segment = re.search(
        r"左段[^，,。；;]{0,18}?直径\s*[:：为是]?\s*" + NUMBER + r"[^，,。；;]{0,18}?(?:长度|长)\s*[:：为是]?\s*" + NUMBER,
        text,
        re.IGNORECASE,
    )
    right_segment = re.search(
        r"右段[^，,。；;]{0,18}?直径\s*[:：为是]?\s*" + NUMBER + r"[^，,。；;]{0,18}?(?:长度|长)\s*[:：为是]?\s*" + NUMBER,
        text,
        re.IGNORECASE,
    )

    left_diameter = float(left_segment.group(1)) if left_segment else None
    left_length = float(left_segment.group(2)) if left_segment else None
    right_diameter = float(right_segment.group(1)) if right_segment else None
    right_length = float(right_segment.group(2)) if right_segment else None

    bore_diameter = _first_number(
        [
            r"(?:内径)\s*[:：为是]?\s*" + NUMBER,
            r"(?:中心孔|通孔|内孔)[^，,。；;]{0,12}?(?:直径|孔径|d|φ|Φ)\s*[:：为是]?\s*" + NUMBER,
            r"(?:直径|孔径|d|φ|Φ)\s*[:：为是]?\s*" + NUMBER + r"[^，,。；;]{0,12}?(?:中心孔|通孔|内孔)",
        ],
        text,
    )

    if total_length is None:
        questions.append("阶梯轴需要总长，例如总长 120 mm。")
    if outer_diameter is None:
        questions.append("阶梯轴需要最大外径，例如最大直径 40 mm。")

    has_center_bore = any(keyword in text for keyword in ("中心孔", "通孔", "内孔"))
    if has_center_bore and bore_diameter is None:
        questions.append("中心孔需要孔径，例如中心孔直径 10 mm。")

    has_groove = _contains_any(text, ("环形槽", "退刀槽", "密封槽"))
    groove_params = _groove_parameters_from_request(text) if has_groove else None
    if has_groove:
        missing_groove = [
            name
            for name in ["width", "bottom_diameter", "position"]
            if (groove_params or {}).get(name) is None
        ]
        if missing_groove:
            warnings.append("已识别环形槽/退刀槽/密封槽，但缺少槽宽、槽底直径或距左端位置。")
            questions.append("环形槽/退刀槽/密封槽需要槽宽、槽底直径和距左端位置，才能生成可靠旋转切除草图。")

    if (
        total_length is not None
        and left_length is not None
        and right_length is not None
        and left_length + right_length >= total_length
    ):
        questions.append("左段长度和右段长度之和必须小于总长，才能形成中间台阶段。")

    if outer_diameter is not None:
        smallest_outer = min(
            value
            for value in [outer_diameter, left_diameter, right_diameter]
            if value is not None
        )
        if bore_diameter is not None and bore_diameter >= smallest_outer:
            questions.append("中心孔直径必须小于最小外径。")

    params = {
        "total_length": total_length,
        "outer_diameter": outer_diameter,
        "left_diameter": left_diameter,
        "left_length": left_length,
        "right_diameter": right_diameter,
        "right_length": right_length,
        "bore_diameter": bore_diameter,
        "groove": groove_params,
        "material": _material_from_request(request, default=""),
    }
    return params, questions, warnings


def _rotational_base_feature_semantics(request: str) -> dict[str, Any]:
    text = _normalized_text(request)
    if "垫圈" in text:
        functional_role = "spacer_or_fastener_load_distribution_body"
        feature_intent = "provide ring body with flat clamping faces"
        mating_interfaces = ["flat_clamping_face", "center_bore"]
    elif "法兰" in text:
        functional_role = "flanged_rotational_body"
        feature_intent = "provide axisymmetric flange or hub body"
        mating_interfaces = ["flange_face", "rotational_outer_surface"]
    elif "圆柱" in text:
        functional_role = "axisymmetric_base_body"
        feature_intent = "provide cylindrical body"
        mating_interfaces = ["rotational_outer_surface"]
    else:
        functional_role = "stepped_rotational_body"
        feature_intent = "provide shaft shoulders and axisymmetric main body"
        mating_interfaces = ["rotational_outer_surface", "shaft_axis"]
    return {
        "functional_role": functional_role,
        "feature_intent": feature_intent,
        "mating_interfaces": mating_interfaces,
        "modeling_method": {
            "command": "revolve",
            "reason": "Axisymmetric geometry is most editable as a constrained half-section revolved around one axis.",
        },
        "sketch_strategy": {
            "type": "half_section_closed_profile",
            "construction": "Draw the axial half-section on the front plane and revolve around the profile axis.",
            "driving_dimensions": ["total_length", "outer_diameter", "segment_lengths", "segment_diameters"],
            "constraint_policy": "axis-aligned dimensions plus one reference anchor; avoid fixing production geometry.",
        },
    }


def _center_bore_feature_semantics() -> dict[str, Any]:
    return {
        "functional_role": "center_bore_or_clearance_passage",
        "feature_intent": "create an axis-aligned through bore for clearance, mating, or weight reduction",
        "mating_interfaces": ["center_bore", "shaft_axis"],
        "modeling_method": {
            "command": "cut_revolve",
            "reason": "The bore is axisymmetric and should share the base revolve axis for stable edits.",
        },
        "sketch_strategy": {
            "type": "axisymmetric_cut_half_section",
            "construction": "Draw a rectangular half-section on the same revolve plane and cut around the base axis.",
            "driving_dimensions": ["bore_diameter", "total_length"],
            "constraint_policy": "constrain bore radius and axial extent from the same datum/axis as the base body.",
        },
    }


def _rotational_groove_feature_from_request(request: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
    text = _normalized_text(request)
    if not _contains_any(text, ("环形槽", "退刀槽", "密封槽")):
        return None
    if "密封槽" in text:
        functional_role = "seal_groove"
        feature_intent = "create an annular groove for sealing element placement"
        mating_interfaces = ["seal_groove_or_sealing_face"]
    elif "退刀槽" in text:
        functional_role = "relief_groove"
        feature_intent = "create a turning relief groove for machining clearance"
        mating_interfaces = ["turned_relief"]
    else:
        functional_role = "annular_groove"
        feature_intent = "create an axisymmetric groove around the part"
        mating_interfaces = ["rotational_outer_surface"]
    groove_params = parameters.get("groove") or {}
    missing = [
        name
        for name in ["width", "bottom_diameter", "position"]
        if groove_params.get(name) is None
    ]
    return {
        "id": functional_role,
        "kind": "groove",
        "method": "cut_revolve",
        "functional_role": functional_role,
        "feature_intent": feature_intent,
        "mating_interfaces": mating_interfaces,
        "modeling_method": {
            "command": "cut_revolve",
            "reason": "Annular grooves are axisymmetric subtractive features and are easiest to edit as revolved cuts.",
        },
        "sketch_strategy": {
            "type": "axisymmetric_groove_half_section",
            "construction": "Draw a groove half-section on the revolve plane with width, radial depth, and axial position dimensions.",
            "driving_dimensions": ["groove_width", "bottom_diameter", "axial_position"],
            "constraint_policy": "share the base revolve axis and dimension the groove from stable shaft datums.",
        },
        "parameters": groove_params,
        "required_parameters": missing,
        "references": {
            "axis": "same_as_base_revolve",
            "sketch_plane": "front",
        },
    }


def _rotational_feature_plan_from_request(
    request: str,
    *,
    strategy: dict[str, Any],
) -> dict[str, Any]:
    params, questions, warnings = _parse_rotational_parameters(request)
    features = [
        {
            "id": "回转主形体",
            "kind": "base_body",
            "method": "revolve",
            **_rotational_base_feature_semantics(request),
            "parameters": {
                "total_length": params["total_length"],
                "outer_diameter": params["outer_diameter"],
                "left_diameter": params["left_diameter"],
                "left_length": params["left_length"],
                "right_diameter": params["right_diameter"],
                "right_length": params["right_length"],
            },
            "references": {
                "sketch_plane": "front",
                "axis": "profile_axis",
            },
        }
    ]
    if params.get("bore_diameter") is not None:
        features.append(
            {
                "id": "贯穿中心孔",
                "kind": "hole",
                "method": "cut_revolve",
                **_center_bore_feature_semantics(),
                "parameters": {
                    "diameter": params["bore_diameter"],
                    "through": True,
                },
                "references": {
                    "axis": "same_as_base_revolve",
                    "sketch_plane": "front",
                },
            }
        )
    groove_feature = _rotational_groove_feature_from_request(request, params)
    if groove_feature is not None:
        features.append(groove_feature)
    missing_capabilities: list[dict[str, Any]] = []
    if groove_feature is not None and groove_feature.get("required_parameters"):
        groove_feature_name = str(groove_feature["functional_role"]) if groove_feature else "annular_groove"
        missing_capabilities.append(
            {
                "feature": groove_feature_name,
                "needed_method": "cut_revolve",
                "reason": "需要槽位置、槽宽和槽底直径后才能生成可靠旋转切除草图和编译规则。",
            }
        )
    feature_plan = feature_plan_to_dict(
        request=request,
        strategy=strategy,
        dominant_geometry="rotational",
        features=features,
        parameters=params,
        engineering_context=_infer_engineering_context(request, "rotational"),
        questions=questions,
        warnings=warnings,
        missing_capabilities=missing_capabilities,
    )
    return {
        "ready": not questions and not missing_capabilities,
        "questions": questions,
        "warnings": warnings,
        "feature_plan": feature_plan,
        "parsed_parameters": params,
    }


def _rotational_job_from_request(
    request: str,
    *,
    strategy: dict[str, Any],
    job_id: str | None,
    part_name: str | None,
    material: str | None,
    export_formats: list[str] | None,
) -> dict[str, Any]:
    draft = _rotational_feature_plan_from_request(request, strategy=strategy)
    feature_plan = draft["feature_plan"]
    params = draft["parsed_parameters"]
    warnings = draft["warnings"]
    if not draft["ready"]:
        return {
            "ready": False,
            "questions": draft["questions"],
            "warnings": warnings,
            "feature_plan": feature_plan,
            "job": None,
            "parsed_parameters": params,
        }

    selected_material = material or params["material"] or "45钢"
    if "垫圈" in request:
        name_stem = "自然语言垫圈"
    elif "法兰" in request:
        name_stem = "自然语言法兰"
    elif "圆柱" in request:
        name_stem = "自然语言圆柱"
    else:
        name_stem = "自然语言阶梯轴"
    selected_job_id = job_id or f"{name_stem}-{_stable_job_suffix(request)}"
    selected_part_name = part_name or name_stem
    selected_exports = export_formats or ["pdf", "svg", "step"]
    job = compile_feature_plan_to_primitive_job(
        feature_plan,
        job_id=selected_job_id,
        part_name=selected_part_name,
        material=selected_material,
        export_formats=selected_exports,
    )
    return {
        "ready": True,
        "questions": [],
        "warnings": warnings,
        "feature_plan": feature_plan,
        "job": job,
        "parsed_parameters": params,
    }


def _box_dimensions_from_request(text: str) -> tuple[float | None, float | None, float | None]:
    triple = re.search(
        NUMBER + r"\s*(?:x|\*)\s*" + NUMBER + r"\s*(?:x|\*)\s*" + NUMBER,
        text,
        re.IGNORECASE,
    )
    if triple:
        return float(triple.group(1)), float(triple.group(2)), float(triple.group(3))

    pair = re.search(NUMBER + r"\s*(?:x|\*)\s*" + NUMBER, text, re.IGNORECASE)
    length = float(pair.group(1)) if pair else None
    width = float(pair.group(2)) if pair else None
    thickness: float | None = None

    explicit_length = _first_number(
        [
            r"(?:板长|总长|长度|长边|(?<!槽)(?<!孔)长)\s*[:：为是]?\s*" + NUMBER,
        ],
        text,
    )
    explicit_width = _first_number(
        [
            r"(?:板宽|总宽|宽度|宽边|(?<!槽)(?<!孔)宽)\s*[:：为是]?\s*" + NUMBER,
        ],
        text,
    )
    explicit_thickness = _first_number(
        [
            r"(?:板厚|厚度|(?<!槽)(?<!孔)厚)\s*[:：为是]?\s*" + NUMBER,
        ],
        text,
    )

    return explicit_length or length, explicit_width or width, explicit_thickness or thickness


def _hole_diameter_from_request(text: str) -> float | None:
    metric = re.search(r"(?<![0-9A-Za-z])m\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if metric:
        return float(metric.group(1))
    return _first_number(
        [
            r"(?:孔径|孔直径)\s*[:：为是]?\s*" + NUMBER,
            r"(?:安装孔|螺栓孔|通孔|孔)[^，,。；;]{0,12}?(?:直径|孔径|d|φ|Φ)\s*[:：为是]?\s*" + NUMBER,
            r"(?:直径|孔径|d|φ|Φ)\s*[:：为是]?\s*" + NUMBER + r"[^，,。；;]{0,12}?(?:安装孔|螺栓孔|通孔|孔)",
        ],
        text,
    )


def _hole_layout_from_request(
    text: str,
    length: float,
    width: float,
    hole_diameter: float | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    questions: list[str] = []
    holes: list[dict[str, Any]] = []
    mentions_hole = _contains_any(text, ("孔", "m3", "m4", "m5", "m6", "m8", "m10", "hole"))
    if not mentions_hole or "无孔" in text:
        return holes, questions
    if _contains_any(text, ("腰形孔", "长圆孔")) and not _contains_any(
        text,
        ("中心孔", "中间孔", "四角孔", "安装孔", "螺栓孔", "定位孔", "销孔", "沉头孔", "沉孔", "螺纹孔", "通孔"),
    ):
        return holes, questions

    if hole_diameter is None:
        questions.append("板类孔特征需要孔径或螺纹规格，例如孔径 8 mm 或 M8。")
        return holes, questions

    has_center_hole = _contains_any(text, ("中心孔", "中间孔", "中心通孔", "中间通孔", "中心沉头孔", "中心沉孔", "中心螺纹孔"))
    if has_center_hole:
        holes.append({"id": "中心孔", "center": [0.0, 0.0], "diameter": hole_diameter})

    has_four_corner_holes = _contains_any(text, ("四角孔", "四个角", "4角孔", "四角安装孔", "四个安装孔", "四角沉头孔", "四角沉孔", "四角螺纹孔"))
    if has_four_corner_holes:
        pitch = re.search(
            r"(?:孔距|孔中心距|孔间距)\s*[:：为是]?\s*" + NUMBER + r"\s*(?:x|\*)\s*" + NUMBER,
            text,
            re.IGNORECASE,
        )
        if pitch:
            pitch_x = float(pitch.group(1))
            pitch_y = float(pitch.group(2))
            x_offset = pitch_x / 2
            y_offset = pitch_y / 2
        else:
            margin = _first_number(
                [
                    r"(?:孔边距|孔距边|距边|边距|离边)\s*[:：为是]?\s*" + NUMBER,
                ],
                text,
            )
            if margin is None:
                questions.append("四角孔需要孔边距或孔距，例如孔边距 12 mm，或孔距 100x60。")
                return holes, questions
            x_offset = length / 2 - margin
            y_offset = width / 2 - margin
        if x_offset <= hole_diameter / 2 or y_offset <= hole_diameter / 2:
            questions.append("四角孔位置与孔径冲突，孔中心到边缘距离必须大于孔半径。")
            return holes, questions
        holes.extend(
            [
                {"id": "左下孔", "center": [-x_offset, -y_offset], "diameter": hole_diameter},
                {"id": "右下孔", "center": [x_offset, -y_offset], "diameter": hole_diameter},
                {"id": "左上孔", "center": [-x_offset, y_offset], "diameter": hole_diameter},
                {"id": "右上孔", "center": [x_offset, y_offset], "diameter": hole_diameter},
            ]
        )

    if mentions_hole and not holes:
        questions.append("请说明孔的位置基准，例如中心孔、四角孔加孔边距，或四角孔加孔距。")

    return holes, questions


def _parse_prismatic_parameters(request: str) -> tuple[dict[str, Any], list[str], list[str]]:
    text = _normalized_text(request)
    questions: list[str] = []
    warnings: list[str] = []
    length, width, thickness = _box_dimensions_from_request(text)
    if length is None:
        questions.append("板类/块类零件需要长度，例如长 120 mm。")
    if width is None:
        questions.append("板类/块类零件需要宽度，例如宽 80 mm。")
    if thickness is None:
        questions.append("板类/块类零件需要厚度，例如厚 8 mm。")

    unsupported_keywords = {
        "槽": "槽/口袋类特征需要长度、宽度、深度和稳定定位基准。",
        "避让": "避让槽/避让切除需要轮廓、位置和作用对象。",
        "口袋": "口袋特征需要长度、宽度、深度和稳定定位基准。",
        "窗口": "窗口类切除需要轮廓尺寸、深度/贯穿方式和定位基准。",
        "圆角": "实体圆角或草图圆角暂未纳入第一版板类 Feature Plan 编译规则。",
        "倒角": "实体倒角或草图倒角暂未纳入第一版板类 Feature Plan 编译规则。",
        "沉头": "沉头孔需要孔规格、头部直径、沉头深度和孔位置。",
        "沉孔": "沉孔需要孔规格、沉孔直径、沉孔深度和孔位置。",
        "螺纹": "螺纹孔需要螺纹规格、深度、底孔策略和孔位置。",
        "腰形孔": "腰形孔需要槽长、槽宽和定位方式，暂未纳入第一版板类 Feature Plan 编译规则。",
        "长圆孔": "长圆孔需要槽长、槽宽和定位方式，暂未纳入第一版板类 Feature Plan 编译规则。",
        "加强筋": "加强筋需要长度、厚度、高度和依附面。",
        "筋板": "筋板需要长度、厚度、高度和依附面。",
        "凸台": "凸台需要轮廓尺寸、位置和高度。",
    }
    has_obround = _contains_any(text, ("腰形孔", "长圆孔"))
    slot_params = _slot_parameters_from_request(text) if has_obround else {}
    for keyword, message in unsupported_keywords.items():
        if keyword == "槽" and has_obround and not _contains_slot_word_outside_obround_dimensions(text):
            continue
        if _compile_ready_keyword(text, keyword):
            continue
        if keyword in text:
            warnings.append(message)
            questions.append(message)

    holes: list[dict[str, Any]] = []
    hole_diameter = _hole_diameter_from_request(text)
    if length is not None and width is not None:
        holes, hole_questions = _hole_layout_from_request(text, length, width, hole_diameter)
        questions.extend(hole_questions)

    params = {
        "length": length,
        "width": width,
        "thickness": thickness,
        "hole_diameter": hole_diameter,
        "holes": holes,
        "material": _material_from_request(request, default=""),
    }
    return params, questions, warnings


def _prismatic_base_feature_semantics(request: str) -> dict[str, Any]:
    text = _normalized_text(request)
    if "支架" in text:
        functional_role = "support_or_bracket_body"
        feature_intent = "provide the main support body and datum faces for later interfaces"
    elif _contains_any(text, ("安装板", "底板", "固定")):
        functional_role = "mounting_plate_body"
        feature_intent = "provide the primary mounting body and flat mounting faces"
    else:
        functional_role = "prismatic_base_body"
        feature_intent = "provide the main prismatic stock body"
    return {
        "functional_role": functional_role,
        "feature_intent": feature_intent,
        "mating_interfaces": ["mounting_face"] if "安装" in text or "固定" in text else [],
        "modeling_method": {
            "command": "extrude",
            "reason": "Plate and block-like geometry is clearest as one constrained closed profile extruded to thickness.",
        },
        "sketch_strategy": {
            "type": "centered_closed_rectangle",
            "construction": "Draw a centered rectangle on the base plane and drive it with length and width dimensions.",
            "driving_dimensions": ["length", "width", "thickness"],
            "constraint_policy": "use horizontal/vertical relations and driven center reference; avoid fixed production edges.",
        },
    }


def _hole_feature_semantics(request: str, holes: list[dict[str, Any]]) -> dict[str, Any]:
    text = _normalized_text(request)
    if _contains_any(text, ("定位孔", "定位销", "销孔")):
        functional_role = "locating_pin_interface"
        feature_intent = "locate mating parts with pin holes"
        mating_interfaces = ["locating_pin_interface"]
    elif len(holes) > 1 or _contains_any(text, ("安装孔", "螺栓", "螺钉", "四角孔", "四个安装孔")):
        functional_role = "fastener_hole_pattern"
        feature_intent = "provide bolt or screw clearance pattern for mounting"
        mating_interfaces = ["fastener_or_clearance_hole", "four_corner_fastener_pattern"]
    elif _contains_any(text, ("中心孔", "中间孔")):
        functional_role = "center_clearance_or_mounting_hole"
        feature_intent = "provide a centered through hole for clearance or mounting"
        mating_interfaces = ["center_bore", "fastener_or_clearance_hole"]
    else:
        functional_role = "through_hole_feature"
        feature_intent = "provide through-hole geometry"
        mating_interfaces = ["fastener_or_clearance_hole"]
    return {
        "functional_role": functional_role,
        "feature_intent": feature_intent,
        "mating_interfaces": _dedupe(mating_interfaces),
        "modeling_method": {
            "command": "cut_extrude",
            "reason": "Same-plane through holes are stable as one constrained hole sketch followed by through cut.",
        },
        "sketch_strategy": {
            "type": "same_plane_circle_layout",
            "construction": "Place circles on the base sketch plane and dimension centers from the part center or edge offsets.",
            "driving_dimensions": ["hole_diameter", "hole_centers", "edge_margin_or_pitch"],
            "constraint_policy": "dimension every hole center and diameter; do not fix hole copies.",
        },
    }


def _slot_or_pocket_feature_from_request(request: str) -> dict[str, Any] | None:
    text = _normalized_text(request)
    has_obround = _contains_any(text, ("腰形孔", "长圆孔"))
    has_generic_slot = _contains_slot_word_outside_obround_dimensions(text)
    if not has_obround and not has_generic_slot:
        return None
    slot_params = _slot_parameters_from_request(text)
    if _contains_any(text, ("中间", "中心", "居中")):
        slot_params["position_strategy"] = "centered_on_part_origin"
    if has_obround and int(slot_params.get("count") or 1) == 1:
        slot_params["position_strategy"] = "centered_on_part_origin"
    elif has_obround and int(slot_params.get("count") or 1) == 2:
        slot_params["position_strategy"] = "two_parallel_slots_symmetric_about_part_center"
    if has_obround:
        functional_role = "adjustment_slot" if _contains_any(text, ("调节", "张紧")) else "obround_slot"
        feature_intent = "provide an adjustable fastener slot" if functional_role == "adjustment_slot" else "provide an obround through slot"
        kind = "obround_slot"
        sketch_type = "straight_slot_profile"
        mating_interfaces = ["adjustment_slot", "fastener_or_clearance_hole"]
        required = ["length", "width"]
        if int(slot_params.get("count") or 1) not in {1, 2}:
            required.append("position")
    elif _contains_any(text, ("避让", "避让槽")):
        functional_role = "clearance_cut_or_relief_slot"
        feature_intent = "provide local clearance for another part or motion envelope"
        kind = "slot_or_pocket"
        sketch_type = "clearance_cut_profile"
        mating_interfaces = ["clearance_envelope"]
        required = ["length", "width", "position", "depth"]
    elif _contains_any(text, ("密封", "密封槽")):
        functional_role = "seal_groove"
        feature_intent = "provide a groove for a sealing element"
        kind = "slot_or_pocket"
        sketch_type = "face_offset_or_closed_slot_profile"
        mating_interfaces = ["seal_groove_or_sealing_face"]
        required = ["length", "width", "position", "depth"]
    else:
        functional_role = "slot_or_pocket_cut"
        feature_intent = "provide a cut slot or pocket feature"
        kind = "slot_or_pocket"
        sketch_type = "closed_slot_or_pocket_profile"
        mating_interfaces = ["cut_feature_interface"]
        required = ["length", "width", "depth"]
        slot_params["position_strategy"] = "centered_on_part_origin"
    missing = [
        name
        for name in required
        if not (name == "position" and slot_params.get("position_strategy")) and slot_params.get(name) is None
    ]
    if not has_obround and "position_strategy" not in slot_params and "position" not in missing:
        missing.append("position")
    return {
        "id": functional_role,
        "kind": kind,
        "method": "cut_extrude",
        "functional_role": functional_role,
        "feature_intent": feature_intent,
        "mating_interfaces": _dedupe(mating_interfaces),
        "modeling_method": {
            "command": "cut_extrude",
            "reason": "Planar slots and pockets are subtractive prismatic features driven by a clean closed sketch profile.",
        },
        "sketch_strategy": {
            "type": sketch_type,
            "construction": "Create a dimensioned closed slot/pocket profile on the target face, then cut to the requested depth or through the body.",
            "driving_dimensions": ["slot_length", "slot_width", "slot_position", "cut_depth"],
            "constraint_policy": "dimension the slot center, length, width, and orientation from stable datums; avoid fixed slot endpoints.",
        },
        "parameters": slot_params,
        "required_parameters": _dedupe(missing),
        "references": {
            "target_face": "to_be_selected",
            "sketch_plane": "target_face",
        },
    }


def _hole_treatment_features_from_request(request: str) -> list[dict[str, Any]]:
    text = _normalized_text(request)
    features: list[dict[str, Any]] = []
    if _contains_any(text, ("沉头", "沉孔")):
        is_countersink = "沉头" in text
        parameters = _hole_treatment_defaults(text, is_countersink=is_countersink)
        required = [
            name
            for name in ["nominal_size", "head_diameter", "seat_depth"]
            if parameters.get(name) is None
        ]
        features.append(
            {
                "id": "沉头孔" if is_countersink else "沉孔",
                "kind": "countersink" if is_countersink else "counterbore",
                "method": "cut_extrude",
                "functional_role": "countersunk_fastener_interface" if is_countersink else "counterbored_fastener_interface",
                "feature_intent": "seat a countersunk or counterbored fastener head below or flush with the surface",
                "mating_interfaces": ["countersunk_fastener_interface" if is_countersink else "counterbored_fastener_interface"],
                "modeling_method": {
                    "command": "cut_extrude",
                    "reason": "The current SolidWorks executor creates the base clearance hole plus a concentric top-face seat cut; countersinks add a draft angle for the conical seat.",
                },
                "sketch_strategy": {
                    "type": "concentric_hole_seat_profile",
                    "construction": "Create a constrained top-face circle concentric with the base hole, then cut the requested seat depth.",
                    "driving_dimensions": ["nominal_hole_size", "head_diameter", "seat_angle_or_depth"],
                    "constraint_policy": "keep the head seat concentric with the through hole and driven by standard dimensions.",
                },
                "parameters": parameters,
                "required_parameters": required,
                "references": {
                    "base_hole": "same_hole_layout",
                },
            }
        )
    if "螺纹" in text:
        parameters = _threaded_hole_defaults(text)
        required = [
            name
            for name in ["thread_size", "thread_depth", "tap_drill_diameter"]
            if parameters.get(name) is None
        ]
        features.append(
            {
                "id": "螺纹孔",
                "kind": "threaded_hole",
                "method": "cut_extrude",
                "functional_role": "threaded_fastener_interface",
                "feature_intent": "provide internal threads for a screw or bolt",
                "mating_interfaces": ["threaded_fastener_interface"],
                "modeling_method": {
                    "command": "cut_extrude",
                    "reason": "The current executor creates a tap-drill hole and records thread metadata for later drawing/Hole Wizard expansion.",
                },
                "sketch_strategy": {
                    "type": "tap_drill_circle_layout",
                    "construction": "Place constrained tap-drill circles on the target face and cut to thread depth.",
                    "driving_dimensions": ["thread_size", "thread_depth", "hole_positions"],
                    "constraint_policy": "dimension thread hole centers from datums and keep thread callout separate from plain hole diameter.",
                },
                "parameters": parameters,
                "required_parameters": required,
                "references": {
                    "target_face": "same_hole_layout",
                },
            }
        )
    return features


def _reinforcement_or_boss_features_from_request(request: str) -> list[dict[str, Any]]:
    text = _normalized_text(request)
    features: list[dict[str, Any]] = []
    if _contains_any(text, ("加强筋", "筋板")):
        features.append(
            {
                "id": "加强筋",
                "kind": "rib",
                "method": "rib_or_extrude",
                "functional_role": "reinforcement_rib",
                "feature_intent": "increase stiffness or support a loaded wall/face",
                "mating_interfaces": ["supporting_faces"],
                "modeling_method": {
                    "command": "rib_or_extrude",
                    "reason": "Ribs should be tied to supporting faces and driven by thickness, height, direction, and draft/fillet policy.",
                },
                "sketch_strategy": {
                    "type": "rib_centerline_or_closed_profile",
                    "construction": "Create a rib path or closed rib section from stable faces and dimension rib thickness and height.",
                    "driving_dimensions": ["rib_thickness", "rib_height", "rib_direction"],
                    "constraint_policy": "reference load-bearing faces rather than floating rib endpoints.",
                },
                "parameters": {
                    "thickness": _feature_dimension(text, ("加强筋", "筋板"), ("厚度", "厚")),
                    "height": _feature_dimension(text, ("加强筋", "筋板"), ("高度", "高")),
                    "length": _feature_dimension(text, ("加强筋", "筋板"), ("长度", "长")),
                    "direction": "x",
                    "position_strategy": "centered_on_part_origin",
                },
                "required_parameters": [
                    name
                    for name in ["thickness", "height", "length"]
                    if _feature_dimension(text, ("加强筋", "筋板"), ({"thickness": "厚度", "height": "高度", "length": "长度"}[name], {"thickness": "厚", "height": "高", "length": "长"}[name])) is None
                ],
                "references": {
                    "supporting_faces": "base_top_face",
                },
            }
        )
    if "凸台" in text:
        diameter = _feature_dimension(text, ("凸台",), ("直径", "外径", "宽"))
        height = _feature_dimension(text, ("凸台",), ("高度", "高"))
        features.append(
            {
                "id": "凸台",
                "kind": "boss",
                "method": "extrude",
                "functional_role": "boss_or_standoff_interface",
                "feature_intent": "provide a raised boss, standoff, or local mounting interface",
                "mating_interfaces": ["boss_or_standoff_interface"],
                "modeling_method": {
                    "command": "extrude",
                    "reason": "Bosses are additive prismatic features best driven by a constrained profile on a selected face.",
                },
                "sketch_strategy": {
                    "type": "face_based_closed_profile",
                    "construction": "Sketch the boss profile on the target face and dimension center, diameter/size, and height.",
                    "driving_dimensions": ["boss_profile_size", "boss_position", "boss_height"],
                    "constraint_policy": "locate boss center from stable datums or mating geometry.",
                },
                "parameters": {
                    "diameter": diameter,
                    "height": height,
                    "position_strategy": "centered_on_part_origin",
                },
                "required_parameters": [
                    name
                    for name, value in {"diameter": diameter, "height": height}.items()
                    if value is None
                ],
                "references": {
                    "target_face": "base_top_face",
                },
            }
        )
    return features


def _edge_treatment_features_from_request(request: str) -> list[dict[str, Any]]:
    text = _normalized_text(request)
    features: list[dict[str, Any]] = []
    if "圆角" in text:
        features.append(
            {
                "id": "圆角处理",
                "kind": "fillet",
                "method": "sketch_fillet_or_feature_fillet",
                "functional_role": "edge_rounding_or_stress_relief",
                "feature_intent": "round selected edges for manufacturing, handling, appearance, or stress relief",
                "mating_interfaces": ["selected_edges"],
                "modeling_method": {
                    "command": "sketch_fillet_or_feature_fillet",
                    "reason": "Fillet placement depends on whether the radius belongs to the sketch profile or to finished solid edges.",
                },
                "sketch_strategy": {
                    "type": "deferred_until_edge_or_sketch_role_known",
                    "construction": "Ask or infer whether the fillet should be sketch-level or feature-level, then apply radius to selected entities.",
                    "driving_dimensions": ["fillet_radius", "target_edges_or_sketch_entities"],
                    "constraint_policy": "do not bake functional fillets into unrelated fixed geometry.",
                },
                "parameters": {
                    "radius": _feature_dimension(text, ("圆角",), ("半径", "r", "R")),
                    "targets": [],
                },
                "required_parameters": ["radius", "target_edges_or_sketch_entities"],
            }
        )
    if "倒角" in text:
        features.append(
            {
                "id": "倒角处理",
                "kind": "chamfer",
                "method": "sketch_chamfer_or_feature_chamfer",
                "functional_role": "edge_break_or_assembly_lead_in",
                "feature_intent": "break sharp edges or provide an assembly lead-in",
                "mating_interfaces": ["selected_edges"],
                "modeling_method": {
                    "command": "sketch_chamfer_or_feature_chamfer",
                    "reason": "Chamfer placement depends on whether it defines the sketch profile or post-feature edge treatment.",
                },
                "sketch_strategy": {
                    "type": "deferred_until_edge_or_sketch_role_known",
                    "construction": "Ask or infer whether the chamfer should be sketch-level or feature-level, then dimension distance/angle.",
                    "driving_dimensions": ["chamfer_distance", "chamfer_angle", "target_edges_or_sketch_entities"],
                    "constraint_policy": "keep chamfer dimensions editable and tied to selected edges/entities.",
                },
                "parameters": {
                    "distance": _feature_dimension(text, ("倒角",), ("距离", "边长", "宽")),
                    "angle": _feature_dimension(text, ("倒角",), ("角度", "角")),
                    "targets": [],
                },
                "required_parameters": ["distance_or_distance_angle", "target_edges_or_sketch_entities"],
            }
        )
    return features


def _prismatic_feature_plan_from_request(
    request: str,
    *,
    strategy: dict[str, Any],
) -> dict[str, Any]:
    params, questions, warnings = _parse_prismatic_parameters(request)
    features = [
        {
            "id": "棱柱主形体",
            "kind": "base_body",
            "method": "extrude",
            **_prismatic_base_feature_semantics(request),
            "parameters": {
                "length": params["length"],
                "width": params["width"],
                "thickness": params["thickness"],
            },
            "references": {
                "sketch_plane": "base",
            },
        }
    ]
    if params.get("holes") and "螺纹" not in _normalized_text(request):
        features.append(
            {
                "id": "孔组切除",
                "kind": "hole_pattern" if len(params["holes"]) > 1 else "hole",
                "method": "cut_extrude",
                **_hole_feature_semantics(request, params["holes"]),
                "parameters": {
                    "holes": params["holes"],
                    "through": True,
                },
                "references": {
                    "sketch_plane": "base",
                    "origin": "part_center",
                },
            }
        )
    planned_feature_groups = [
        _slot_or_pocket_feature_from_request(request),
        *_hole_treatment_features_from_request(request),
        *_reinforcement_or_boss_features_from_request(request),
        *_edge_treatment_features_from_request(request),
    ]
    features.extend(feature for feature in planned_feature_groups if feature is not None)
    missing_capabilities: list[dict[str, Any]] = []
    unsupported_map = {
        "槽": ("slot_or_pocket", "cut_extrude", "需要槽长、槽宽、位置和开口/闭合语义。"),
        "避让": ("slot_or_pocket", "cut_extrude", "需要避让轮廓、深度、位置和作用对象。"),
        "口袋": ("slot_or_pocket", "cut_extrude", "需要口袋轮廓、深度和定位基准。"),
        "窗口": ("window_cut", "cut_extrude", "需要窗口轮廓、尺寸和定位基准。"),
        "圆角": ("fillet", "sketch_fillet_or_feature_fillet", "需要圆角作用对象和半径。"),
        "倒角": ("chamfer", "sketch_chamfer_or_feature_chamfer", "需要倒角作用对象和距离/角度。"),
        "沉头": ("countersink", "cut_extrude_with_draft", "需要孔规格、头部直径、沉头深度和孔位置。"),
        "沉孔": ("counterbore", "cut_extrude", "需要孔规格、沉孔直径、沉孔深度和孔位置。"),
        "螺纹": ("threaded_hole", "tap_drill_cut_with_thread_metadata", "需要螺纹规格、深度、底孔策略和孔位置。"),
        "腰形孔": ("obround_slot", "cut_extrude", "需要槽长、槽宽和定位方式。"),
        "长圆孔": ("obround_slot", "cut_extrude", "需要槽长、槽宽和定位方式。"),
        "加强筋": ("rib", "rib_or_extrude", "需要加强筋高度、厚度、方向和依附面。"),
        "筋板": ("rib", "rib_or_extrude", "需要筋板高度、厚度、方向和依附面。"),
        "凸台": ("boss", "extrude", "需要凸台轮廓、位置、高度和目标面。"),
    }
    compile_ready_features = {
        str(feature.get("kind"))
        for feature in planned_feature_groups
        if feature is not None and not feature.get("required_parameters")
    }
    seen_capabilities: set[tuple[str, str]] = set()
    for keyword, (feature, method, reason) in unsupported_map.items():
        if keyword == "槽" and _contains_any(_normalized_text(request), ("腰形孔", "长圆孔")) and not _contains_slot_word_outside_obround_dimensions(_normalized_text(request)):
            continue
        if feature in compile_ready_features:
            continue
        if keyword in _normalized_text(request):
            capability_key = (feature, method)
            if capability_key in seen_capabilities:
                continue
            seen_capabilities.add(capability_key)
            missing_capabilities.append(
                {
                    "feature": feature,
                    "needed_method": method,
                    "reason": reason,
                }
            )
    feature_plan = feature_plan_to_dict(
        request=request,
        strategy=strategy,
        dominant_geometry="prismatic",
        features=features,
        parameters=params,
        engineering_context=_infer_engineering_context(request, "prismatic"),
        questions=questions,
        warnings=warnings,
        missing_capabilities=missing_capabilities,
    )
    return {
        "ready": not questions and not missing_capabilities,
        "questions": questions,
        "warnings": warnings,
        "feature_plan": feature_plan,
        "parsed_parameters": params,
    }


def _prismatic_job_from_request(
    request: str,
    *,
    strategy: dict[str, Any],
    job_id: str | None,
    part_name: str | None,
    material: str | None,
    export_formats: list[str] | None,
) -> dict[str, Any]:
    draft = _prismatic_feature_plan_from_request(request, strategy=strategy)
    feature_plan = draft["feature_plan"]
    params = draft["parsed_parameters"]
    warnings = draft["warnings"]
    if not draft["ready"]:
        return {
            "ready": False,
            "questions": draft["questions"],
            "warnings": warnings,
            "feature_plan": feature_plan,
            "job": None,
            "parsed_parameters": params,
        }

    selected_material = material or params["material"] or "6061-T6 aluminum"
    selected_job_id = job_id or f"自然语言板类零件-{_stable_job_suffix(request)}"
    selected_part_name = part_name or ("自然语言安装板" if "安装板" in request else "自然语言板类零件")
    selected_exports = export_formats or ["pdf", "svg", "step"]
    job = compile_feature_plan_to_primitive_job(
        feature_plan,
        job_id=selected_job_id,
        part_name=selected_part_name,
        material=selected_material,
        export_formats=selected_exports,
    )
    return {
        "ready": True,
        "questions": [],
        "warnings": warnings,
        "feature_plan": feature_plan,
        "job": job,
        "parsed_parameters": params,
    }


def draft_primitive_job_from_natural_language(
    request: str,
    *,
    job_id: str | None = None,
    part_name: str | None = None,
    material: str | None = None,
    export_formats: list[str] | None = None,
) -> dict[str, Any]:
    clean_request = request.strip()
    if not clean_request:
        raise ValueError("Natural-language CAD request must not be empty.")

    strategy = plan_modeling_strategy_dict(clean_request)
    if strategy["intent"] != "part_modeling":
        feature_plan = _unsupported_feature_plan(
            request=clean_request,
            strategy=strategy,
            questions=["第一版自然语言 job 草案只支持零件建模请求。"],
            feature="unsupported_intent",
            needed_method=strategy.get("intent", "unknown"),
            reason="当前自然语言建模草案只展开零件建模，不展开装配、出图或逆向建模。",
        )
        return {
            "ok": False,
            "ready_for_execution": False,
            "request": clean_request,
            "strategy": strategy,
            "questions": feature_plan["questions"],
            "warnings": [],
            "feature_plan": feature_plan,
            "parsed_parameters": {},
            "job": None,
        }

    if strategy["chosen_strategy"] == "revolve_then_cut_revolve":
        draft = _rotational_job_from_request(
            clean_request,
            strategy=strategy,
            job_id=job_id,
            part_name=part_name,
            material=material,
            export_formats=export_formats,
        )
    elif strategy["chosen_strategy"] in {
        "extrude_then_cut_extrude",
        "sketch_level_optimized_extrude_or_cut",
    }:
        draft = _prismatic_job_from_request(
            clean_request,
            strategy=strategy,
            job_id=job_id,
            part_name=part_name,
            material=material,
            export_formats=export_formats,
        )
    else:
        questions = list(strategy.get("questions", []))
        questions.append("当前自然语言 job 草案支持旋转类零件和基础板类/块类零件；该策略下一步继续扩展。")
        feature_plan = _unsupported_feature_plan(
            request=clean_request,
            strategy=strategy,
            questions=questions,
            feature="unsupported_feature_plan_family",
            needed_method=strategy.get("chosen_strategy", "unknown"),
            reason="当前 Feature Plan 编译器还没有展开该建模家族。",
        )
        return {
            "ok": False,
            "ready_for_execution": False,
            "request": clean_request,
            "strategy": strategy,
            "questions": feature_plan["questions"],
            "warnings": [],
            "feature_plan": feature_plan,
            "parsed_parameters": {},
            "job": None,
        }
    ready = bool(draft["ready"])
    return {
        "ok": ready,
        "ready_for_execution": ready,
        "request": clean_request,
        "strategy": strategy,
        "questions": draft["questions"],
        "warnings": draft["warnings"],
        "feature_plan": draft["feature_plan"],
        "parsed_parameters": draft["parsed_parameters"],
        "job": draft["job"],
    }


def draft_feature_plan_from_natural_language(request: str) -> dict[str, Any]:
    clean_request = request.strip()
    if not clean_request:
        raise ValueError("Natural-language CAD request must not be empty.")

    strategy = plan_modeling_strategy_dict(clean_request)
    if strategy["intent"] != "part_modeling":
        feature_plan = _unsupported_feature_plan(
            request=clean_request,
            strategy=strategy,
            questions=["第一版自然语言 Feature Plan 草案只支持零件建模请求。"],
            feature="unsupported_intent",
            needed_method=strategy.get("intent", "unknown"),
            reason="当前自然语言建模草案只展开零件建模，不展开装配、出图或逆向建模。",
        )
    elif strategy["chosen_strategy"] == "revolve_then_cut_revolve":
        feature_plan = _rotational_feature_plan_from_request(clean_request, strategy=strategy)["feature_plan"]
    elif strategy["chosen_strategy"] in {
        "extrude_then_cut_extrude",
        "sketch_level_optimized_extrude_or_cut",
    }:
        feature_plan = _prismatic_feature_plan_from_request(clean_request, strategy=strategy)["feature_plan"]
    else:
        questions = list(strategy.get("questions", []))
        questions.append("当前 Feature Plan 草案支持旋转类零件和基础板类/块类零件；该策略下一步继续扩展。")
        feature_plan = _unsupported_feature_plan(
            request=clean_request,
            strategy=strategy,
            questions=questions,
            feature="unsupported_feature_plan_family",
            needed_method=strategy.get("chosen_strategy", "unknown"),
            reason="当前 Feature Plan 草案还不能展开该建模策略。",
        )
    return {
        "ok": not feature_plan.get("questions") and not feature_plan.get("missing_capabilities"),
        "ready_for_compilation": not feature_plan.get("questions") and not feature_plan.get("missing_capabilities"),
        "request": clean_request,
        "feature_plan": feature_plan,
    }
