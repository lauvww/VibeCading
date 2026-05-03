from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


DIMENSION_RE = re.compile(
    r"(?:m\d+(?:\.\d+)?)|(?:\d+(?:\.\d+)?\s*(?:mm|毫米|cm|厘米|m|米|度|°)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StrategyRule:
    name: str
    dominant_geometry: str
    recommended_primitives: tuple[str, ...]
    keywords: tuple[str, ...]
    reason: str
    alternatives: tuple[str, ...]
    priority: int
    assumptions: tuple[str, ...] = ()


@dataclass(slots=True)
class StrategyPlan:
    request: str
    intent: str
    dominant_geometry: str
    chosen_strategy: str
    recommended_job_kind: str
    recommended_primitives: list[str]
    alternatives_considered: list[str]
    selection_reason: str
    assumptions: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    ready_for_primitive_dsl: bool = False
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "intent": self.intent,
            "dominant_geometry": self.dominant_geometry,
            "chosen_strategy": self.chosen_strategy,
            "recommended_job_kind": self.recommended_job_kind,
            "recommended_primitives": list(self.recommended_primitives),
            "alternatives_considered": list(self.alternatives_considered),
            "selection_reason": self.selection_reason,
            "assumptions": list(self.assumptions),
            "questions": list(self.questions),
            "confidence": self.confidence,
            "ready_for_primitive_dsl": self.ready_for_primitive_dsl,
            "signals": dict(self.signals),
        }


