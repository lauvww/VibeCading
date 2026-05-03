from __future__ import annotations

import copy
import hashlib
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from core.edit_execution import apply_edit_dsl_to_feature_plan, compile_edit_dsl_to_job
from core.edit_planner import build_edit_dsl, build_edit_plan
from core.feature_plan import feature_plan_to_dict, resolve_feature_plan_references
from core.part_context import load_part_context
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


def _requests_hole_wizard(text: str) -> bool:
    return _contains_any(text, ("孔向导", "hole wizard", "holewizard"))


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


def _dedupe_hole_layout(holes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[float, float, float, str]] = set()
    for hole in holes:
        center = hole.get("center", [0.0, 0.0])
        key = (
            round(float(center[0]), 6),
            round(float(center[1]), 6),
            round(float(hole.get("diameter", 0.0)), 6),
            str(hole.get("callout") or hole.get("id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(copy.deepcopy(hole))
    return deduped


def _load_existing_part_context(context_file: str | Path | None) -> dict[str, Any] | None:
    if not context_file:
        return None
    return load_part_context(context_file)


def _existing_context_feature_plan(existing_part_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not existing_part_context:
        return None
    feature_plan = existing_part_context.get("feature_plan")
    if isinstance(feature_plan, dict):
        return copy.deepcopy(feature_plan)
    return None


def _existing_context_parameters(existing_part_context: dict[str, Any] | None) -> dict[str, Any]:
    feature_plan = _existing_context_feature_plan(existing_part_context)
    if feature_plan:
        return dict(feature_plan.get("parameters", {}))
    if existing_part_context and isinstance(existing_part_context.get("parameters"), dict):
        return dict(existing_part_context["parameters"])
    return {}


def _existing_context_registry(existing_part_context: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not existing_part_context:
        return {}
    registry = existing_part_context.get("reference_registry")
    if not isinstance(registry, dict):
        return {}
    return copy.deepcopy(registry)


def _request_mentions_prismatic_base_dimensions(text: str) -> bool:
    return bool(
        re.search(
            NUMBER + r"\s*(?:x|\*)\s*" + NUMBER + r"\s*(?:x|\*)\s*" + NUMBER,
            text,
            re.IGNORECASE,
        )
        or re.search(r"(?:板长|总长|长度|长边|(?<!槽)(?<!孔)长)\s*[:：为是]?\s*" + NUMBER, text, re.IGNORECASE)
        or re.search(r"(?:板宽|总宽|宽度|宽边|(?<!槽)(?<!孔)宽)\s*[:：为是]?\s*" + NUMBER, text, re.IGNORECASE)
        or re.search(r"(?:板厚|厚度|(?<!槽)(?<!孔)厚)\s*[:：为是]?\s*" + NUMBER, text, re.IGNORECASE)
    )


def _request_mentions_local_prismatic_feature(text: str) -> bool:
    return _contains_any(text, ("凸台", "口袋", "避让槽", "避让", "窗口", "槽", "加强筋", "筋板"))


def _request_mentions_rotational_base_dimensions(text: str) -> bool:
    return bool(
        re.search(r"(?:总长|长度|长)\s*[:：为是]?\s*" + NUMBER, text, re.IGNORECASE)
        or re.search(r"(?:最大直径|外径|直径)\s*[:：为是]?\s*" + NUMBER, text, re.IGNORECASE)
    )


def _looks_like_modification_request(request: str, dominant_geometry: str, existing_part_context: dict[str, Any] | None) -> bool:
    if not existing_part_context:
        return False
    text = _normalized_text(request)
    if _contains_any(text, ("追加", "再加", "新增", "修改", "改成", "继续", "已有", "原来", "之前", "在")):
        if _contains_any(text, ("凸台上", "口袋底部", "侧面", "安装面", "端面", "上开", "上加", "底部", "顶部")):
            return True
    if dominant_geometry == "prismatic":
        return not _request_mentions_prismatic_base_dimensions(text)
    if dominant_geometry == "rotational":
        return not _request_mentions_rotational_base_dimensions(text)
    return False


def _is_parameter_update_request(request: str) -> bool:
    text = _normalized_text(request)
    return _contains_any(text, ("修改", "改成", "改为", "调整", "变成", "变为", "改大", "改小"))


def _existing_context_dominant_geometry(existing_part_context: dict[str, Any] | None) -> str:
    feature_plan = _existing_context_feature_plan(existing_part_context)
    if feature_plan:
        return str(feature_plan.get("dominant_geometry", ""))
    if existing_part_context:
        return str(existing_part_context.get("dominant_geometry", ""))
    return ""


def _bias_strategy_with_existing_context(
    request: str,
    strategy: dict[str, Any],
    existing_part_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not existing_part_context or str(strategy.get("intent", "")) != "part_modeling":
        return strategy
    context_geometry = _existing_context_dominant_geometry(existing_part_context)
    if context_geometry not in {"prismatic", "rotational"}:
        return strategy
    if not _looks_like_modification_request(request, context_geometry, existing_part_context):
        return strategy

    updated = dict(strategy)
    updated["dominant_geometry"] = context_geometry
    updated["chosen_strategy"] = (
        "extrude_then_cut_extrude" if context_geometry == "prismatic" else "revolve_then_cut_revolve"
    )
    assumptions = list(updated.get("assumptions", []))
    updated["assumptions"] = _dedupe([*assumptions, "reuse_existing_part_context_geometry"])
    updated["selection_reason"] = (
        f"当前请求按修改已有零件处理，沿用已有零件上下文中的 {context_geometry} 主导几何，"
        "再把新增工程语义追加到原有 Feature Plan 上。"
    )
    return updated


def _stable_job_suffix(request: str) -> str:
    return hashlib.sha1(request.encode("utf-8")).hexdigest()[:8]


def _auto_job_id(base: str, request: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"{base}-{_stable_job_suffix(request)}-{timestamp}"


def _material_from_request(request: str, default: str = "") -> str:
    match = re.search(r"材料\s*[:：为是]?\s*([0-9A-Za-z#\-\u4e00-\u9fff]+)", request)
    if not match:
        return default
    return match.group(1)


def _feature_dimension(text: str, feature_keywords: tuple[str, ...], dimension_keywords: tuple[str, ...]) -> float | None:
    feature_pattern = "|".join(re.escape(keyword) for keyword in feature_keywords)
    dimension_pattern = "|".join(re.escape(keyword) for keyword in dimension_keywords)
    set_phrase = r"(?:改成|改为|调整为|变成|变为)?\s*"
    direct = _first_number(
        [
            rf"(?:{feature_pattern})[^，,。；;]{{0,24}}?(?:{dimension_pattern})\s*(?:[:：为是]?\s*{set_phrase}|{set_phrase}){NUMBER}",
            rf"(?:{dimension_pattern})\s*(?:[:：为是]?\s*{set_phrase}|{set_phrase}){NUMBER}[^，,。；;]{{0,24}}?(?:{feature_pattern})",
        ],
        text,
    )
    if direct is not None:
        return direct
    if _contains_any(text, feature_keywords) and _contains_any(text, ("改成", "改为", "调整为", "变成", "变为")):
        return _first_number(
            [
                rf"(?:{dimension_pattern})\s*(?:[:：为是]?\s*{set_phrase}|{set_phrase}){NUMBER}",
            ],
            text,
        )
    return None


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


def _metric_size_from_request(text: str) -> float | None:
    metric = re.search(r"(?<![0-9A-Za-z])m\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if metric:
        return float(metric.group(1))
    return None


def _without_hole_treatment_diameter_phrases(text: str) -> str:
    return re.sub(
        r"(?:头部直径|沉头直径|沉孔直径|座孔直径|大径)\s*[:：为是]?\s*" + NUMBER,
        "",
        text,
        flags=re.IGNORECASE,
    )


def _explicit_nominal_hole_size_from_request(text: str) -> float | None:
    search_text = _without_hole_treatment_diameter_phrases(text)
    return _first_number(
        [
            r"(?:公称直径|螺纹规格|孔规格|螺栓规格)\s*[:：为是]?\s*" + NUMBER,
            r"(?:孔径|孔直径)\s*[:：为是]?\s*" + NUMBER,
            r"(?:安装孔|螺栓孔|通孔|中心孔|中间孔)[^，,。；;]{0,12}?(?:直径|孔径|d|φ|Φ)\s*[:：为是]?\s*" + NUMBER,
            r"(?:直径|孔径|d|φ|Φ)\s*[:：为是]?\s*" + NUMBER + r"[^，,。；;]{0,12}?(?:安装孔|螺栓孔|通孔|中心孔|中间孔)",
        ],
        search_text,
    )


def _clearance_class_from_request(text: str) -> str:
    if _contains_any(text, ("精密间隙", "紧间隙", "close clearance", "close-fit", "close fit")):
        return "close"
    if _contains_any(text, ("宽松间隙", "松间隙", "loose clearance", "loose fit")):
        return "loose"
    return "normal"


def _metric_clearance_diameter(nominal_size: float | None, clearance_class: str) -> float | None:
    if nominal_size is None:
        return None
    table = {
        3.0: {"close": 3.2, "normal": 3.4, "loose": 3.6},
        4.0: {"close": 4.3, "normal": 4.5, "loose": 4.8},
        5.0: {"close": 5.3, "normal": 5.5, "loose": 5.8},
        6.0: {"close": 6.4, "normal": 6.6, "loose": 7.0},
        8.0: {"close": 8.4, "normal": 9.0, "loose": 10.0},
        10.0: {"close": 10.5, "normal": 11.0, "loose": 12.0},
        12.0: {"close": 13.0, "normal": 13.5, "loose": 14.0},
    }
    rounded = round(float(nominal_size), 1)
    if rounded in table:
        return table[rounded].get(clearance_class, table[rounded]["normal"])
    return round(float(nominal_size) * 1.1, 2)


def _metric_thread_pitch(thread_size: float | None) -> float | None:
    if thread_size is None:
        return None
    standard_pitches = {
        3.0: 0.5,
        4.0: 0.7,
        5.0: 0.8,
        6.0: 1.0,
        8.0: 1.25,
        10.0: 1.5,
        12.0: 1.75,
    }
    return standard_pitches.get(round(float(thread_size), 1))


def _standard_counterbore_geometry(nominal_size: float | None) -> dict[str, float | None]:
    if nominal_size is None:
        return {"head_diameter": None, "seat_depth": None}
    table = {
        3.0: {"head_diameter": 5.5, "seat_depth": 3.0},
        4.0: {"head_diameter": 7.0, "seat_depth": 4.0},
        5.0: {"head_diameter": 8.5, "seat_depth": 5.0},
        6.0: {"head_diameter": 10.0, "seat_depth": 6.0},
        8.0: {"head_diameter": 13.0, "seat_depth": 8.0},
        10.0: {"head_diameter": 16.0, "seat_depth": 10.0},
        12.0: {"head_diameter": 18.0, "seat_depth": 12.0},
    }
    return table.get(round(float(nominal_size), 1), {"head_diameter": nominal_size * 1.8, "seat_depth": nominal_size})


def _standard_countersink_head_diameter(nominal_size: float | None) -> float | None:
    if nominal_size is None:
        return None
    table = {
        3.0: 6.3,
        4.0: 8.4,
        5.0: 10.5,
        6.0: 12.6,
        8.0: 16.8,
        10.0: 21.0,
        12.0: 25.0,
    }
    return table.get(round(float(nominal_size), 1), round(float(nominal_size) * 2.1, 2))


def _feature_center_from_request(text: str, feature_keywords: tuple[str, ...]) -> list[float] | None:
    feature_pattern = "|".join(re.escape(keyword) for keyword in feature_keywords)
    match = re.search(
        rf"(?:{feature_pattern})[^，,。；;]{{0,24}}?(?:中心|位置|坐标)?\s*x\s*[:：=]?\s*(-?\d+(?:\.\d+)?)\s*[,，]?\s*y\s*[:：=]?\s*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if match:
        return [float(match.group(1)), float(match.group(2))]
    centered_pattern = rf"(?:(?:{feature_pattern})[^，,。；;]{{0,16}}?(?:中间|中心|居中)|(?:中间|中心|居中)[^，,。；;]{{0,16}}?(?:{feature_pattern}))"
    if re.search(centered_pattern, text):
        return [0.0, 0.0]
    return None


def _feature_draft_angle_from_request(text: str, feature_keywords: tuple[str, ...]) -> float | None:
    return _feature_dimension(text, feature_keywords, ("拔模角", "拔模", "斜度"))


def _hole_treatment_defaults(text: str, *, is_countersink: bool) -> dict[str, Any]:
    nominal = _metric_size_from_request(text) or _explicit_nominal_hole_size_from_request(text)
    clearance_class = _clearance_class_from_request(text)
    clearance_diameter = _metric_clearance_diameter(nominal, clearance_class) if _metric_size_from_request(text) is not None else nominal
    head_diameter = _feature_dimension(
        text,
        ("沉头孔", "沉头", "沉孔"),
        ("头部直径", "沉头直径", "沉孔直径", "座孔直径", "大径"),
    )
    if head_diameter is None:
        head_diameter = _standard_countersink_head_diameter(nominal) if is_countersink else _standard_counterbore_geometry(nominal)["head_diameter"]
    seat_angle = _feature_dimension(text, ("沉头孔", "沉头"), ("角度", "锥角"))
    seat_angle_explicit = seat_angle is not None
    if seat_angle is None and is_countersink:
        seat_angle = 90.0
    seat_depth = _feature_dimension(text, ("沉头孔", "沉头", "沉孔"), ("沉头深", "沉孔深", "深度", "深"))
    if seat_depth is None and nominal is not None and head_diameter is not None:
        if is_countersink:
            half_angle = (seat_angle or 90.0) / 2
            radial_delta = max((float(head_diameter) - float(clearance_diameter or nominal)) / 2, 0.0)
            seat_depth = max(round(radial_delta / max(math.tan(math.radians(half_angle)), 1e-9), 2), 0.5)
        else:
            seat_depth = _standard_counterbore_geometry(nominal)["seat_depth"] or max(nominal * 0.6, 1.0)
    if is_countersink and not seat_angle_explicit and head_diameter is not None and seat_depth is not None:
        base_diameter = clearance_diameter or nominal
        if base_diameter is not None and float(seat_depth) > 0:
            radial_delta = max((float(head_diameter) - float(base_diameter)) / 2, 0.0)
            if radial_delta > 0:
                seat_angle = round(math.degrees(math.atan(radial_delta / float(seat_depth))) * 2, 2)
    return {
        "nominal_size": nominal,
        "clearance_diameter": clearance_diameter,
        "clearance_class": clearance_class,
        "head_diameter": head_diameter,
        "seat_depth": seat_depth,
        "seat_angle": seat_angle if is_countersink else None,
        "standard": "metric_engineering_default",
        "callout": f"M{nominal:g} {'countersink' if is_countersink else 'counterbore'}" if nominal is not None else "",
    }


def _threaded_hole_defaults(text: str) -> dict[str, Any]:
    thread_size = _metric_size_from_request(text) or _explicit_nominal_hole_size_from_request(text)
    thread_depth = _feature_dimension(text, ("螺纹孔", "螺纹"), ("深度", "孔深", "螺纹深", "深"))
    thread_pitch = _metric_thread_pitch(thread_size)
    drill_depth = None if thread_depth is None else round(float(thread_depth) + max(float(thread_size or 0) * 0.35, 2.0), 2)
    return {
        "thread_size": thread_size,
        "thread_standard": "ISO metric coarse",
        "thread_pitch": thread_pitch,
        "thread_depth": thread_depth,
        "drill_depth": drill_depth,
        "tap_drill_diameter": _metric_tap_drill(thread_size),
        "thread_modeling": "solidworks_hole_wizard" if _requests_hole_wizard(text) else "tap_drill_geometry_with_thread_metadata",
        "callout": f"M{thread_size:g} x {thread_pitch:g}" if thread_size is not None and thread_pitch is not None else "",
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
        has_position_strategy = _feature_center_from_request(text, ("避让槽", "避让", "口袋", "凹槽", "窗口", "槽")) is not None
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


def _parse_rotational_parameters(
    request: str,
    *,
    existing_part_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    text = _normalized_text(request)
    questions: list[str] = []
    warnings: list[str] = []
    context_parameters = _existing_context_parameters(existing_part_context)
    set_phrase = r"(?:改成|改为|调整为|变成|变为)?\s*"

    total_lengths = _all_numbers(r"(?:总长|全长|长度|长)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER, text)
    total_length = _first_number([r"(?:总长|全长)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER], text)
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

    has_center_bore_words = any(keyword in text for keyword in ("中心孔", "通孔", "内孔", "内径"))
    has_rotational_body_words = _contains_any(text, ("轴", "阶梯轴", "套筒", "圆柱", "垫圈", "法兰", "皮带轮", "旋转体"))
    diameters = _all_numbers(r"(?:最大直径|外径|直径|d|φ|Φ)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER, text)
    explicit_outer_diameter = _first_number(
        [
            r"(?:最大直径|最大外径|外径)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER,
        ],
        text,
    )
    generic_outer_diameter = None
    if not has_center_bore_words and has_rotational_body_words:
        generic_outer_diameter = _first_number(
            [
                r"(?:直径|d|φ|Φ)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER,
            ],
            text,
        )
    outer_diameter = explicit_outer_diameter or generic_outer_diameter
    if diameters and (explicit_outer_diameter is not None or (generic_outer_diameter is not None and not has_center_bore_words)):
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
            r"(?:内径)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER,
            r"(?:中心孔|通孔|内孔)[^，,。；;]{0,12}?(?:直径|孔径|d|φ|Φ)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER,
            r"(?:直径|孔径|d|φ|Φ)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER + r"[^，,。；;]{0,12}?(?:中心孔|通孔|内孔)",
        ],
        text,
    )

    if total_length is None and context_parameters.get("total_length") is not None:
        total_length = float(context_parameters["total_length"])
        warnings.append("沿用已有零件上下文中的总长进行重建。")
    if outer_diameter is None and context_parameters.get("outer_diameter") is not None:
        outer_diameter = float(context_parameters["outer_diameter"])
        warnings.append("沿用已有零件上下文中的最大外径进行重建。")
    if left_diameter is None and context_parameters.get("left_diameter") is not None:
        left_diameter = float(context_parameters["left_diameter"])
    if left_length is None and context_parameters.get("left_length") is not None:
        left_length = float(context_parameters["left_length"])
    if right_diameter is None and context_parameters.get("right_diameter") is not None:
        right_diameter = float(context_parameters["right_diameter"])
    if right_length is None and context_parameters.get("right_length") is not None:
        right_length = float(context_parameters["right_length"])
    if bore_diameter is None and context_parameters.get("bore_diameter") is not None and not _contains_any(text, ("无中心孔", "取消中心孔")):
        bore_diameter = float(context_parameters["bore_diameter"])

    if total_length is None:
        questions.append("rotational 主导几何需要总长，例如总长 120 mm。")
    if outer_diameter is None:
        questions.append("rotational 主导几何需要最大外径，例如最大直径 40 mm。")

    has_center_bore = has_center_bore_words
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
        "material": _material_from_request(request, default=str(context_parameters.get("material", ""))),
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
    existing_part_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params, questions, warnings = _parse_rotational_parameters(request, existing_part_context=existing_part_context)
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
    feature_plan = resolve_feature_plan_references(
        feature_plan,
        additional_registry=_existing_context_registry(existing_part_context),
    )
    return {
        "ready": not feature_plan.get("questions") and not missing_capabilities,
        "questions": list(feature_plan.get("questions", [])),
        "warnings": warnings,
        "feature_plan": feature_plan,
        "parsed_parameters": params,
    }


def _box_dimensions_from_request(text: str, *, allow_generic_terms: bool = True) -> tuple[float | None, float | None, float | None]:
    set_phrase = r"(?:改成|改为|调整为|变成|变为)?\s*"
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

    length_patterns = [r"(?:板长|总长|长边)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER]
    width_patterns = [r"(?:板宽|总宽|宽边)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER]
    thickness_patterns = [r"(?:板厚)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER]
    if allow_generic_terms:
        length_patterns.append(r"(?:长度)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER)
        width_patterns.append(r"(?:宽度)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER)
        thickness_patterns.append(r"(?:厚度)\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER)
        length_patterns.append(r"(?<!槽)(?<!孔)长\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER)
        width_patterns.append(r"(?<!槽)(?<!孔)宽\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER)
        thickness_patterns.append(r"(?<!槽)(?<!孔)厚\s*(?:[:：为是]?\s*" + set_phrase + r"|" + set_phrase + r")" + NUMBER)

    explicit_length = _first_number(length_patterns, text)
    explicit_width = _first_number(width_patterns, text)
    explicit_thickness = _first_number(thickness_patterns, text)

    return explicit_length or length, explicit_width or width, explicit_thickness or thickness


def _hole_diameter_from_request(text: str) -> float | None:
    explicit = _explicit_nominal_hole_size_from_request(text)
    if explicit is not None:
        return explicit
    metric = _metric_size_from_request(text)
    if metric is None:
        return None
    if "螺纹" in text:
        return metric
    return _metric_clearance_diameter(metric, _clearance_class_from_request(text))


def _hole_layout_metadata(text: str, hole_diameter: float) -> dict[str, Any]:
    nominal = _metric_size_from_request(text)
    clearance_class = _clearance_class_from_request(text)
    if nominal is not None and "螺纹" not in text:
        return {
            "nominal_size": nominal,
            "finished_diameter": hole_diameter,
            "clearance_class": clearance_class,
            "standard": "metric_clearance_default",
            "callout": f"M{nominal:g} {clearance_class} clearance Ø{hole_diameter:g}",
        }
    return {
        "nominal_size": nominal or hole_diameter,
        "finished_diameter": hole_diameter,
        "clearance_class": "",
        "standard": "explicit_diameter",
        "callout": f"Ø{hole_diameter:g}",
    }


def _hole_engineering_intent(text: str) -> str:
    if _contains_any(text, ("螺纹孔", "螺纹", "攻丝", "内螺纹")):
        return "threaded"
    if _contains_any(text, ("沉头孔", "沉头")):
        return "countersink_fastener"
    if _contains_any(text, ("沉孔",)):
        return "counterbore_fastener"
    if _contains_any(text, ("定位孔", "销孔", "定位销")):
        return "locating"
    if _contains_any(text, ("轴承孔", "轴承座", "bearing")):
        return "bearing"
    if _contains_any(text, ("过线孔", "走线孔", "线缆孔", "cable", "routing")):
        return "routing"
    if _contains_any(text, ("减重孔", "轻量化孔", "lightening")):
        return "lightening"
    if _contains_any(text, ("安装孔", "螺栓孔", "螺钉孔", "固定孔", "四角孔", "四角安装孔", "四个安装孔", "fastener", "bolt", "screw")):
        return "fastener_clearance"
    if _contains_any(text, ("通孔", "中心孔", "中间孔")):
        return "simple_through"
    return "generic"


def _hole_clarification_questions(text: str) -> list[str]:
    if not _contains_any(text, ("孔", "m3", "m4", "m5", "m6", "m8", "m10", "hole")):
        return []
    if _contains_any(text, ("长圆孔", "腰形孔")) and not _contains_any(
        text,
        ("中心孔", "中间孔", "四角孔", "安装孔", "螺栓孔", "定位孔", "销孔", "沉头孔", "沉孔", "螺纹孔", "通孔"),
    ):
        return []
    intent = _hole_engineering_intent(text)
    if intent == "generic":
        return ["这个孔的工程作用还不明确，请说明它是安装孔、定位孔、螺纹孔、轴承孔、过线孔还是减重孔。"]
    if intent == "locating" and not _contains_any(text, ("公差", "配合", "h7", "h8", "g6", "过盈", "间隙")):
        return ["定位孔需要实际孔径和配合/公差，例如 Φ6H7 配定位销；否则不应默认当作普通安装孔。"]
    if intent == "bearing" and not _contains_any(text, ("公差", "配合", "h7", "n6", "p6", "过盈", "间隙", "轴承型号", "外径")):
        return ["轴承孔需要轴承型号或配合孔径/公差，例如 6201 外径 32，孔 H7；否则不应默认当作普通通孔。"]
    return []


def _hole_position_pairs_from_segment(segment: str) -> list[list[float]]:
    pairs: list[list[float]] = []
    for match in re.finditer(
        r"x\s*[:：=]?\s*(-?\d+(?:\.\d+)?)\s*[,，/\s]*y\s*[:：=]?\s*(-?\d+(?:\.\d+)?)",
        segment,
        re.IGNORECASE,
    ):
        pairs.append([float(match.group(1)), float(match.group(2))])
    if pairs:
        return pairs
    if _contains_any(segment, ("位置", "坐标")):
        for match in re.finditer(
            r"\(\s*(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)\s*\)",
            segment,
            re.IGNORECASE,
        ):
            pairs.append([float(match.group(1)), float(match.group(2))])
    return pairs


def _explicit_hole_centers_from_request(text: str) -> list[list[float]]:
    hole_keywords = ("孔", "安装孔", "螺栓孔", "螺钉孔", "定位孔", "销孔", "沉头孔", "沉孔", "螺纹孔", "通孔")
    unrelated_feature_keywords = ("口袋", "凸台", "加强筋", "筋板", "槽", "避让", "窗口")
    segments = [segment.strip() for segment in re.split(r"[，,；;]", text) if segment.strip()]
    centers: list[list[float]] = []
    carry_hole_context = False
    for segment in segments:
        has_hole_context = _contains_any(segment, hole_keywords)
        if has_hole_context:
            carry_hole_context = True
        if not has_hole_context and not carry_hole_context:
            continue
        if _contains_any(segment, unrelated_feature_keywords) and not has_hole_context:
            carry_hole_context = False
            continue
        pairs = _hole_position_pairs_from_segment(segment)
        if pairs:
            centers.extend(pairs)
            continue
        if not has_hole_context:
            carry_hole_context = False
    deduped: list[list[float]] = []
    seen: set[tuple[float, float]] = set()
    for center in centers:
        key = (round(float(center[0]), 6), round(float(center[1]), 6))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(center)
    return deduped


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
        questions.append("prismatic 主导几何中的孔特征需要孔径或螺纹规格，例如孔径 8 mm 或 M8。")
        return holes, questions

    has_center_hole = _contains_any(
        text,
        ("中心孔", "中间孔", "中心通孔", "中间通孔", "中心沉头孔", "中心沉孔", "中心螺纹孔"),
    ) or bool(
        re.search(
            r"(?:中心|中间)[^，,。；;]{0,16}?(?:孔|通孔|沉头孔|沉孔|螺纹孔)",
            text,
            re.IGNORECASE,
        )
    )
    hole_metadata = _hole_layout_metadata(text, hole_diameter)
    explicit_centers = _explicit_hole_centers_from_request(text)
    if explicit_centers:
        for index, center in enumerate(explicit_centers, start=1):
            center_x = float(center[0])
            center_y = float(center[1])
            if abs(center_x) + hole_diameter / 2 > length / 2 or abs(center_y) + hole_diameter / 2 > width / 2:
                questions.append(f"显式孔位置 {center} 与孔径冲突，孔轮廓超出了底板边界。")
                return holes, questions
            holes.append({"id": f"孔{index}", "center": [center_x, center_y], "diameter": hole_diameter, **hole_metadata})
        return holes, questions
    if has_center_hole:
        holes.append({"id": "中心孔", "center": [0.0, 0.0], "diameter": hole_diameter, **hole_metadata})

    has_four_corner_holes = _contains_any(text, ("四角孔", "四个角", "4角孔", "四角安装孔", "四个安装孔", "四角沉头孔", "四角沉孔", "四角螺纹孔")) or bool(
        re.search(
            r"(?:四角|四个角|4角)[^，,。；;]{0,16}?(?:安装孔|螺栓孔|螺钉孔|孔|沉头孔|沉孔|螺纹孔)",
            text,
            re.IGNORECASE,
        )
    )
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
        for hole in holes[-4:]:
            hole.update(hole_metadata)

    if mentions_hole and not holes:
        questions.append("请说明孔的位置基准，例如中心孔、四角孔加孔边距，或四角孔加孔距。")

    return holes, questions


def _parse_prismatic_parameters(
    request: str,
    *,
    existing_part_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    text = _normalized_text(request)
    questions: list[str] = []
    warnings: list[str] = []
    context_parameters = _existing_context_parameters(existing_part_context)
    allow_generic_base_terms = True
    if existing_part_context and _is_parameter_update_request(request) and _request_mentions_local_prismatic_feature(text):
        allow_generic_base_terms = False
    length, width, thickness = _box_dimensions_from_request(text, allow_generic_terms=allow_generic_base_terms)
    if length is None and context_parameters.get("length") is not None:
        length = float(context_parameters["length"])
        warnings.append("沿用已有零件上下文中的长度进行重建。")
    if width is None and context_parameters.get("width") is not None:
        width = float(context_parameters["width"])
        warnings.append("沿用已有零件上下文中的宽度进行重建。")
    if thickness is None and context_parameters.get("thickness") is not None:
        thickness = float(context_parameters["thickness"])
        warnings.append("沿用已有零件上下文中的厚度进行重建。")
    if length is None:
        questions.append("prismatic 主导几何需要长度，例如长 120 mm。")
    if width is None:
        questions.append("prismatic 主导几何需要宽度，例如宽 80 mm。")
    if thickness is None:
        questions.append("prismatic 主导几何需要厚度，例如厚 8 mm。")

    unsupported_keywords = {
        "槽": "槽/口袋类特征需要长度、宽度、深度和稳定定位基准。",
        "避让": "避让槽/避让切除需要轮廓、位置和作用对象。",
        "口袋": "口袋特征需要长度、宽度、深度和稳定定位基准。",
        "窗口": "窗口类切除需要轮廓尺寸、深度/贯穿方式和定位基准。",
        "圆角": "实体圆角或草图圆角暂未纳入第一版 prismatic Feature Plan 编译规则。",
        "倒角": "实体倒角或草图倒角暂未纳入第一版 prismatic Feature Plan 编译规则。",
        "沉头": "沉头孔需要孔规格、头部直径、沉头深度和孔位置。",
        "沉孔": "沉孔需要孔规格、沉孔直径、沉孔深度和孔位置。",
        "螺纹": "螺纹孔需要螺纹规格、深度、底孔策略和孔位置。",
        "腰形孔": "腰形孔需要槽长、槽宽和定位方式，暂未纳入第一版 prismatic Feature Plan 编译规则。",
        "长圆孔": "长圆孔需要槽长、槽宽和定位方式，暂未纳入第一版 prismatic Feature Plan 编译规则。",
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
    questions.extend(_hole_clarification_questions(text))

    params = {
        "length": length,
        "width": width,
        "thickness": thickness,
        "hole_diameter": hole_diameter,
        "holes": holes,
        "material": _material_from_request(request, default=str(context_parameters.get("material", ""))),
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
    use_hole_wizard = _requests_hole_wizard(text)
    intent = _hole_engineering_intent(text)
    if intent == "locating":
        functional_role = "locating_pin_interface"
        feature_intent = "locate mating parts with pin holes"
        mating_interfaces = ["locating_pin_interface"]
    elif intent in {"fastener_clearance", "countersink_fastener", "counterbore_fastener"}:
        functional_role = "fastener_hole_pattern"
        feature_intent = "provide bolt or screw clearance pattern for mounting"
        mating_interfaces = ["fastener_or_clearance_hole", "four_corner_fastener_pattern"]
    elif intent == "bearing":
        functional_role = "bearing_seat_hole"
        feature_intent = "provide a bearing-seat bore with controlled fit intent"
        mating_interfaces = ["bearing_seat"]
    elif intent == "routing":
        functional_role = "routing_passage_hole"
        feature_intent = "provide a routed passage for cable, hose, or wire"
        mating_interfaces = ["routing_passage"]
    elif intent == "lightening":
        functional_role = "lightening_hole_pattern" if len(holes) > 1 else "lightening_hole"
        feature_intent = "remove local mass without creating a mating interface"
        mating_interfaces = ["weight_reduction_feature"]
    elif intent == "simple_through":
        functional_role = "center_clearance_or_mounting_hole"
        feature_intent = "provide a centered through hole for clearance or mounting"
        mating_interfaces = ["center_bore", "fastener_or_clearance_hole"]
    elif len(holes) > 1:
        functional_role = "general_hole_pattern"
        feature_intent = "provide multiple through-hole features at explicit locations"
        mating_interfaces = ["through_hole_interface"]
    else:
        functional_role = "through_hole_feature"
        feature_intent = "provide through-hole geometry"
        mating_interfaces = ["through_hole_interface"]
    return {
        "functional_role": functional_role,
        "feature_intent": feature_intent,
        "mating_interfaces": _dedupe(mating_interfaces),
        "modeling_method": {
            "command": "hole_wizard" if use_hole_wizard else "cut_extrude",
            "reason": "Use SolidWorks Hole Wizard because the user explicitly requested it." if use_hole_wizard else "Same-plane through holes are stable as one constrained hole sketch followed by through cut.",
        },
        "sketch_strategy": {
            "type": "hole_wizard_points" if use_hole_wizard else "same_plane_circle_layout",
            "construction": "Place Hole Wizard points on the target face and drive them from the part center or edge offsets." if use_hole_wizard else "Place circles on the base sketch plane and dimension centers from the part center or edge offsets.",
            "driving_dimensions": ["hole_diameter", "hole_centers", "edge_margin_or_pitch"],
            "constraint_policy": "dimension every hole center and diameter; do not fix hole copies.",
        },
    }


def _hole_wizard_hole_type_and_size_label(request: str, holes: list[dict[str, Any]]) -> tuple[str, str | None]:
    text = _normalized_text(request)
    intent = _hole_engineering_intent(text)
    nominal_size = _metric_size_from_request(text)
    explicit_diameter = _explicit_nominal_hole_size_from_request(text)
    fastener_words = _contains_any(text, ("安装孔", "螺栓", "螺钉", "紧固", "fastener", "bolt", "screw"))
    if intent in {"locating", "bearing", "routing", "lightening", "generic", "simple_through"}:
        return "simple", f"{float(explicit_diameter or nominal_size or holes[0]['diameter']):g}"
    if nominal_size is not None and (fastener_words or len(holes) > 1):
        return "clearance", f"M{float(nominal_size):g}"
    if explicit_diameter is not None:
        return "simple", f"{float(explicit_diameter):g}"
    if nominal_size is not None:
        return "simple", f"{float(nominal_size):g}"
    return "simple", f"{float(holes[0]['diameter']):g}" if holes else None


def _slot_or_pocket_feature_from_request(request: str) -> dict[str, Any] | None:
    text = _normalized_text(request)
    has_obround = _contains_any(text, ("腰形孔", "长圆孔"))
    has_generic_slot = _contains_slot_word_outside_obround_dimensions(text)
    if not has_obround and not has_generic_slot:
        return None
    slot_params = _slot_parameters_from_request(text)
    feature_center = _feature_center_from_request(text, ("长圆孔", "腰形孔", "调节槽", "开槽", "避让槽", "避让", "口袋", "凹槽", "窗口", "槽"))
    if feature_center is not None:
        slot_params["center"] = feature_center
        slot_params["position_strategy"] = "centered_on_part_origin"
        if any(abs(value) > 1e-9 for value in feature_center):
            slot_params["position_strategy"] = "explicit_center_xy"
    draft_angle = _feature_draft_angle_from_request(text, ("避让槽", "口袋", "凹槽", "窗口", "槽"))
    if draft_angle is not None:
        slot_params["draft_angle"] = draft_angle
    corner_radius = _feature_dimension(text, ("避让槽", "口袋", "凹槽", "窗口", "槽"), ("圆角半径", "圆角", "R", "r"))
    if corner_radius is not None:
        slot_params["corner_radius"] = corner_radius
    if has_obround and int(slot_params.get("count") or 1) == 1:
        slot_params.setdefault("position_strategy", "centered_on_part_origin")
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
        slot_params.setdefault("position_strategy", "centered_on_part_origin")
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
            "target_face": "base_top_face",
            "sketch_plane": "target_face",
        },
    }


def _hole_treatment_features_from_request(request: str) -> list[dict[str, Any]]:
    text = _normalized_text(request)
    features: list[dict[str, Any]] = []
    use_hole_wizard = _requests_hole_wizard(text)
    if _contains_any(text, ("沉头", "沉孔")):
        is_countersink = "沉头" in text
        parameters = _hole_treatment_defaults(text, is_countersink=is_countersink)
        if use_hole_wizard:
            parameters["use_hole_wizard"] = True
        required = [
            name
            for name in ["nominal_size", "head_diameter", "seat_depth"]
            if parameters.get(name) is None
        ]
        features.append(
            {
                "id": "沉头孔" if is_countersink else "沉孔",
                "kind": "countersink" if is_countersink else "counterbore",
                "method": "hole_wizard" if use_hole_wizard else "cut_extrude",
                "functional_role": "countersunk_fastener_interface" if is_countersink else "counterbored_fastener_interface",
                "feature_intent": "seat a countersunk or counterbored fastener head below or flush with the surface",
                "mating_interfaces": ["countersunk_fastener_interface" if is_countersink else "counterbored_fastener_interface"],
                "modeling_method": {
                    "command": "hole_wizard" if use_hole_wizard else "cut_extrude",
                    "reason": "Use SolidWorks Hole Wizard for the clearance hole and fastener seat because the user explicitly requested it." if use_hole_wizard else "The current SolidWorks executor creates the base clearance hole plus a concentric top-face seat cut; countersinks add a draft angle for the conical seat.",
                },
                "sketch_strategy": {
                    "type": "hole_wizard_points" if use_hole_wizard else "concentric_hole_seat_profile",
                    "construction": "Create Hole Wizard point locations on the target face and let SolidWorks generate the fastener seat." if use_hole_wizard else "Create a constrained top-face circle concentric with the base hole, then cut the requested seat depth.",
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
        if use_hole_wizard:
            parameters["use_hole_wizard"] = True
        required = [
            name
            for name in ["thread_size", "thread_depth", "tap_drill_diameter"]
            if parameters.get(name) is None
        ]
        features.append(
            {
                "id": "螺纹孔",
                "kind": "threaded_hole",
                "method": "hole_wizard" if use_hole_wizard else "cut_extrude",
                "functional_role": "threaded_fastener_interface",
                "feature_intent": "provide internal threads for a screw or bolt",
                "mating_interfaces": ["threaded_fastener_interface"],
                "modeling_method": {
                    "command": "hole_wizard" if use_hole_wizard else "cut_extrude",
                    "reason": "Use SolidWorks Hole Wizard so the feature keeps thread/standard semantics in SolidWorks." if use_hole_wizard else "The current executor creates a tap-drill hole and records thread metadata for later drawing/Hole Wizard expansion.",
                },
                "sketch_strategy": {
                    "type": "hole_wizard_points" if use_hole_wizard else "tap_drill_circle_layout",
                    "construction": "Place Hole Wizard points on the target face and drive them from stable datums." if use_hole_wizard else "Place constrained tap-drill circles on the target face and cut to thread depth.",
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
        rib_thickness = _feature_dimension(text, ("加强筋", "筋板"), ("厚度", "厚"))
        rib_height = _feature_dimension(text, ("加强筋", "筋板"), ("高度", "高"))
        rib_length = _feature_dimension(text, ("加强筋", "筋板"), ("长度", "长"))
        rib_center = _feature_center_from_request(text, ("加强筋", "筋板"))
        rib_draft_angle = _feature_draft_angle_from_request(text, ("加强筋", "筋板"))
        rib_fillet_radius = _feature_dimension(text, ("加强筋", "筋板"), ("圆角半径", "根部圆角", "圆角", "R", "r"))
        rib_parameters: dict[str, Any] = {
            "thickness": rib_thickness,
            "height": rib_height,
            "length": rib_length,
            "direction": "x",
            "position_strategy": "centered_on_part_origin",
        }
        if rib_center is not None:
            rib_parameters["center"] = rib_center
            if any(abs(value) > 1e-9 for value in rib_center):
                rib_parameters["position_strategy"] = "explicit_center_xy"
        if rib_draft_angle is not None:
            rib_parameters["draft_angle"] = rib_draft_angle
        if rib_fillet_radius is not None:
            rib_parameters["fillet_radius"] = rib_fillet_radius
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
                "parameters": rib_parameters,
                "required_parameters": [
                    name
                    for name, value in {"thickness": rib_thickness, "height": rib_height, "length": rib_length}.items()
                    if value is None
                ],
                "references": {
                    "supporting_faces": "base_top_face",
                },
            }
        )
    if "凸台" in text:
        diameter = _feature_dimension(text, ("凸台",), ("直径", "外径", "宽"))
        height = _feature_dimension(text, ("凸台",), ("高度", "高"))
        boss_center = _feature_center_from_request(text, ("凸台",))
        boss_draft_angle = _feature_draft_angle_from_request(text, ("凸台",))
        boss_fillet_radius = _feature_dimension(text, ("凸台",), ("圆角半径", "根部圆角", "圆角", "R", "r"))
        boss_parameters: dict[str, Any] = {
            "diameter": diameter,
            "height": height,
            "position_strategy": "centered_on_part_origin",
        }
        if boss_center is not None:
            boss_parameters["center"] = boss_center
            if any(abs(value) > 1e-9 for value in boss_center):
                boss_parameters["position_strategy"] = "explicit_center_xy"
        if boss_draft_angle is not None:
            boss_parameters["draft_angle"] = boss_draft_angle
        if boss_fillet_radius is not None:
            boss_parameters["fillet_radius"] = boss_fillet_radius
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
                "parameters": boss_parameters,
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
    existing_part_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params, questions, warnings = _parse_prismatic_parameters(request, existing_part_context=existing_part_context)
    text = _normalized_text(request)
    modification_mode = _looks_like_modification_request(request, "prismatic", existing_part_context)
    mentions_existing_boss_host = modification_mode and _contains_any(text, ("凸台上", "凸台顶部", "凸台顶面"))
    mentions_existing_pocket_host = modification_mode and _contains_any(text, ("口袋底部", "口袋底"))
    use_hole_wizard = _requests_hole_wizard(text)
    hole_wizard_treatment = use_hole_wizard and _contains_any(text, ("沉头", "沉孔", "螺纹"))
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
    if params.get("holes") and "螺纹" not in text and not hole_wizard_treatment:
        hole_wizard_hole_type, hole_wizard_size_label = _hole_wizard_hole_type_and_size_label(request, params["holes"])
        features.append(
            {
                "id": "孔组切除",
                "kind": "hole_pattern" if len(params["holes"]) > 1 else "hole",
                "method": "hole_wizard" if use_hole_wizard else "cut_extrude",
                **_hole_feature_semantics(request, params["holes"]),
                "parameters": {
                    "holes": params["holes"],
                    "through": True,
                    "use_hole_wizard": use_hole_wizard,
                    "hole_type": hole_wizard_hole_type,
                    "size_label": hole_wizard_size_label,
                },
                "references": {
                    "target_face": "base_top_face",
                    "sketch_plane": "target_face",
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
    if mentions_existing_boss_host:
        planned_feature_groups = [
            feature
            for feature in planned_feature_groups
            if not (feature is not None and feature.get("kind") == "boss" and feature.get("required_parameters"))
        ]
        questions = [item for item in questions if "凸台需要" not in item]
        warnings = [item for item in warnings if "凸台需要" not in item]
    if mentions_existing_pocket_host:
        planned_feature_groups = [
            feature
            for feature in planned_feature_groups
            if not (feature is not None and feature.get("kind") == "slot_or_pocket" and feature.get("required_parameters"))
        ]
        questions = [item for item in questions if "口袋特征需要" not in item]
        warnings = [item for item in warnings if "口袋特征需要" not in item]
    features.extend(feature for feature in planned_feature_groups if feature is not None)
    if modification_mode and (mentions_existing_boss_host or mentions_existing_pocket_host):
        semantic = "boss_top_face" if mentions_existing_boss_host else "pocket_floor_face"
        host_selector = (
            {"kind": "boss", "functional_role": "boss_or_standoff_interface"}
            if mentions_existing_boss_host
            else {"kind": "slot_or_pocket"}
        )
        for feature in features:
            if str(feature.get("kind", "")) not in {"hole", "hole_pattern", "threaded_hole", "countersink", "counterbore"}:
                continue
            references = feature.setdefault("references", {})
            references["target_semantic"] = semantic
            references["host_feature_selector"] = host_selector
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
        if mentions_existing_boss_host and keyword == "凸台":
            continue
        if mentions_existing_pocket_host and keyword == "口袋":
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
    if modification_mode:
        compile_ready_requested_kinds = {
            str(feature.get("kind", ""))
            for feature in feature_plan.get("features", [])
            if not feature.get("required_parameters")
        }
        question_cleanup_rules = [
            ("口袋特征需要", "slot_or_pocket", _contains_any(text, ("口袋",))),
            ("凸台需要", "boss", _contains_any(text, ("凸台",))),
            ("加强筋需要", "rib", _contains_any(text, ("加强筋", "筋板"))),
        ]
        for phrase, kind, active in question_cleanup_rules:
            if not active or kind not in compile_ready_requested_kinds:
                continue
            feature_plan["questions"] = [item for item in feature_plan.get("questions", []) if phrase not in item]
            feature_plan["warnings"] = [item for item in feature_plan.get("warnings", []) if phrase not in item]
            feature_plan["missing_capabilities"] = [
                item for item in feature_plan.get("missing_capabilities", []) if str(item.get("feature", "")) != kind
            ]
    feature_plan = resolve_feature_plan_references(
        feature_plan,
        additional_registry=_existing_context_registry(existing_part_context),
    )
    return {
        "ready": not feature_plan.get("questions") and not missing_capabilities,
        "questions": list(feature_plan.get("questions", [])),
        "warnings": warnings,
        "feature_plan": feature_plan,
        "parsed_parameters": params,
    }


_PRIMITIVE_DRAFT_STRATEGY_FAMILIES = {
    "revolve_then_cut_revolve": "rotational",
    "extrude_then_cut_extrude": "prismatic",
    "sketch_level_optimized_extrude_or_cut": "prismatic",
}


def _compressed_strategy_view(strategy: dict[str, Any], feature_plan: dict[str, Any]) -> dict[str, Any]:
    # Keep strategy as a lightweight planning view only. Feature Plan is the
    # single engineering-semantic source of truth for downstream compilation.
    compressed = dict(strategy)
    feature_plan_questions = list(feature_plan.get("questions", []))
    compressed["questions"] = feature_plan_questions
    compressed["ready_for_primitive_dsl"] = (
        compressed.get("intent") == "part_modeling"
        and not feature_plan_questions
        and not feature_plan.get("missing_capabilities")
    )
    return compressed


def _feature_plan_draft_from_strategy(
    request: str,
    strategy: dict[str, Any],
    *,
    existing_part_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Route every natural-language request through one feature-plan drafting path
    # so strategy and feature semantics do not diverge into parallel systems.
    if strategy["intent"] != "part_modeling":
        feature_plan = _unsupported_feature_plan(
            request=request,
            strategy=strategy,
            questions=["第一版自然语言建模草案只支持零件建模请求。"],
            feature="unsupported_intent",
            needed_method=strategy.get("intent", "unknown"),
            reason="当前自然语言建模草案只展开零件建模，不展开装配、出图或逆向建模。",
        )
        return {
            "ready": False,
            "questions": list(feature_plan["questions"]),
            "warnings": [],
            "feature_plan": feature_plan,
            "parsed_parameters": {},
        }

    family = _PRIMITIVE_DRAFT_STRATEGY_FAMILIES.get(str(strategy.get("chosen_strategy", "")))
    if family == "rotational":
        return _rotational_feature_plan_from_request(request, strategy=strategy, existing_part_context=existing_part_context)
    if family == "prismatic":
        return _prismatic_feature_plan_from_request(request, strategy=strategy, existing_part_context=existing_part_context)

    questions = list(strategy.get("questions", []))
    questions.append("当前 Feature Plan 草案支持 rotational 与 prismatic 主导几何；该策略下一步继续扩展。")
    feature_plan = _unsupported_feature_plan(
        request=request,
        strategy=strategy,
        questions=questions,
        feature="unsupported_feature_plan_family",
        needed_method=strategy.get("chosen_strategy", "unknown"),
        reason="当前 Feature Plan 编译器还没有展开该建模家族。",
    )
    return {
        "ready": False,
        "questions": list(feature_plan["questions"]),
        "warnings": [],
        "feature_plan": feature_plan,
        "parsed_parameters": {},
    }


def _compile_feature_plan_draft_to_job(
    request: str,
    draft: dict[str, Any],
    *,
    job_id: str | None,
    part_name: str | None,
    material: str | None,
    export_formats: list[str] | None,
    existing_part_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feature_plan = draft["feature_plan"]
    params = draft["parsed_parameters"]
    warnings = draft["warnings"]
    requested_feature_plan = copy.deepcopy(feature_plan)
    edit_plan = build_edit_plan(
        request=request,
        feature_plan=requested_feature_plan,
        existing_part_context=existing_part_context,
    )
    edit_dsl = build_edit_dsl(edit_plan)
    applied_feature_plan = apply_edit_dsl_to_feature_plan(
        edit_dsl=edit_dsl,
        existing_feature_plan=_existing_context_feature_plan(existing_part_context),
        requested_feature_plan=requested_feature_plan,
    )
    if not draft["ready"]:
        return {
            "ready": False,
            "questions": draft["questions"],
            "warnings": warnings,
            "feature_plan": applied_feature_plan,
            "requested_feature_plan": requested_feature_plan,
            "edit_plan": edit_plan,
            "edit_dsl": edit_dsl,
            "job": None,
            "parsed_parameters": params,
        }

    dominant_geometry = str(feature_plan.get("dominant_geometry", ""))
    selected_exports = export_formats or ["pdf", "svg", "step"]
    if dominant_geometry == "rotational":
        selected_material = material or params.get("material") or str((existing_part_context or {}).get("material", "")) or "45钢"
        if "垫圈" in request:
            name_stem = "自然语言垫圈"
        elif "法兰" in request:
            name_stem = "自然语言法兰"
        elif "圆柱" in request:
            name_stem = "自然语言圆柱"
        else:
            name_stem = "自然语言阶梯轴"
        suggested_job_id = edit_plan["output_revision"].get("suggested_job_id")
        selected_job_id = job_id or _auto_job_id(suggested_job_id or name_stem, request)
        selected_part_name = part_name or str((existing_part_context or {}).get("part_name", "")) or name_stem
    else:
        selected_material = material or params.get("material") or str((existing_part_context or {}).get("material", "")) or "6061-T6 aluminum"
        suggested_job_id = edit_plan["output_revision"].get("suggested_job_id")
        selected_job_id = job_id or _auto_job_id(suggested_job_id or "自然语言棱柱零件", request)
        selected_part_name = part_name or str((existing_part_context or {}).get("part_name", "")) or ("自然语言安装板" if "安装板" in request else "自然语言棱柱零件")

    job = compile_edit_dsl_to_job(
        edit_dsl=edit_dsl,
        feature_plan=applied_feature_plan,
        job_id=selected_job_id,
        part_name=selected_part_name,
        material=selected_material,
        export_formats=selected_exports,
    )
    return {
        "ready": True,
        "questions": [],
        "warnings": warnings,
        "feature_plan": applied_feature_plan,
        "requested_feature_plan": requested_feature_plan,
        "edit_plan": edit_plan,
        "edit_dsl": edit_dsl,
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
    context_file: str | Path | None = None,
) -> dict[str, Any]:
    clean_request = request.strip()
    if not clean_request:
        raise ValueError("Natural-language CAD request must not be empty.")

    existing_part_context = _load_existing_part_context(context_file)
    strategy = _bias_strategy_with_existing_context(
        clean_request,
        plan_modeling_strategy_dict(clean_request),
        existing_part_context,
    )
    feature_plan_draft = _feature_plan_draft_from_strategy(
        clean_request,
        strategy,
        existing_part_context=existing_part_context,
    )
    compressed_strategy = _compressed_strategy_view(strategy, feature_plan_draft["feature_plan"])
    draft = _compile_feature_plan_draft_to_job(
        clean_request,
        feature_plan_draft,
        job_id=job_id,
        part_name=part_name,
        material=material,
        export_formats=export_formats,
        existing_part_context=existing_part_context,
    )
    ready = bool(draft["ready"])
    return {
        "ok": ready,
        "ready_for_execution": ready,
        "request": clean_request,
        "strategy": compressed_strategy,
        "questions": draft["questions"],
        "warnings": draft["warnings"],
        "requested_feature_plan": draft["requested_feature_plan"],
        "feature_plan": draft["feature_plan"],
        "edit_plan": draft["edit_plan"],
        "edit_dsl": draft["edit_dsl"],
        "parsed_parameters": draft["parsed_parameters"],
        "job": draft["job"],
    }
def draft_feature_plan_from_natural_language(
    request: str,
    *,
    context_file: str | Path | None = None,
) -> dict[str, Any]:
    clean_request = request.strip()
    if not clean_request:
        raise ValueError("Natural-language CAD request must not be empty.")

    existing_part_context = _load_existing_part_context(context_file)
    strategy = _bias_strategy_with_existing_context(
        clean_request,
        plan_modeling_strategy_dict(clean_request),
        existing_part_context,
    )
    draft = _feature_plan_draft_from_strategy(
        clean_request,
        strategy,
        existing_part_context=existing_part_context,
    )
    requested_feature_plan = copy.deepcopy(draft["feature_plan"])
    edit_plan = build_edit_plan(
        request=clean_request,
        feature_plan=requested_feature_plan,
        existing_part_context=existing_part_context,
    )
    edit_dsl = build_edit_dsl(edit_plan)
    feature_plan = apply_edit_dsl_to_feature_plan(
        edit_dsl=edit_dsl,
        existing_feature_plan=_existing_context_feature_plan(existing_part_context),
        requested_feature_plan=requested_feature_plan,
    )
    return {
        "ok": not feature_plan.get("questions") and not feature_plan.get("missing_capabilities"),
        "ready_for_compilation": not feature_plan.get("questions") and not feature_plan.get("missing_capabilities"),
        "request": clean_request,
        "requested_feature_plan": requested_feature_plan,
        "feature_plan": feature_plan,
        "edit_plan": edit_plan,
        "edit_dsl": edit_dsl,
    }