STRATEGY_RULES: tuple[StrategyRule, ...] = (
    StrategyRule(
        name="ordered_profiles_loft_or_cut_loft",
        dominant_geometry="multi_section_transition",
        recommended_primitives=(
            "create_offset_plane",
            "start_sketch",
            "add_circle/add_polyline/add_spline",
            "add_dimensions",
            "validate_fully_constrained",
            "finish_sketch",
            "loft/cut_loft",
        ),
        keywords=(
            "放样",
            "过渡",
            "变截面",
            "变径",
            "渐缩",
            "渐扩",
            "风道",
            "异形管",
            "多截面",
            "进出口",
            "内部通道",
            "reducer",
            "duct",
            "transition",
            "loft",
            "multi-section",
            "variable section",
            "tapered passage",
        ),
        reason="请求包含多截面或变截面过渡语义，优先用有序截面草图和放样/放样切除表达设计意图。",
        alternatives=("stacked_extrudes", "sweep_with_variable_section"),
        priority=100,
        assumptions=("ordered_profile_sections", "datum_or_offset_planes"),
    ),
    StrategyRule(
        name="sweep_or_cut_sweep",
        dominant_geometry="path_driven",
        recommended_primitives=(
            "start_sketch",
            "add_polyline/add_arc/add_spline",
            "add_dimensions",
            "validate_fully_constrained",
            "finish_sketch",
            "start_sketch",
            "add_circle/add_polygon/add_polyline",
            "add_relation(pierce)",
            "validate_fully_constrained",
            "finish_sketch",
            "sweep/cut_sweep",
        ),
        keywords=(
            "扫描",
            "路径",
            "沿",
            "管路",
            "管",
            "把手",
            "导轨",
            "线缆",
            "电缆",
            "油路",
            "油道",
            "弯曲槽",
            "曲线槽",
            "曲线孔",
            "弯孔",
            "圆弧路径",
            "guide",
            "handle",
            "rail",
            "pipe",
            "tube",
            "sweep",
            "path",
            "curved groove",
            "oil passage",
        ),
        reason="请求包含一个截面沿路径生成或切除的语义，优先用路径草图、截面草图和扫描/扫描切除。",
        alternatives=("many_small_extrudes", "loft_for_simple_path"),
        priority=90,
        assumptions=("separate_path_and_profile_sketches", "pierce_relation_when_profile_touches_path"),
    ),
    StrategyRule(
        name="revolve_then_cut_revolve",
        dominant_geometry="rotational",
        recommended_primitives=(
            "start_sketch",
            "add_polyline",
            "add_dimensions",
            "validate_fully_constrained",
            "revolve",
            "start_sketch",
            "add_polyline",
            "add_dimensions",
            "validate_fully_constrained",
            "cut_revolve",
        ),
        keywords=(
            "轴",
            "阶梯轴",
            "套筒",
            "套",
            "垫圈",
            "法兰",
            "旋钮",
            "圆锥",
            "皮带轮",
            "车削",
            "回转",
            "旋转体",
            "中心孔",
            "环形槽",
            "退刀槽",
            "沉头",
            "锥孔",
            "内孔",
            "shaft",
            "sleeve",
            "washer",
            "flange",
            "pulley",
            "knob",
            "cone",
            "turned",
            "lathe",
            "revolve",
            "bore",
            "annular groove",
        ),
        reason="请求以 rotational 主导几何为主，半剖轮廓旋转后再用旋转切除表达孔、槽和退刀结构，后续改尺寸更稳定。",
        alternatives=("stacked_cylindrical_extrudes", "extrude_circles_from_multiple_planes"),
        priority=80,
        assumptions=("front_plane_half_section", "axis_defined_by_profile_segment"),
    ),
    StrategyRule(
        name="extrude_base_then_face_derived_cut_extrude",
        dominant_geometry="face_derived_prismatic",
        recommended_primitives=(
            "start_sketch",
            "add_center_rectangle/add_polyline",
            "add_dimensions",
            "validate_fully_constrained",
            "extrude",
            "start_sketch_on_face",
            "convert_entities",
            "offset_entities",
            "trim_entities/delete_entities",
            "add_dimensions",
            "validate_fully_constrained",
            "cut_extrude",
        ),
        keywords=(
            "已有面",
            "生成面",
            "上表面",
            "侧面",
            "面边界",
            "边缘",
            "开口槽",
            "边缘缺口",
            "u形槽",
            "u 形槽",
            "边上切",
            "内缩",
            "等距",
            "密封槽",
            "轮廓等距",
            "转换实体",
            "offset",
            "convert",
            "edge notch",
            "open slot",
            "inset",
            "gasket",
        ),
        reason="请求需要引用已生成面或边界来定位局部切除，应先建主实体，再在目标面上转换/等距/清理引用几何，最后切除。",
        alternatives=("direct_unreferenced_cut_sketch", "leave_reference_loop_in_final_sketch"),
        priority=75,
        assumptions=("named_or_selected_target_face", "reference_geometry_cleaned_before_cut"),
    ),
    StrategyRule(
        name="sketch_level_optimized_extrude_or_cut",
        dominant_geometry="sketch_optimized_prismatic",
        recommended_primitives=(
            "start_sketch",
            "add_center_rectangle/add_straight_slot/add_polygon/add_spline",
            "add_dimensions",
            "sketch_fillet/sketch_chamfer",
            "add_mirrored_circle/add_circle_linear_pattern",
            "validate_fully_constrained",
            "extrude/cut_extrude",
        ),
        keywords=(
            "草图圆角",
            "草图倒角",
            "镜像孔",
            "阵列孔",
            "腰形孔",
            "直槽口",
            "多边形",
            "样条",
            "草图优化",
            "fillet",
            "chamfer",
            "mirror",
            "pattern",
            "straight slot",
            "polygon",
            "spline",
        ),
        reason="请求中的圆角、倒角、镜像、阵列或曲线形状适合在草图阶段完成，以减少后续实体特征数量并保持可编辑约束。",
        alternatives=("separate_feature_fillet_chamfer", "one_feature_per_hole"),
        priority=70,
        assumptions=("driving_dimensions_before_sketch_edit_commands",),
    ),
    StrategyRule(
        name="extrude_then_cut_extrude",
        dominant_geometry="prismatic",
        recommended_primitives=(
            "start_sketch",
            "add_center_rectangle/add_polyline",
            "add_dimensions",
            "validate_fully_constrained",
            "extrude",
            "start_sketch_on_face",
            "add_circle/add_straight_slot/add_polygon",
            "add_dimensions",
            "validate_fully_constrained",
            "cut_extrude",
        ),
        keywords=(
            "板",
            "安装板",
            "底板",
            "面板",
            "盖板",
            "块",
            "凸台",
            "支架",
            "固定座",
            "支撑座",
            "连接件",
            "矩形",
            "方形",
            "孔",
            "槽",
            "口袋",
            "窗口",
            "plate",
            "block",
            "bracket",
            "boss",
            "pocket",
            "window",
            "slot",
            "hole",
        ),
        reason="请求以 prismatic 主导几何为主，优先用拉伸主实体和拉伸切除表达。",
        alternatives=("revolve_for_non_rotational_body", "large_single_unreadable_sketch"),
        priority=50,
        assumptions=("top_face_for_secondary_cut_sketches",),
    ),
)

PRISMATIC_DOMINANT_KEYWORDS = (
    "板",
    "安装板",
    "底板",
    "面板",
    "盖板",
    "块",
    "支架",
    "固定座",
    "支撑座",
    "连接件",
    "矩形",
    "方形",
    "plate",
    "block",
    "bracket",
)

ROTATIONAL_DOMINANT_KEYWORDS = (
    "轴",
    "阶梯轴",
    "套筒",
    "垫圈",
    "法兰",
    "旋钮",
    "圆锥",
    "皮带轮",
    "车削",
    "回转",
    "旋转体",
    "圆柱",
    "圆盘",
    "shaft",
    "sleeve",
    "washer",
    "flange",
    "pulley",
    "knob",
    "cone",
    "turned",
    "lathe",
    "cylinder",
    "disk",
)

PRISMATIC_STRATEGIES = {
    "extrude_then_cut_extrude",
    "sketch_level_optimized_extrude_or_cut",
    "extrude_base_then_face_derived_cut_extrude",
}


def _normalize_request(request: str) -> str:
    return re.sub(r"\s+", "", request.lower())


def _keyword_hits(text: str, collapsed_text: str, keywords: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        normalized_keyword = keyword.lower()
        collapsed_keyword = re.sub(r"\s+", "", normalized_keyword)
        if normalized_keyword in text or collapsed_keyword in collapsed_text:
            hits.append(keyword)
    return hits


def _detect_intent(collapsed_text: str) -> str:
    if any(keyword in collapsed_text for keyword in ("装配", "装配体", "assembly")):
        return "assembly_planning"
    if any(keyword in collapsed_text for keyword in ("二维图", "工程图", "出图", "drawing")):
        return "drawing_planning"
    if any(keyword in collapsed_text for keyword in ("逆向", "图纸重建", "reverse")):
        return "reverse_modeling_planning"
    return "part_modeling"


def _detect_dimensions(request: str) -> list[str]:
    return [match.group(0).strip() for match in DIMENSION_RE.finditer(request) if match.group(0).strip()]


def _has_any(collapsed_text: str, keywords: tuple[str, ...]) -> bool:
    return any(re.sub(r"\s+", "", keyword.lower()) in collapsed_text for keyword in keywords)


def _build_questions(rule: StrategyRule, request: str, collapsed_text: str, dimensions: list[str]) -> list[str]:
    questions: list[str] = []

    if not dimensions:
        questions.append("请补充关键外形尺寸、主要特征尺寸和单位；默认单位可以按 mm 处理。")

    mentions_obround_slot = _has_any(collapsed_text, ("长圆孔", "腰形孔", "straight slot", "obround"))
    mentions_hole = _has_any(collapsed_text, ("孔", "hole", "bore", "中心孔", "螺纹孔"))
    mentions_non_slot_hole = mentions_hole and not (
        mentions_obround_slot
        and not _has_any(collapsed_text, ("中心孔", "四角孔", "安装孔", "螺栓孔", "定位孔", "销孔", "沉头孔", "沉孔", "螺纹孔", "通孔"))
    )
    has_hole_size = _has_any(collapsed_text, ("直径", "孔径", "m3", "m4", "m5", "m6", "m8", "m10", "diameter", "dia"))
    has_explicit_hole_positions = bool(
        re.search(
            r"x\s*[:：=]?\s*-?\d+(?:\.\d+)?\s*[,，/\s]*y\s*[:：=]?\s*-?\d+(?:\.\d+)?",
            request,
            re.IGNORECASE,
        )
    ) or bool(
        re.search(
            r"(?:位置|坐标)[^。；;]{0,24}?\(\s*-?\d+(?:\.\d+)?\s*[,，]\s*-?\d+(?:\.\d+)?\s*\)",
            request,
            re.IGNORECASE,
        )
    )
    has_slot_size = mentions_obround_slot and _has_any(collapsed_text, ("槽长", "槽宽", "长度", "宽度", "长", "宽"))
    if mentions_non_slot_hole and not mentions_obround_slot and not has_hole_size:
        questions.append("孔类特征需要孔径或螺纹规格，例如直径 6 mm 或 M6。")

    hole_role_hits = {
        "fastener": _has_any(collapsed_text, ("安装孔", "四角孔", "四角安装孔", "四个安装孔", "螺栓孔", "螺钉孔", "固定孔", "bolt", "screw", "fastener")),
        "locating": _has_any(collapsed_text, ("定位孔", "销孔", "定位销")),
        "threaded": _has_any(collapsed_text, ("螺纹孔", "螺纹", "攻丝")),
        "bearing": _has_any(collapsed_text, ("轴承孔", "轴承座", "bearing")),
        "routing": _has_any(collapsed_text, ("过线孔", "走线孔", "线缆孔", "cable", "routing")),
        "lightening": _has_any(collapsed_text, ("减重孔", "轻量化孔", "lightening")),
        "simple": _has_any(collapsed_text, ("通孔", "中心孔", "中间孔")),
    }
    if mentions_non_slot_hole and not any(hole_role_hits.values()):
        questions.append("请说明这个孔的工程作用：安装孔、定位孔、螺纹孔、轴承孔、过线孔还是减重孔。")
    if hole_role_hits["locating"] and not _has_any(collapsed_text, ("公差", "配合", "h7", "h8", "g6", "过盈", "间隙")):
        questions.append("定位孔需要实际孔径和配合/公差，例如 Φ6H7 配定位销。")
    if hole_role_hits["bearing"] and not _has_any(collapsed_text, ("公差", "配合", "h7", "n6", "p6", "过盈", "间隙", "轴承型号", "外径")):
        questions.append("轴承孔需要轴承型号或配合孔径/公差，例如 6201 外径 32，孔 H7。")

    if (
        mentions_non_slot_hole
        and not (mentions_obround_slot and has_slot_size)
        and not has_explicit_hole_positions
        and not _has_any(collapsed_text, ("中心", "四角", "孔距", "坐标", "分布", "阵列", "同心", "center", "pattern", "pitch"))
    ):
        questions.append("请说明孔的位置基准，例如中心、四角孔距、坐标或阵列间距。")

    if rule.name == "sweep_or_cut_sweep":
        if not _has_any(collapsed_text, ("路径", "沿", "圆弧", "直线", "样条", "path", "arc", "line", "spline")):
            questions.append("扫描需要路径定义：直线、圆弧、样条，或沿哪条已有边/草图。")
        if not _has_any(collapsed_text, ("截面", "圆管", "矩形", "直径", "半径", "profile", "section", "diameter", "radius")):
            questions.append("扫描需要截面尺寸，例如圆截面直径或矩形截面宽高。")

    if rule.name == "ordered_profiles_loft_or_cut_loft":
        if not _has_any(collapsed_text, ("入口", "出口", "截面", "半径", "直径", "轮廓", "profile", "section", "inlet", "outlet")):
            questions.append("放样需要至少两个有序截面的位置和尺寸，例如入口截面、出口截面和间距。")

    if rule.name == "extrude_base_then_face_derived_cut_extrude":
        if not _has_any(collapsed_text, ("上表面", "下表面", "侧面", "边缘", "已有面", "生成面", "top", "side", "edge", "face")):
            questions.append("面引用切除需要说明目标面或边，例如上表面、侧面、某个命名面或边缘。")

    return questions


def _score_rules(request: str, collapsed_text: str) -> list[tuple[StrategyRule, list[str], int]]:
    scores: list[tuple[StrategyRule, list[str], int]] = []
    for rule in STRATEGY_RULES:
        hits = _keyword_hits(request.lower(), collapsed_text, rule.keywords)
        if not hits:
            continue
        score = rule.priority + len(set(hits)) * 8
        scores.append((rule, hits, score))
    return sorted(scores, key=lambda item: (item[2], item[0].priority), reverse=True)


def _default_rule() -> StrategyRule:
    return next(rule for rule in STRATEGY_RULES if rule.name == "extrude_then_cut_extrude")


def _rule_by_name(name: str) -> StrategyRule:
    return next(rule for rule in STRATEGY_RULES if rule.name == name)


def plan_modeling_strategy(request: str) -> StrategyPlan:
    clean_request = request.strip()
    if not clean_request:
        raise ValueError("Natural-language CAD request must not be empty.")

    collapsed_text = _normalize_request(clean_request)
    intent = _detect_intent(collapsed_text)
    dimensions = _detect_dimensions(clean_request)
    scored = _score_rules(clean_request, collapsed_text)

    if scored:
        chosen_rule, matched_keywords, _ = scored[0]
    else:
        chosen_rule = _default_rule()
        matched_keywords = []

    has_prismatic_dominant = _has_any(collapsed_text, PRISMATIC_DOMINANT_KEYWORDS)
    has_rotational_dominant = _has_any(collapsed_text, ROTATIONAL_DOMINANT_KEYWORDS)
    bearing_hole_on_plate = has_prismatic_dominant and _has_any(collapsed_text, ("轴承孔", "轴承座", "bearing"))
    if chosen_rule.name == "revolve_then_cut_revolve" and has_prismatic_dominant and (not has_rotational_dominant or bearing_hole_on_plate):
        prismatic_candidates = [
            (rule, hits, score)
            for rule, hits, score in scored
            if rule.name in PRISMATIC_STRATEGIES
        ]
        if prismatic_candidates:
            chosen_rule, matched_keywords, _ = prismatic_candidates[0]
        else:
            chosen_rule = _rule_by_name("extrude_then_cut_extrude")
            matched_keywords = _keyword_hits(clean_request.lower(), collapsed_text, chosen_rule.keywords)

    alternatives: list[str] = []
    for candidate, _, _ in scored[1:4]:
        if candidate.name != chosen_rule.name:
            alternatives.append(candidate.name)
    for alternative in chosen_rule.alternatives:
        if alternative not in alternatives:
            alternatives.append(alternative)

    questions = _build_questions(chosen_rule, clean_request, collapsed_text, dimensions)
    confidence = min(0.95, 0.45 + len(set(matched_keywords)) * 0.07)
    if not matched_keywords:
        confidence = 0.35
    if questions:
        confidence = max(0.25, confidence - min(0.2, len(questions) * 0.05))

    recommended_primitives = list(chosen_rule.recommended_primitives)
    selection_reason = chosen_rule.reason
    assumptions = list(chosen_rule.assumptions)
    if _has_any(collapsed_text, ("孔向导", "hole wizard", "holewizard")):
        recommended_primitives = [
            "hole_wizard" if primitive == "cut_extrude" else primitive
            for primitive in recommended_primitives
        ]
        if "hole_wizard" not in recommended_primitives:
            recommended_primitives.append("hole_wizard")
        selection_reason = f"{selection_reason} 孔类特征明确要求使用 SolidWorks Hole Wizard。"
        assumptions.append("solidworks_hole_wizard_for_hole_features")

    return StrategyPlan(
        request=clean_request,
        intent=intent,
        dominant_geometry=chosen_rule.dominant_geometry,
        chosen_strategy=chosen_rule.name,
        recommended_job_kind="primitive_part",
        recommended_primitives=recommended_primitives,
        alternatives_considered=alternatives,
        selection_reason=selection_reason,
        assumptions=assumptions,
        questions=questions,
        confidence=round(confidence, 2),
        ready_for_primitive_dsl=not questions and intent == "part_modeling",
        signals={
            "matched_keywords": matched_keywords,
            "detected_dimensions": dimensions,
        },
    )


def plan_modeling_strategy_dict(request: str) -> dict[str, Any]:
    return plan_modeling_strategy(request).to_dict()
