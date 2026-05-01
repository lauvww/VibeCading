from __future__ import annotations

import math
from typing import Any

from adapters.base import BackendUnavailable
from core.dsl import PrimitiveOperation, PrimitivePart


SW_INPUT_DIM_VALUE_ON_CREATE = 10
SW_REF_PLANE_DISTANCE = 8
SWEEP_TWIST_CONTROLS = {
    "follow_path": 0,
    "keep_normal_constant": 1,
    "follow_path_first_guide_curve": 2,
    "follow_first_second_guide_curves": 3,
    "constant_twist": 8,
    "normal_constant_twist": 9,
}
SWEEP_PATH_ALIGNS = {
    "none": 0,
    "normal_to_profile": 1,
    "direction_vector": 2,
    "all_faces": 3,
    "minimum_twist": 10,
}
LOFT_GUIDE_CURVE_INFLUENCES = {
    "next_guide": 0,
    "next_sharp": 1,
    "next_edge": 2,
    "next_global": 3,
    "swguidecurveinfluencenextguide": 0,
    "swguidecurveinfluencenextsharp": 1,
    "swguidecurveinfluencenextedge": 2,
    "swguidecurveinfluencenextglobal": 3,
}
SKETCH_FILLET_CORNER_ACTIONS = {
    "interact": 0,
    "keep_geometry": 1,
    "delete_geometry": 2,
    "stop_processing": 3,
}
SKETCH_CHAMFER_TYPES = {
    "distance_distance": -1,
    "distance_angle": 0,
    "distance_equal": 2,
}
SKETCH_TRIM_OPTIONS = {
    "closest": 0,
    "trim_to_closest": 0,
    "corner": 1,
    "two_entities": 2,
    "to_entity": 2,
    "entity_point": 3,
    "point": 3,
    "power": 4,
    "power_trim": 4,
    "entities": 4,
    "outside": 5,
    "trim_away_outside": 5,
    "inside": 6,
    "trim_away_inside": 6,
}

ORIGINAL_PLANE_ALIASES = {
    "front": {"front", "front_plane", "前视", "前视基准面"},
    "top": {"top", "top_plane", "上视", "上视基准面"},
    "right": {"right", "right_plane", "右视", "右视基准面"},
}

CONSTRAINT_STATUS = {
    1: "unknown",
    2: "under_constrained",
    3: "fully_constrained",
    4: "over_constrained",
    5: "no_solution",
    6: "invalid_solution",
    7: "autosolve_off",
}


def _maybe_call(value):
    if hasattr(value, "_oleobj_"):
        return value
    return value() if callable(value) else value


def _point_tuple(point) -> tuple[float, float]:
    return (float(_maybe_call(point.X)), float(_maybe_call(point.Y)))


class SolidWorksPrimitiveExecutor:
    def __init__(self, sw_app, model) -> None:
        self.sw_app = sw_app
        self.model = model
        self.sketch_manager = model.SketchManager
        self.feature_manager = model.FeatureManager
        self.active_sketch_id: str | None = None
        self.sketches: dict[str, dict[str, object]] = {}
        self.geometry: dict[str, Any] = {}
        self.sketch_geometry: dict[str, list[Any]] = {}
        self.sketch_origin_refs: dict[str, Any] = {}
        self.features: dict[str, Any] = {}
        self.named_faces: dict[str, dict[str, Any]] = {}
        self.reference_planes: dict[str, Any] = {}
        self.circle_specs: dict[str, dict[str, float]] = {}
        self.relations_added = 0
        self.dimensions_added = 0

    def execute(self, part: PrimitivePart) -> list[dict[str, object]]:
        old_input_dim_prompt = bool(self.sw_app.GetUserPreferenceToggle(SW_INPUT_DIM_VALUE_ON_CREATE))
        self.sw_app.SetUserPreferenceToggle(SW_INPUT_DIM_VALUE_ON_CREATE, False)
        reports: list[dict[str, object]] = []
        try:
            for operation in part.operations:
                reports.append(self._execute_operation(operation))
            return reports
        finally:
            self.sw_app.SetUserPreferenceToggle(SW_INPUT_DIM_VALUE_ON_CREATE, old_input_dim_prompt)

    def _execute_operation(self, operation: PrimitiveOperation) -> dict[str, object]:
        if operation.type == "start_sketch":
            return self._start_sketch(operation)
        if operation.type == "start_sketch_on_face":
            return self._start_sketch_on_face(operation)
        if operation.type == "finish_sketch":
            return self._finish_sketch(operation)
        if operation.type == "tag_face":
            return self._tag_face(operation)
        if operation.type == "create_offset_plane":
            return self._create_offset_plane(operation)
        if operation.type == "add_centerline":
            return self._add_centerline(operation)
        if operation.type == "add_polyline":
            return self._add_polyline(operation)
        if operation.type == "add_arc":
            return self._add_arc(operation)
        if operation.type == "add_center_rectangle":
            return self._add_center_rectangle(operation)
        if operation.type == "add_chamfered_rectangle":
            return self._add_chamfered_rectangle(operation)
        if operation.type == "add_straight_slot":
            return self._add_straight_slot(operation)
        if operation.type == "add_polygon":
            return self._add_polygon(operation)
        if operation.type == "add_spline":
            return self._add_spline(operation)
        if operation.type == "add_circle":
            return self._add_circle(operation)
        if operation.type == "add_mirrored_circle":
            return self._add_mirrored_circle(operation)
        if operation.type == "add_circle_linear_pattern":
            return self._add_circle_linear_pattern(operation)
        if operation.type == "add_point":
            return self._add_point(operation)
        if operation.type == "add_axis_constraints":
            return self._add_axis_constraints(operation)
        if operation.type == "add_relation":
            return self._add_relation_operation(operation)
        if operation.type == "add_dimensions":
            return self._add_dimensions(operation)
        if operation.type == "sketch_fillet":
            return self._sketch_fillet(operation)
        if operation.type == "sketch_chamfer":
            return self._sketch_chamfer(operation)
        if operation.type == "fully_define_sketch":
            return self._fully_define_sketch(operation)
        if operation.type == "convert_entities":
            return self._convert_entities(operation)
        if operation.type == "offset_entities":
            return self._offset_entities(operation)
        if operation.type == "trim_entities":
            return self._trim_entities(operation)
        if operation.type == "delete_entities":
            return self._delete_entities(operation)
        if operation.type == "validate_fully_constrained":
            return self._validate_fully_constrained(operation)
        if operation.type == "extrude":
            return self._extrude(operation)
        if operation.type == "cut_extrude":
            return self._cut_extrude(operation)
        if operation.type == "revolve":
            return self._revolve(operation, is_cut=False)
        if operation.type == "cut_revolve":
            return self._revolve(operation, is_cut=True)
        if operation.type == "sweep":
            return self._sweep(operation, is_cut=False)
        if operation.type == "cut_sweep":
            return self._sweep(operation, is_cut=True)
        if operation.type == "loft":
            return self._loft(operation, is_cut=False)
        if operation.type == "cut_loft":
            return self._loft(operation, is_cut=True)
        raise BackendUnavailable(f"Unsupported SolidWorks primitive operation: {operation.type}")

    def _start_sketch(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        plane_ref = str(operation.parameters.get("plane", "base"))
        self.model.ClearSelection2(True)
        plane_name = self._select_sketch_plane(plane_ref)
        self.sketch_manager.InsertSketch(True)
        active_sketch = _maybe_call(self.sketch_manager.ActiveSketch)
        self._try_rename_entity(active_sketch, sketch_id)
        self.active_sketch_id = sketch_id
        self.sketches[sketch_id] = {
            "plane": plane_name,
            "plane_ref": plane_ref,
            "operation_id": operation.id,
            "sketch_object": active_sketch,
        }
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sketch": sketch_id,
            "plane": plane_name,
        }

    def _start_sketch_on_face(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        target = dict(operation.parameters["target"])
        face, face_report = self._find_planar_face(target)
        self.model.ClearSelection2(True)
        if not self._select_entity(face):
            raise BackendUnavailable(f"SolidWorks failed to select target face for sketch: {operation.id}")
        self.sketch_manager.InsertSketch(True)
        active_sketch = _maybe_call(self.sketch_manager.ActiveSketch)
        self._try_rename_entity(active_sketch, sketch_id)
        self.active_sketch_id = sketch_id
        self.sketches[sketch_id] = {
            "plane": "generated_face",
            "operation_id": operation.id,
            "target": target,
            "face": face_report,
            "sketch_object": active_sketch,
        }
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sketch": sketch_id,
            "face": face_report,
        }

    def _finish_sketch(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        self._require_active_sketch(sketch_id)
        self.sketch_manager.InsertSketch(True)
        self.active_sketch_id = None
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sketch": sketch_id,
        }

    def _create_offset_plane(self, operation: PrimitiveOperation) -> dict[str, object]:
        name = str(operation.parameters["name"])
        base_target = operation.parameters.get("base", operation.parameters.get("target", {}))
        offset = self._mm_to_m(operation.parameters["offset"])
        reverse = bool(operation.parameters.get("reverse", False))
        if reverse:
            offset = -offset

        self.model.ClearSelection2(True)
        base_report = self._select_offset_plane_base(base_target, operation.id)

        try:
            feature = self.feature_manager.InsertRefPlane(SW_REF_PLANE_DISTANCE, offset, 0, 0, 0, 0)
        except Exception as exc:
            raise BackendUnavailable(f"SolidWorks failed to create offset plane: {operation.id}") from exc
        finally:
            self.model.ClearSelection2(True)

        if feature is None:
            raise BackendUnavailable(f"SolidWorks failed to create offset plane: {operation.id}")

        feature_name = self._register_feature(operation.id, feature, feature_name=name)
        self.reference_planes[name] = feature
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "name": name,
            "feature_name": feature_name,
            "offset": float(operation.parameters["offset"]),
            "reverse": reverse,
            "base": base_report,
        }

    def _tag_face(self, operation: PrimitiveOperation) -> dict[str, object]:
        name = str(operation.parameters["name"])
        target = dict(operation.parameters["target"])
        face, face_report = self._find_planar_face(target)
        self.named_faces[name] = {
            "face": face,
            "target": target,
            "report": face_report,
        }
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "name": name,
            "face": face_report,
        }

    def _add_centerline(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        start_x, start_y = operation.parameters["start"]
        end_x, end_y = operation.parameters["end"]
        line = self.sketch_manager.CreateCenterLine(
            self._mm_to_m(start_x),
            self._mm_to_m(start_y),
            0,
            self._mm_to_m(end_x),
            self._mm_to_m(end_y),
            0,
        )
        if line is None:
            raise BackendUnavailable(f"SolidWorks failed to create centerline: {operation.id}")
        self.geometry[operation.id] = line
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
        }

    def _add_polyline(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        raw_points = operation.parameters["points"]
        points = [(self._mm_to_m(point[0]), self._mm_to_m(point[1])) for point in raw_points]
        closed = bool(operation.parameters.get("closed", False))
        segment_count = len(points) if closed else len(points) - 1
        segments = []
        for index in range(segment_count):
            start = points[index]
            end = points[(index + 1) % len(points)]
            segment = self.sketch_manager.CreateLine(start[0], start[1], 0, end[0], end[1], 0)
            if segment is None:
                raise BackendUnavailable(f"SolidWorks failed to create polyline segment: {operation.id}[{index}]")
            segments.append(segment)
        self.geometry[operation.id] = segments
        self._register_sketch_geometry(str(operation.parameters["sketch"]), segments)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "segments": len(segments),
        }

    def _add_arc(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        center_x, center_y = operation.parameters["center"]
        start_x, start_y = operation.parameters["start"]
        end_x, end_y = operation.parameters["end"]
        direction = self._arc_direction(operation.parameters.get("direction", "counterclockwise"))
        arc = self.sketch_manager.CreateArc(
            self._mm_to_m(center_x),
            self._mm_to_m(center_y),
            0,
            self._mm_to_m(start_x),
            self._mm_to_m(start_y),
            0,
            self._mm_to_m(end_x),
            self._mm_to_m(end_y),
            0,
            direction,
        )
        if arc is None:
            raise BackendUnavailable(f"SolidWorks failed to create arc: {operation.id}")
        self.geometry[operation.id] = arc
        self._register_sketch_geometry(str(operation.parameters["sketch"]), [arc])
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "direction": "clockwise" if direction < 0 else "counterclockwise",
        }

    def _add_center_rectangle(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        center_x, center_y = operation.parameters["center"]
        size_x, size_y = operation.parameters["size"]
        x1 = self._mm_to_m(float(center_x) - float(size_x) / 2)
        y1 = self._mm_to_m(float(center_y) - float(size_y) / 2)
        x2 = self._mm_to_m(float(center_x) + float(size_x) / 2)
        y2 = self._mm_to_m(float(center_y) + float(size_y) / 2)
        rectangle = self.sketch_manager.CreateCornerRectangle(x1, y1, 0, x2, y2, 0)
        if rectangle is None:
            raise BackendUnavailable(f"SolidWorks failed to create rectangle: {operation.id}")
        self.geometry[operation.id] = list(rectangle)
        self._register_sketch_geometry(str(operation.parameters["sketch"]), list(rectangle))
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "segments": len(self.geometry[operation.id]),
        }

    def _add_chamfered_rectangle(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        center_x, center_y = [float(item) for item in operation.parameters["center"]]
        size_x, size_y = [float(item) for item in operation.parameters["size"]]
        chamfer = float(operation.parameters["chamfer"])
        x0 = center_x - size_x / 2
        x1 = center_x + size_x / 2
        y0 = center_y - size_y / 2
        y1 = center_y + size_y / 2
        points = [
            (x0 + chamfer, y0),
            (x1 - chamfer, y0),
            (x1, y0 + chamfer),
            (x1, y1 - chamfer),
            (x1 - chamfer, y1),
            (x0 + chamfer, y1),
            (x0, y1 - chamfer),
            (x0, y0 + chamfer),
        ]
        segments = []
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            segment = self.sketch_manager.CreateLine(
                self._mm_to_m(start[0]),
                self._mm_to_m(start[1]),
                0,
                self._mm_to_m(end[0]),
                self._mm_to_m(end[1]),
                0,
            )
            if segment is None:
                raise BackendUnavailable(f"SolidWorks failed to create chamfered rectangle: {operation.id}[{index}]")
            segments.append(segment)
        coincident_relations = 0
        for index, segment in enumerate(segments):
            next_segment = segments[(index + 1) % len(segments)]
            if self._add_relation_to_entities(
                [
                    _maybe_call(segment.GetEndPoint2),
                    _maybe_call(next_segment.GetStartPoint2),
                ],
                "sgCOINCIDENT",
            ):
                coincident_relations += 1
        fixed_relations = 0
        if bool(operation.parameters.get("fix_geometry", True)):
            for segment in segments:
                if self._add_relation(segment, "sgFIXED"):
                    fixed_relations += 1
            self.relations_added += fixed_relations
        self.relations_added += coincident_relations
        self.geometry[operation.id] = segments
        self._register_sketch_geometry(str(operation.parameters["sketch"]), segments)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "segments": len(segments),
            "chamfer": chamfer,
            "coincident_relations": coincident_relations,
            "fixed_relations": fixed_relations,
        }

    def _add_straight_slot(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        definition_mode = str(operation.parameters.get("definition_mode", "native")).lower()
        if bool(operation.parameters.get("fully_define", False)) or definition_mode in {
            "dimensioned_geometry",
            "manual",
        }:
            return self._add_dimensioned_straight_slot(operation)

        center_x, center_y = [float(item) for item in operation.parameters["center"]]
        length = float(operation.parameters["length"])
        width = float(operation.parameters["width"])
        angle = math.radians(float(operation.parameters.get("angle", 0)))
        axis_length = length - width
        ux = math.cos(angle)
        uy = math.sin(angle)
        start_x = center_x - ux * axis_length / 2
        start_y = center_y - uy * axis_length / 2
        end_x = center_x + ux * axis_length / 2
        end_y = center_y + uy * axis_length / 2
        add_dimensions = bool(operation.parameters.get("add_dimensions", True))
        slot = self.sketch_manager.CreateSketchSlot(
            0,
            0,
            self._mm_to_m(width),
            self._mm_to_m(start_x),
            self._mm_to_m(start_y),
            0,
            self._mm_to_m(end_x),
            self._mm_to_m(end_y),
            0,
            self._mm_to_m(center_x),
            self._mm_to_m(center_y),
            0,
            1,
            add_dimensions,
        )
        if slot is None:
            raise BackendUnavailable(f"SolidWorks failed to create straight slot: {operation.id}")
        slot_entities = list(slot) if isinstance(slot, tuple | list) else [slot]
        self.geometry[operation.id] = slot_entities
        self._register_sketch_geometry(str(operation.parameters["sketch"]), slot_entities)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "length": length,
            "width": width,
            "angle": float(operation.parameters.get("angle", 0)),
            "definition_mode": definition_mode,
            "add_dimensions": add_dimensions,
        }

    def _add_dimensioned_straight_slot(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        center_x, center_y = [float(item) for item in operation.parameters["center"]]
        length = float(operation.parameters["length"])
        width = float(operation.parameters["width"])
        angle = math.radians(float(operation.parameters.get("angle", 0)))
        radius = width / 2
        axis_length = length - width
        ux = math.cos(angle)
        uy = math.sin(angle)
        nx = -uy
        ny = ux
        start_center = (center_x - ux * axis_length / 2, center_y - uy * axis_length / 2)
        end_center = (center_x + ux * axis_length / 2, center_y + uy * axis_length / 2)
        p1 = (start_center[0] + nx * radius, start_center[1] + ny * radius)
        p2 = (end_center[0] + nx * radius, end_center[1] + ny * radius)
        p3 = (end_center[0] - nx * radius, end_center[1] - ny * radius)
        p4 = (start_center[0] - nx * radius, start_center[1] - ny * radius)

        top = self.sketch_manager.CreateLine(self._mm_to_m(p1[0]), self._mm_to_m(p1[1]), 0, self._mm_to_m(p2[0]), self._mm_to_m(p2[1]), 0)
        right_arc = self.sketch_manager.CreateArc(
            self._mm_to_m(end_center[0]), self._mm_to_m(end_center[1]), 0,
            self._mm_to_m(p2[0]), self._mm_to_m(p2[1]), 0,
            self._mm_to_m(p3[0]), self._mm_to_m(p3[1]), 0,
            -1,
        )
        bottom = self.sketch_manager.CreateLine(self._mm_to_m(p3[0]), self._mm_to_m(p3[1]), 0, self._mm_to_m(p4[0]), self._mm_to_m(p4[1]), 0)
        left_arc = self.sketch_manager.CreateArc(
            self._mm_to_m(start_center[0]), self._mm_to_m(start_center[1]), 0,
            self._mm_to_m(p4[0]), self._mm_to_m(p4[1]), 0,
            self._mm_to_m(p1[0]), self._mm_to_m(p1[1]), 0,
            -1,
        )
        entities = [top, right_arc, bottom, left_arc]
        if any(entity is None for entity in entities):
            raise BackendUnavailable(f"SolidWorks failed to create dimensioned straight slot: {operation.id}")

        relation_count = 0
        for first, second, relation in [
            (_maybe_call(top.GetEndPoint2), _maybe_call(right_arc.GetStartPoint2), "sgCOINCIDENT"),
            (_maybe_call(right_arc.GetEndPoint2), _maybe_call(bottom.GetStartPoint2), "sgCOINCIDENT"),
            (_maybe_call(bottom.GetEndPoint2), _maybe_call(left_arc.GetStartPoint2), "sgCOINCIDENT"),
            (_maybe_call(left_arc.GetEndPoint2), _maybe_call(top.GetStartPoint2), "sgCOINCIDENT"),
            (top, right_arc, "sgTANGENT"),
            (right_arc, bottom, "sgTANGENT"),
            (bottom, left_arc, "sgTANGENT"),
            (left_arc, top, "sgTANGENT"),
        ]:
            if self._add_relation_to_entities([first, second], relation):
                relation_count += 1
            else:
                raise BackendUnavailable(f"SolidWorks failed to constrain dimensioned straight slot: {operation.id}")

        reference = self._sketch_origin_reference(sketch_id)
        dimensions_added = 0
        extra_relations = 0
        for point, coordinates in [
            (_maybe_call(top.GetStartPoint2), p1),
            (_maybe_call(top.GetEndPoint2), p2),
            (_maybe_call(bottom.GetStartPoint2), p3),
            (_maybe_call(bottom.GetEndPoint2), p4),
            (_maybe_call(left_arc.GetCenterPoint2), start_center),
            (_maybe_call(right_arc.GetCenterPoint2), end_center),
        ]:
            dim_count, rel_count = self._define_point_from_reference(reference, point, coordinates[0], coordinates[1])
            dimensions_added += dim_count
            extra_relations += rel_count

        self.relations_added += relation_count
        self.geometry[operation.id] = entities
        self.geometry[f"{operation.id}_top"] = top
        self.geometry[f"{operation.id}_right_arc"] = right_arc
        self.geometry[f"{operation.id}_bottom"] = bottom
        self.geometry[f"{operation.id}_left_arc"] = left_arc
        self._register_sketch_geometry(sketch_id, entities)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "length": length,
            "width": width,
            "angle": float(operation.parameters.get("angle", 0)),
            "definition_mode": "dimensioned_geometry",
            "relations_added": relation_count + extra_relations,
            "dimensions_added": dimensions_added,
        }

    def _add_polygon(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        if bool(operation.parameters.get("fully_define", False)):
            return self._add_dimensioned_polygon(operation)

        center_x, center_y = [float(item) for item in operation.parameters["center"]]
        radius = float(operation.parameters["radius"])
        sides = int(operation.parameters["sides"])
        angle = math.radians(float(operation.parameters.get("angle", 0)))
        vertex_x = center_x + math.cos(angle) * radius
        vertex_y = center_y + math.sin(angle) * radius
        inscribed = bool(operation.parameters.get("inscribed", False))
        polygon = self.sketch_manager.CreatePolygon(
            self._mm_to_m(center_x),
            self._mm_to_m(center_y),
            0,
            self._mm_to_m(vertex_x),
            self._mm_to_m(vertex_y),
            0,
            sides,
            inscribed,
        )
        if polygon is None:
            raise BackendUnavailable(f"SolidWorks failed to create polygon: {operation.id}")
        segments = list(polygon) if isinstance(polygon, (list, tuple)) else [polygon]
        self.geometry[operation.id] = segments
        self._register_sketch_geometry(str(operation.parameters["sketch"]), segments)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sides": sides,
            "radius": radius,
            "angle": float(operation.parameters.get("angle", 0)),
            "inscribed": inscribed,
        }

    def _add_dimensioned_polygon(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        center_x, center_y = [float(item) for item in operation.parameters["center"]]
        radius = float(operation.parameters["radius"])
        sides = int(operation.parameters["sides"])
        angle = math.radians(float(operation.parameters.get("angle", 0)))
        vertices = [
            (
                center_x + math.cos(angle + 2 * math.pi * index / sides) * radius,
                center_y + math.sin(angle + 2 * math.pi * index / sides) * radius,
            )
            for index in range(sides)
        ]
        segments = []
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % sides]
            segment = self.sketch_manager.CreateLine(
                self._mm_to_m(start[0]), self._mm_to_m(start[1]), 0,
                self._mm_to_m(end[0]), self._mm_to_m(end[1]), 0,
            )
            if segment is None:
                raise BackendUnavailable(f"SolidWorks failed to create dimensioned polygon: {operation.id}[{index}]")
            segments.append(segment)

        relation_count = 0
        for index, segment in enumerate(segments):
            next_segment = segments[(index + 1) % sides]
            if self._add_relation_to_entities(
                [_maybe_call(segment.GetEndPoint2), _maybe_call(next_segment.GetStartPoint2)],
                "sgCOINCIDENT",
            ):
                relation_count += 1
            else:
                raise BackendUnavailable(f"SolidWorks failed to close dimensioned polygon: {operation.id}")

        reference = self._sketch_origin_reference(sketch_id)
        dimensions_added = 0
        extra_relations = 0
        for segment, coordinates in zip(segments, vertices):
            dim_count, rel_count = self._define_point_from_reference(
                reference,
                _maybe_call(segment.GetStartPoint2),
                coordinates[0],
                coordinates[1],
            )
            dimensions_added += dim_count
            extra_relations += rel_count

        self.relations_added += relation_count
        self.geometry[operation.id] = segments
        self._register_sketch_geometry(sketch_id, segments)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sides": sides,
            "radius": radius,
            "angle": float(operation.parameters.get("angle", 0)),
            "definition_mode": "dimensioned_geometry",
            "relations_added": relation_count + extra_relations,
            "dimensions_added": dimensions_added,
        }

    def _add_spline(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        points = [[float(point[0]), float(point[1])] for point in operation.parameters["points"]]
        closed = bool(operation.parameters.get("closed", False))
        if closed and points[0] != points[-1]:
            points.append(points[0])
        fit_point_refs = []
        if bool(operation.parameters.get("create_fit_point_refs", False)):
            for index, (point_x, point_y) in enumerate(points):
                point = self.sketch_manager.CreatePoint(self._mm_to_m(point_x), self._mm_to_m(point_y), 0)
                if point is None:
                    raise BackendUnavailable(f"SolidWorks failed to create spline fit point reference: {operation.id}[{index}]")
                fit_point_refs.append(point)
        point_data = []
        for point_x, point_y in points:
            point_data.extend([self._mm_to_m(point_x), self._mm_to_m(point_y), 0])

        spline = None
        try:
            from win32com.client import VARIANT
            import pythoncom

            point_variant = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, point_data)
        except Exception:
            point_variant = point_data
        for method_name, args in [
            ("CreateSpline2", (point_variant, closed)),
            ("CreateSpline2", (point_data, closed)),
            ("CreateSpline", (point_variant,)),
            ("CreateSpline", (point_data,)),
        ]:
            try:
                method = getattr(self.sketch_manager, method_name)
            except Exception:
                continue
            try:
                spline = method(*args)
            except Exception:
                continue
            if spline is not None:
                break
        if spline is None:
            raise BackendUnavailable(f"SolidWorks failed to create spline: {operation.id}")
        self.geometry[operation.id] = spline
        spline_points = self._spline_points(spline)
        spline_point_relations = 0
        if fit_point_refs:
            spline_points = fit_point_refs
            for index, point in enumerate(spline_points):
                if not self._add_relation_to_entities([point, spline], "sgCOINCIDENT"):
                    raise BackendUnavailable(f"SolidWorks failed to bind spline fit point reference: {operation.id}[{index}]")
                spline_point_relations += 1
            self.relations_added += spline_point_relations
        if len(spline_points) < len(points):
            spline_points = []
            for index, (point_x, point_y) in enumerate(points):
                self.model.ClearSelection2(True)
                point = self.sketch_manager.CreatePoint(self._mm_to_m(point_x), self._mm_to_m(point_y), 0)
                if point is None:
                    raise BackendUnavailable(f"SolidWorks failed to create spline fit point reference: {operation.id}[{index}]")
                if not self._add_relation_to_entities([point, spline], "sgCOINCIDENT"):
                    raise BackendUnavailable(f"SolidWorks failed to bind spline fit point reference: {operation.id}[{index}]")
                spline_point_relations += 1
                spline_points.append(point)
            self.relations_added += spline_point_relations
        for index, point in enumerate(spline_points):
            self.geometry[f"{operation.id}_point_{index}"] = point
        if spline_points:
            self.geometry[f"{operation.id}_start"] = spline_points[0]
            self.geometry[f"{operation.id}_end"] = spline_points[-1]
        self._register_sketch_geometry(str(operation.parameters["sketch"]), [spline])
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "points": len(points),
            "registered_points": len(spline_points),
            "point_binding_relations": spline_point_relations,
            "closed": closed,
        }

    def _add_circle(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        center_x, center_y = operation.parameters["center"]
        diameter = float(operation.parameters["diameter"])
        circle = self.sketch_manager.CreateCircleByRadius(
            self._mm_to_m(center_x),
            self._mm_to_m(center_y),
            0,
            self._mm_to_m(diameter / 2),
        )
        if circle is None:
            raise BackendUnavailable(f"SolidWorks failed to create circle: {operation.id}")
        self.geometry[operation.id] = circle
        self.circle_specs[operation.id] = {
            "center_x": float(center_x),
            "center_y": float(center_y),
            "diameter": diameter,
        }
        self._register_sketch_geometry(str(operation.parameters["sketch"]), [circle])
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "diameter": diameter,
        }

    def _add_mirrored_circle(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        center_x, center_y = operation.parameters["center"]
        diameter = float(operation.parameters["diameter"])
        axis = self._resolve_entity(operation.parameters["axis"])
        self.model.ClearSelection2(True)
        if not self._select_entity(axis):
            raise BackendUnavailable(f"SolidWorks failed to select mirror axis: {operation.id}")
        try:
            self.sketch_manager.SetDynamicMirror(True)
            circle = self.sketch_manager.CreateCircleByRadius(
                self._mm_to_m(center_x),
                self._mm_to_m(center_y),
                0,
                self._mm_to_m(diameter / 2),
            )
        except Exception as exc:
            raise BackendUnavailable(f"SolidWorks failed to create mirrored circle: {operation.id}") from exc
        finally:
            try:
                self.sketch_manager.SetDynamicMirror(False)
            except Exception:
                pass
            self.model.ClearSelection2(True)
        if circle is None:
            raise BackendUnavailable(f"SolidWorks failed to create mirrored circle: {operation.id}")
        self.geometry[operation.id] = circle
        self.circle_specs[operation.id] = {
            "center_x": float(center_x),
            "center_y": float(center_y),
            "diameter": diameter,
        }
        self._register_sketch_geometry(str(operation.parameters["sketch"]), [circle])
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "diameter": diameter,
            "mirrored": True,
        }

    def _add_circle_linear_pattern(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        source_id = str(operation.parameters["source"])
        source = self.circle_specs.get(source_id)
        if source is None:
            raise BackendUnavailable(f"Unknown source circle for sketch pattern: {source_id}")
        count = int(operation.parameters["count"])
        spacing_x, spacing_y = [float(item) for item in operation.parameters["spacing"]]
        fix_copies = bool(operation.parameters.get("fix_copies", False))
        circles = []
        fixed_relations = 0
        for index in range(1, count):
            center_x = source["center_x"] + spacing_x * index
            center_y = source["center_y"] + spacing_y * index
            circle = self.sketch_manager.CreateCircleByRadius(
                self._mm_to_m(center_x),
                self._mm_to_m(center_y),
                0,
                self._mm_to_m(source["diameter"] / 2),
            )
            if circle is None:
                raise BackendUnavailable(f"SolidWorks failed to create sketch circle pattern: {operation.id}[{index}]")
            circles.append(circle)
            copy_id = f"{operation.id}_{index}"
            self.geometry[copy_id] = circle
            self.circle_specs[copy_id] = {
                "center_x": center_x,
                "center_y": center_y,
                "diameter": source["diameter"],
            }
            if fix_copies and self._add_relation(circle, "sgFIXED"):
                fixed_relations += 1
        self.geometry[operation.id] = circles
        self.relations_added += fixed_relations
        self._register_sketch_geometry(str(operation.parameters["sketch"]), circles)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "source": source_id,
            "count": count,
            "copies_created": len(circles),
            "fixed_relations": fixed_relations,
        }

    def _add_point(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        point_x, point_y = operation.parameters["point"]
        point = self.sketch_manager.CreatePoint(self._mm_to_m(point_x), self._mm_to_m(point_y), 0)
        if point is None:
            raise BackendUnavailable(f"SolidWorks failed to create point: {operation.id}")
        self.geometry[operation.id] = point
        self._register_sketch_geometry(str(operation.parameters["sketch"]), [point])
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
        }

    def _add_axis_constraints(self, operation: PrimitiveOperation) -> dict[str, object]:
        profile_id = str(operation.parameters["profile"])
        segments = self._resolve_profile_segments(profile_id)
        failed: list[str] = []
        added = 0
        for index, segment in enumerate(segments):
            start_x, start_y = _point_tuple(_maybe_call(segment.GetStartPoint2))
            end_x, end_y = _point_tuple(_maybe_call(segment.GetEndPoint2))
            if abs(start_y - end_y) <= 1e-9:
                relation = "sgHORIZONTAL2D"
            elif abs(start_x - end_x) <= 1e-9:
                relation = "sgVERTICAL2D"
            else:
                failed.append(f"{profile_id}[{index}]")
                continue
            if self._add_relation(segment, relation):
                added += 1
            else:
                failed.append(f"{profile_id}[{index}]")
        if failed:
            raise BackendUnavailable(f"SolidWorks failed to add axis constraints: {', '.join(failed)}")
        self.relations_added += added
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "relations_added": added,
        }

    def _add_relation_operation(self, operation: PrimitiveOperation) -> dict[str, object]:
        relation_name = str(operation.parameters["relation"]).lower()
        relation = {
            "fixed": "sgFIXED",
            "horizontal": "sgHORIZONTAL2D",
            "vertical": "sgVERTICAL2D",
            "coincident": "sgCOINCIDENT",
            "tangent": "sgTANGENT",
            "curvature": "sgCURVATURE",
            "equal_curvature": "sgCURVATURE",
            "pierce": "sgATPIERCE",
        }.get(relation_name)
        if relation is None:
            raise BackendUnavailable(f"Unsupported SolidWorks relation: {relation_name}")
        entities = (
            [self._resolve_entity(item) for item in operation.parameters["entities"]]
            if "entities" in operation.parameters
            else [self._resolve_entity(operation.parameters["entity"])]
        )
        if not self._add_relation_to_entities(entities, relation):
            raise BackendUnavailable(f"SolidWorks failed to add relation: {operation.id}")
        self.relations_added += 1
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "relation": relation_name,
            "relations_added": 1,
        }

    def _add_dimensions(self, operation: PrimitiveOperation) -> dict[str, object]:
        failed: list[str] = []
        added = 0
        for index, dimension in enumerate(operation.parameters["dimensions"]):
            label = str(dimension.get("id", f"dimension_{index + 1}"))
            position = self._position(dimension["position"])
            dimension_type = str(dimension["type"]).lower()
            if dimension_type == "entity":
                ok = self._dimension_entity(self._resolve_entity(dimension["entity"]), *position)
            elif dimension_type == "horizontal_between":
                ok = self._dimension_horizontal(
                    self._resolve_entity(dimension["first"]),
                    self._resolve_entity(dimension["second"]),
                    *position,
                )
            elif dimension_type == "vertical_between":
                ok = self._dimension_vertical(
                    self._resolve_entity(dimension["first"]),
                    self._resolve_entity(dimension["second"]),
                    *position,
                )
            else:
                raise BackendUnavailable(f"Unsupported dimension primitive: {dimension_type}")
            if ok:
                added += 1
            else:
                failed.append(label)
        if failed:
            raise BackendUnavailable(f"SolidWorks failed to add dimensions: {', '.join(failed)}")
        self.dimensions_added += added
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "dimensions_added": added,
        }

    def _sketch_fillet(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        entities = [self._resolve_entity(item) for item in operation.parameters["entities"]]
        radius = self._mm_to_m(operation.parameters["radius"])
        action = self._enum_value(
            operation.parameters.get("constrained_corner_action", "keep_geometry"),
            SKETCH_FILLET_CORNER_ACTIONS,
        )
        self.model.ClearSelection2(True)
        try:
            for index, entity in enumerate(entities):
                if not self._select_entity(entity, append=index > 0):
                    raise BackendUnavailable(f"SolidWorks failed to select sketch fillet entity: {operation.id}")
            fillet = self.sketch_manager.CreateFillet(radius, action)
        except BackendUnavailable:
            raise
        except Exception as exc:
            raise BackendUnavailable(f"SolidWorks failed to create sketch fillet: {operation.id}") from exc
        finally:
            self.model.ClearSelection2(True)
        if fillet is None:
            raise BackendUnavailable(f"SolidWorks failed to create sketch fillet: {operation.id}")
        self.geometry[operation.id] = fillet
        self._register_sketch_geometry(str(operation.parameters["sketch"]), [fillet])
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "radius": float(operation.parameters["radius"]),
            "constrained_corner_action": action,
        }

    def _sketch_chamfer(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        entities = [self._resolve_entity(item) for item in operation.parameters["entities"]]
        chamfer_type = self._enum_value(
            operation.parameters.get("chamfer_type", "distance_equal"),
            SKETCH_CHAMFER_TYPES,
        )
        distance = self._mm_to_m(operation.parameters["distance"])
        if chamfer_type == -1:
            distance_or_angle = self._mm_to_m(operation.parameters["distance2"])
        elif chamfer_type == 0:
            distance_or_angle = math.radians(float(operation.parameters["angle"]))
        else:
            distance_or_angle = distance
        self.model.ClearSelection2(True)
        try:
            for index, entity in enumerate(entities):
                if not self._select_entity(entity, append=index > 0):
                    raise BackendUnavailable(f"SolidWorks failed to select sketch chamfer entity: {operation.id}")
            chamfer = self.sketch_manager.CreateChamfer(chamfer_type, distance, distance_or_angle)
        except BackendUnavailable:
            raise
        except Exception as exc:
            raise BackendUnavailable(f"SolidWorks failed to create sketch chamfer: {operation.id}") from exc
        finally:
            self.model.ClearSelection2(True)
        if chamfer is None:
            raise BackendUnavailable(f"SolidWorks failed to create sketch chamfer: {operation.id}")
        self.geometry[operation.id] = chamfer
        self._register_sketch_geometry(str(operation.parameters["sketch"]), [chamfer])
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "distance": float(operation.parameters["distance"]),
            "chamfer_type": chamfer_type,
        }

    def _validate_fully_constrained(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        active_sketch = self.sketch_manager.ActiveSketch
        status_code = int(_maybe_call(active_sketch.GetConstrainedStatus))
        status = CONSTRAINT_STATUS.get(status_code, "unknown")
        report = {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "status_code": status_code,
            "status": status,
            "fully_constrained": status_code == 3,
            "relations_added_total": self.relations_added,
            "dimensions_added_total": self.dimensions_added,
        }
        if status_code != 3:
            raise BackendUnavailable(
                "SolidWorks primitive sketch is not fully constrained. "
                f"Status: {status}; operation: {operation.id}"
            )
        return report

    def _fully_define_sketch(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        self._require_active_sketch(sketch_id)
        all_entities = bool(operation.parameters.get("all_entities", True))
        apply_relations = bool(operation.parameters.get("apply_relations", True))
        apply_dimensions = bool(operation.parameters.get("apply_dimensions", True))
        relation_mask = int(operation.parameters.get("relation_mask", 1023))
        horizontal_scheme = int(operation.parameters.get("horizontal_scheme", 1))
        vertical_scheme = int(operation.parameters.get("vertical_scheme", 1))
        horizontal_placement = int(operation.parameters.get("horizontal_placement", 1))
        vertical_placement = int(operation.parameters.get("vertical_placement", 1))
        common_datum = operation.parameters.get("datum")
        horizontal_datum = operation.parameters.get("horizontal_datum", common_datum)
        vertical_datum = operation.parameters.get("vertical_datum", common_datum)
        horizontal_datum_entity = self._resolve_entity(horizontal_datum) if horizontal_datum else None
        vertical_datum_entity = self._resolve_entity(vertical_datum) if vertical_datum else None
        method_errors: list[str] = []
        datum_variants = [(horizontal_datum_entity, vertical_datum_entity)]
        if horizontal_datum_entity is not None or vertical_datum_entity is not None:
            datum_variants.append((None, None))
        for horizontal_datum_item, vertical_datum_item in datum_variants:
            args = (
                all_entities,
                apply_relations,
                relation_mask,
                apply_dimensions,
                horizontal_scheme,
                horizontal_datum_item,
                vertical_scheme,
                vertical_datum_item,
                horizontal_placement,
                vertical_placement,
            )
            if (
                horizontal_datum_item is None
                and vertical_datum_item is None
                and common_datum is not None
                and bool(operation.parameters.get("select_datum_when_null", True))
            ):
                self.model.ClearSelection2(True)
                datum_entity = self._resolve_entity(common_datum)
                if self._select_entity(datum_entity, mark=int(operation.parameters.get("datum_selection_mark", 6))):
                    method_errors.append("Selected datum by mark for null datum fallback.")
                else:
                    method_errors.append("Failed to select datum by mark for null datum fallback.")
                    continue
            else:
                self.model.ClearSelection2(True)

            for owner_name, owner in [
                ("SketchManager", self.sketch_manager),
                ("ModelDoc2", self.model),
            ]:
                try:
                    method = getattr(owner, "FullyDefineSketch")
                except Exception:
                    continue
                try:
                    result = method(*args)
                    self.model.ClearSelection2(True)
                    return {
                        "operation_id": operation.id,
                        "operation_type": operation.type,
                        "sketch": sketch_id,
                        "method": owner_name,
                        "result": result,
                        "all_entities": all_entities,
                        "apply_relations": apply_relations,
                        "apply_dimensions": apply_dimensions,
                        "relation_mask": relation_mask,
                        "horizontal_scheme": horizontal_scheme,
                        "vertical_scheme": vertical_scheme,
                        "has_horizontal_datum": horizontal_datum_entity is not None,
                        "has_vertical_datum": vertical_datum_entity is not None,
                    }
                except Exception as exc:
                    method_errors.append(f"{owner_name}: {exc}")
            self.model.ClearSelection2(True)

        error_suffix = f" ({'; '.join(method_errors)})" if method_errors else ""
        raise BackendUnavailable(f"SolidWorks failed to fully define sketch: {operation.id}{error_suffix}")

    def _convert_entities(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        self._require_active_sketch(sketch_id)
        target = dict(operation.parameters["target"])
        loop_mode = str(operation.parameters.get("loop", target.get("loop", "outer"))).lower()
        chain = bool(operation.parameters.get("chain", target.get("chain", False)))
        inner_loops = bool(operation.parameters.get("inner_loops", loop_mode == "all"))
        prefer_native = bool(operation.parameters.get("prefer_native", True))
        before_count = len(self._active_sketch_segments())

        self.model.ClearSelection2(True)
        target_report: dict[str, object] = {}
        selection_mode = "face"
        conversion_face = None
        if str(target.get("type", "body_face")).lower() == "entities":
            selection_mode = "entities"
            entities = [self._resolve_entity(item) for item in target["entities"]]
            selected = self._select_entities(entities)
            target_report = {"selection_mode": "entities", "entity_count": len(entities)}
        elif loop_mode == "inner":
            selection_mode = "loop_edges"
            conversion_face, target_report = self._find_conversion_face(target)
            edges = self._face_edges_by_loop(conversion_face, loop_mode)
            selected = self._select_entities(edges)
            target_report["converted_loop"] = loop_mode
            target_report["edge_count"] = len(edges)
        else:
            conversion_face, target_report = self._find_conversion_face(target)
            selected = self._select_face_by_report(conversion_face, target_report)
            target_report["converted_loop"] = loop_mode

        if not selected and prefer_native:
            self.model.ClearSelection2(True)
            raise BackendUnavailable(f"SolidWorks failed to select entities for conversion: {operation.id}")

        converted = False
        method_used = ""
        conversion_errors: list[str] = []
        new_segments: list[Any] = []
        if prefer_native:
            for method_name, args in [
                ("SketchUseEdge3", (chain, inner_loops)),
                ("SketchUseEdge2", (chain,)),
                ("SketchUseEdge", (chain,)),
                ("ConvertEntities", ()),
            ]:
                if loop_mode == "inner" and method_name.startswith("SketchUseEdge"):
                    continue
                try:
                    method = getattr(self.sketch_manager, method_name)
                except Exception:
                    continue
                try:
                    result = method(*args)
                    converted = True if result is None else bool(result)
                except Exception as exc:
                    conversion_errors.append(f"{method_name}: {exc}")
                    converted = False
                if converted:
                    method_used = method_name
                    break

        self.model.ClearSelection2(True)
        if not converted and prefer_native:
            error_suffix = f" ({'; '.join(conversion_errors)})" if conversion_errors else ""
            raise BackendUnavailable(f"SolidWorks failed to convert entities: {operation.id}{error_suffix}")

        if converted:
            new_segments = self._active_sketch_segments()[before_count:]
        if not new_segments and conversion_face is not None and selection_mode == "face":
            fallback_edges = self._face_edges_by_loop(conversion_face, loop_mode)
            target_report["edge_count"] = len(fallback_edges)
            if prefer_native:
                for owner_name, owner, method_name, args in [
                    ("ModelDoc2", self.model, "SketchUseEdge2", (False,)),
                    ("ModelDoc2", self.model, "SketchUseEdge", ()),
                    ("SketchManager", self.sketch_manager, "SketchUseEdge2", (False,)),
                    ("SketchManager", self.sketch_manager, "ConvertEntities", ()),
                ]:
                    self.model.ClearSelection2(True)
                    before_count = len(self._active_sketch_segments())
                    if not self._select_entities(fallback_edges):
                        self.model.ClearSelection2(True)
                        raise BackendUnavailable(f"SolidWorks failed to select face loop edges for conversion: {operation.id}")
                    try:
                        method = getattr(owner, method_name)
                        result = method(*args)
                        converted = True if result is None else bool(result)
                    except Exception as exc:
                        conversion_errors.append(f"{owner_name}.{method_name}: {exc}")
                        converted = False
                    finally:
                        self.model.ClearSelection2(True)
                    if converted:
                        new_segments = self._active_sketch_segments()[before_count:]
                        if new_segments:
                            method_used = f"{owner_name}.{method_name}"
                            selection_mode = "loop_edges"
                            break
            if not new_segments:
                self.model.ClearSelection2(True)
                new_segments = self._project_face_edges_as_sketch_segments(sketch_id, fallback_edges, operation.id)
                method_used = "manual_project_edges"
                selection_mode = "projected_loop_edges"
        if not new_segments:
            raise BackendUnavailable(f"SolidWorks converted no sketch entities: {operation.id}")
        self.geometry[operation.id] = new_segments
        for index, segment in enumerate(new_segments):
            self.geometry[f"{operation.id}_{index}"] = segment
        self._register_sketch_geometry(sketch_id, new_segments)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sketch": sketch_id,
            "method": method_used,
            "selection_mode": selection_mode,
            "chain": chain,
            "inner_loops": inner_loops,
            "converted_segments": len(new_segments),
            "target": target_report,
        }

    def _offset_entities(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        self._require_active_sketch(sketch_id)
        source_entities = self._resolve_entity_collection(operation.parameters["source"])
        if not source_entities:
            raise BackendUnavailable(f"Offset source resolved no entities: {operation.id}")

        offset = self._mm_to_m(operation.parameters["offset"])
        direction = str(operation.parameters.get("direction", "default")).lower()
        if bool(operation.parameters.get("reverse", False)) or direction in {"inside", "inward", "negative", "reverse"}:
            offset = -offset
        both_directions = bool(operation.parameters.get("both_directions", False))
        chain = bool(operation.parameters.get("chain", True))
        cap_ends = bool(operation.parameters.get("cap_ends", False))
        cap_ends_type = int(operation.parameters.get("cap_ends_type", 0))
        make_construction = bool(operation.parameters.get("make_construction", False))
        add_dimensions = bool(operation.parameters.get("add_dimensions", True))
        before_count = len(self._active_sketch_segments())

        self.model.ClearSelection2(True)
        if not self._select_entities(source_entities):
            self.model.ClearSelection2(True)
            raise BackendUnavailable(f"SolidWorks failed to select offset source entities: {operation.id}")

        offset_created = False
        method_used = ""
        offset_errors: list[str] = []
        for method_name, args in [
            ("SketchOffset", (offset, both_directions, chain, cap_ends, make_construction, add_dimensions)),
            ("SketchOffset2", (offset, both_directions, chain, cap_ends_type, int(make_construction), add_dimensions)),
        ]:
            try:
                method = getattr(self.sketch_manager, method_name)
            except Exception:
                continue
            try:
                offset_created = bool(method(*args))
            except Exception as exc:
                offset_errors.append(f"{method_name}: {exc}")
                offset_created = False
            if offset_created:
                method_used = method_name
                break

        self.model.ClearSelection2(True)
        if not offset_created:
            error_suffix = f" ({'; '.join(offset_errors)})" if offset_errors else ""
            raise BackendUnavailable(f"SolidWorks failed to offset sketch entities: {operation.id}{error_suffix}")

        new_segments = self._active_sketch_segments()[before_count:]
        if not new_segments:
            raise BackendUnavailable(f"SolidWorks offset created no sketch entities: {operation.id}")
        self.geometry[operation.id] = new_segments
        for index, segment in enumerate(new_segments):
            self.geometry[f"{operation.id}_{index}"] = segment
        self._register_sketch_geometry(sketch_id, new_segments)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sketch": sketch_id,
            "method": method_used,
            "source_entities": len(source_entities),
            "offset": float(operation.parameters["offset"]),
            "direction": direction,
            "both_directions": both_directions,
            "chain": chain,
            "cap_ends": cap_ends,
            "make_construction": make_construction,
            "add_dimensions": add_dimensions,
            "offset_segments": len(new_segments),
        }

    def _trim_entities(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        self._require_active_sketch(sketch_id)
        mode = str(operation.parameters.get("mode", "closest")).strip().lower()
        trim_option = self._enum_value(mode, SKETCH_TRIM_OPTIONS)
        entities, selection_points, boundary_count, trim_target_count = self._trim_selection(operation)
        pick_point_count = len([point for point in selection_points if point is not None])
        before_segments = self._active_sketch_segments()
        method_used = "native"

        self.model.ClearSelection2(True)
        try:
            if trim_option in {0, 3}:
                if len(entities) != 1:
                    raise BackendUnavailable(f"Sketch trim mode {mode} requires exactly one entity: {operation.id}")
                trim_point = self._trim_point(operation, selection_points)
                if not self._select_sketch_segment_for_trim(entities[0], trim_point, append=False, mark=0):
                    raise BackendUnavailable(f"SolidWorks failed to select sketch trim entity: {operation.id}")
                call_point = trim_point if trim_option == 3 else (0.0, 0.0, 0.0)
                trim_result = self._call_sketch_trim(trim_option, call_point)
            elif trim_option == 1:
                if len(entities) != 2:
                    raise BackendUnavailable(f"Sketch trim corner mode requires exactly two entities: {operation.id}")
                for index, entity in enumerate(entities):
                    point = self._trim_selection_point(selection_points, index, entity)
                    if not self._select_sketch_segment_for_trim(entity, point, append=index > 0, mark=0):
                        raise BackendUnavailable(f"SolidWorks failed to select sketch trim corner entity: {operation.id}")
                trim_result = self._call_sketch_trim(trim_option, (0.0, 0.0, 0.0))
            elif trim_option == 2:
                if len(entities) != 2:
                    raise BackendUnavailable(f"Sketch trim two_entities mode requires exactly two entities: {operation.id}")
                for index, entity in enumerate(entities):
                    point = self._trim_selection_point(selection_points, index, entity)
                    if not self._select_sketch_segment_for_trim(entity, point, append=index > 0, mark=0):
                        raise BackendUnavailable(f"SolidWorks failed to select sketch two_entities trim entity: {operation.id}")
                trim_result = self._call_sketch_trim(trim_option, (0.0, 0.0, 0.0))
            elif trim_option == 4:
                if len(selection_points) != len(entities) or any(point is None for point in selection_points):
                    raise BackendUnavailable(
                        f"Sketch power trim requires one pick point per entity: {operation.id}"
                    )
                for index, entity in enumerate(entities):
                    if not self._select_sketch_segment_for_trim(entity, selection_points[index], append=index > 0, mark=0):
                        raise BackendUnavailable(f"SolidWorks failed to select sketch power trim entity: {operation.id}")
                trim_result = self._call_sketch_trim(trim_option, (0.0, 0.0, 0.0))
                if not trim_result:
                    self.model.ClearSelection2(True)
                    trimmed = 0
                    for index, entity in enumerate(entities):
                        if not self._select_sketch_segment_for_trim(entity, selection_points[index], append=False, mark=0):
                            raise BackendUnavailable(
                                f"SolidWorks failed to select sketch power trim fallback entity: {operation.id}"
                            )
                        if self._call_sketch_trim(3, selection_points[index]):
                            trimmed += 1
                        self.model.ClearSelection2(True)
                    trim_result = trimmed == len(entities)
                    method_used = "entity_point_fallback"
            elif trim_option in {5, 6}:
                if len(entities) < 3:
                    raise BackendUnavailable(f"Sketch inside/outside trim requires at least three entities: {operation.id}")
                for index, entity in enumerate(entities):
                    point = self._trim_selection_point(selection_points, index, entity)
                    if not self._select_sketch_segment_for_trim(entity, point, append=index > 0, mark=0):
                        raise BackendUnavailable(f"SolidWorks failed to select sketch inside/outside trim entity: {operation.id}")
                trim_result = self._call_sketch_trim(trim_option, (0.0, 0.0, 0.0))
            else:
                raise BackendUnavailable(f"Unsupported sketch trim mode: {mode}")
        finally:
            self.model.ClearSelection2(True)

        if not trim_result:
            raise BackendUnavailable(f"SolidWorks failed to trim sketch entities: {operation.id}")

        after_segments = self._active_sketch_segments()
        self.geometry[operation.id] = after_segments
        self.sketch_geometry[sketch_id] = after_segments
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sketch": sketch_id,
            "mode": mode,
            "trim_option": trim_option,
            "method": method_used,
            "selected_entities": len(entities),
            "boundary_entities": boundary_count,
            "trim_targets": trim_target_count,
            "pick_points": pick_point_count,
            "trim_point_provided": any(key in operation.parameters for key in ("trim_point", "point", "pick_point")),
            "segments_before": len(before_segments),
            "segments_after": len(after_segments),
        }

    def _delete_entities(self, operation: PrimitiveOperation) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        self._require_active_sketch(sketch_id)
        entities = [
            entity
            for item in operation.parameters["entities"]
            for entity in self._resolve_entity_collection(item)
        ]
        if not entities:
            raise BackendUnavailable(f"Delete source resolved no entities: {operation.id}")
        before_segments = self._active_sketch_segments()

        self.model.ClearSelection2(True)
        if not self._select_entities(entities):
            self.model.ClearSelection2(True)
            raise BackendUnavailable(f"SolidWorks failed to select sketch entities for deletion: {operation.id}")

        method_used = ""
        deleted = False
        delete_errors: list[str] = []
        try:
            try:
                deleted = bool(self.model.Extension.DeleteSelection2(0))
                if deleted:
                    method_used = "ModelDocExtension.DeleteSelection2"
            except Exception as exc:
                delete_errors.append(f"DeleteSelection2: {exc}")
                deleted = False

            if not deleted:
                try:
                    result = self.model.EditDelete()
                    deleted = True if result is None else bool(result)
                    if deleted:
                        method_used = "ModelDoc2.EditDelete"
                except Exception as exc:
                    delete_errors.append(f"EditDelete: {exc}")
                    deleted = False
        finally:
            self.model.ClearSelection2(True)

        if not deleted:
            error_suffix = f" ({'; '.join(delete_errors)})" if delete_errors else ""
            raise BackendUnavailable(f"SolidWorks failed to delete sketch entities: {operation.id}{error_suffix}")

        after_segments = self._active_sketch_segments()
        self.sketch_geometry[sketch_id] = after_segments
        self.geometry[operation.id] = after_segments
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "sketch": sketch_id,
            "method": method_used,
            "selected_entities": len(entities),
            "segments_before": len(before_segments),
            "segments_after": len(after_segments),
        }

    def _extrude(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        depth = self._mm_to_m(operation.parameters["depth"])
        self.sketch_manager.InsertSketch(True)
        feature = self.feature_manager.FeatureExtrusion2(
            True,
            False,
            False,
            0,
            0,
            depth,
            0,
            False,
            False,
            False,
            False,
            0,
            0,
            False,
            False,
            False,
            False,
            True,
            True,
            True,
            0,
            0,
            False,
        )
        if feature is None:
            raise BackendUnavailable(f"SolidWorks failed to create extrusion: {operation.id}")
        feature_name = self._register_feature(operation.id, feature)
        self.active_sketch_id = None
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "depth": float(operation.parameters["depth"]),
            "feature_id": operation.id,
            "feature_name": feature_name,
        }

    def _cut_extrude(self, operation: PrimitiveOperation) -> dict[str, object]:
        self._require_active_sketch(str(operation.parameters["sketch"]))
        depth = self._mm_to_m(operation.parameters["depth"])
        reverse_direction = bool(operation.parameters.get("reverse_direction", True))
        flip_side_to_cut = bool(operation.parameters.get("flip_side_to_cut", False))
        self.sketch_manager.InsertSketch(True)
        feature = self.feature_manager.FeatureCut3(
            True,
            flip_side_to_cut,
            reverse_direction,
            0,
            0,
            depth,
            0,
            False,
            False,
            False,
            False,
            0,
            0,
            False,
            False,
            False,
            False,
            False,
            True,
            True,
            True,
            True,
            False,
            0,
            0,
            False,
        )
        if feature is None:
            raise BackendUnavailable(f"SolidWorks failed to create cut extrusion: {operation.id}")
        feature_name = self._register_feature(operation.id, feature)
        self.active_sketch_id = None
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "depth": float(operation.parameters["depth"]),
            "reverse_direction": reverse_direction,
            "flip_side_to_cut": flip_side_to_cut,
            "feature_id": operation.id,
            "feature_name": feature_name,
        }

    def _revolve(self, operation: PrimitiveOperation, *, is_cut: bool) -> dict[str, object]:
        sketch_id = str(operation.parameters["sketch"])
        self._require_active_sketch(sketch_id)
        axis = self._resolve_entity(operation.parameters["axis"])
        angle = float(operation.parameters.get("angle", 360))
        reverse_direction = bool(operation.parameters.get("reverse_direction", False))
        if angle <= 0 or angle > 360:
            raise BackendUnavailable(f"Revolve angle must be greater than 0 and at most 360: {operation.id}")

        self.sketch_manager.InsertSketch(True)
        feature = None
        for mark in [4, 16, 0]:
            self.model.ClearSelection2(True)
            if not self._select_entity(axis, append=False, mark=mark):
                continue
            if not self._select_sketch(sketch_id, append=True):
                continue
            feature = self.feature_manager.FeatureRevolve2(
                True,
                True,
                False,
                is_cut,
                reverse_direction,
                False,
                0,
                0,
                math.radians(angle),
                0,
                False,
                False,
                0,
                0,
                0,
                0,
                0,
                True,
                True,
                True,
            )
            if feature is not None:
                break

        self.model.ClearSelection2(True)
        if feature is None:
            feature_type = "cut revolve" if is_cut else "revolve"
            raise BackendUnavailable(f"SolidWorks failed to create {feature_type}: {operation.id}")

        feature_name = self._register_feature(operation.id, feature)
        self.active_sketch_id = None
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "angle": angle,
            "reverse_direction": reverse_direction,
            "is_cut": is_cut,
            "feature_id": operation.id,
            "feature_name": feature_name,
        }

    def _sweep(self, operation: PrimitiveOperation, *, is_cut: bool) -> dict[str, object]:
        profile_id = self._sketch_ref_to_id(operation.parameters["profile"], "profile")
        path_id = self._sketch_ref_to_id(operation.parameters["path"], "path")
        guide_ids = [
            self._sketch_ref_to_id(item, f"guide_curves[{index}]")
            for index, item in enumerate(operation.parameters.get("guide_curves", []) or [])
        ]
        if profile_id == path_id:
            raise BackendUnavailable(f"Sweep profile and path must be different sketches: {operation.id}")

        if self.active_sketch_id is not None:
            if self.active_sketch_id not in {profile_id, path_id, *guide_ids}:
                raise BackendUnavailable(
                    f"Sweep cannot close unrelated active sketch {self.active_sketch_id}: {operation.id}"
                )
            self.sketch_manager.InsertSketch(True)
            self.active_sketch_id = None

        merge = bool(operation.parameters.get("merge", True))
        path_align = self._enum_value(operation.parameters.get("path_align", 0), SWEEP_PATH_ALIGNS)
        twist_control = self._enum_value(operation.parameters.get("twist_control", 0), SWEEP_TWIST_CONTROLS)
        twist_angle = math.radians(float(operation.parameters.get("twist_angle", 0)))
        direction = int(operation.parameters.get("direction", 0))
        alignment = bool(operation.parameters.get("alignment", twist_control not in {8, 9}))
        keep_tangency = bool(operation.parameters.get("keep_tangency", False))
        advanced_smoothing = bool(operation.parameters.get("advanced_smoothing", False))
        start_matching_type = int(operation.parameters.get("start_matching_type", 0))
        end_matching_type = int(operation.parameters.get("end_matching_type", 0))
        circular_profile = bool(operation.parameters.get("circular_profile", False))
        circular_profile_diameter = self._mm_to_m(operation.parameters.get("circular_profile_diameter", 0))
        feature = None

        selection_attempts = [
            (profile_id, 1, path_id, 4, "profile_path_guides"),
            (profile_id, 1, path_id, 4, "profile_guides_path"),
            (profile_id, 0, path_id, 0, "profile_path_guides"),
            (path_id, 4, profile_id, 1, "profile_path_guides"),
        ]
        for first_id, first_mark, second_id, second_mark, guide_order in selection_attempts:
            self.model.ClearSelection2(True)
            if not self._select_sketch(first_id, append=False, mark=first_mark):
                continue
            if guide_order == "profile_guides_path":
                guide_selection_failed = False
                for guide_id in guide_ids:
                    if not self._select_guide_curve(guide_id, append=True):
                        guide_selection_failed = True
                        break
                if guide_selection_failed:
                    continue
                if not self._select_sketch(second_id, append=True, mark=second_mark):
                    continue
            else:
                if not self._select_sketch(second_id, append=True, mark=second_mark):
                    continue
                guide_selection_failed = False
                for guide_id in guide_ids:
                    if not self._select_guide_curve(guide_id, append=True):
                        guide_selection_failed = True
                        break
                if guide_selection_failed:
                    continue
            try:
                if is_cut:
                    feature = self.feature_manager.InsertCutSwept5(
                        False,
                        alignment,
                        twist_control,
                        keep_tangency,
                        advanced_smoothing,
                        start_matching_type,
                        end_matching_type,
                        False,
                        0,
                        0,
                        0,
                        path_align,
                        False,
                        True,
                        twist_angle,
                        True,
                        False,
                        True,
                        False,
                        circular_profile,
                        circular_profile_diameter,
                        direction,
                    )
                else:
                    feature = self.feature_manager.InsertProtrusionSwept4(
                        False,
                        alignment,
                        twist_control,
                        keep_tangency,
                        advanced_smoothing,
                        start_matching_type,
                        end_matching_type,
                        False,
                        0,
                        0,
                        0,
                        path_align,
                        merge,
                        False,
                        True,
                        twist_angle,
                        True,
                        circular_profile,
                        circular_profile_diameter,
                        direction,
                    )
            except Exception:
                feature = None
            if feature is not None:
                break

        self.model.ClearSelection2(True)
        if feature is None:
            feature_type = "cut sweep" if is_cut else "sweep"
            raise BackendUnavailable(f"SolidWorks failed to create {feature_type}: {operation.id}")

        feature_name = self._register_feature(operation.id, feature)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "profile": profile_id,
            "path": path_id,
            "guide_curves": guide_ids,
            "merge": merge,
            "path_align": path_align,
            "twist_control": twist_control,
            "twist_angle": float(operation.parameters.get("twist_angle", 0)),
            "direction": direction,
            "is_cut": is_cut,
            "feature_id": operation.id,
            "feature_name": feature_name,
        }

    def _loft(self, operation: PrimitiveOperation, *, is_cut: bool) -> dict[str, object]:
        profile_ids = [
            self._sketch_ref_to_id(item, f"profiles[{index}]")
            for index, item in enumerate(operation.parameters["profiles"])
        ]
        guide_ids = [
            self._sketch_ref_to_id(item, f"guide_curves[{index}]")
            for index, item in enumerate(operation.parameters.get("guide_curves", []) or [])
        ]
        centerline_id = None
        if operation.parameters.get("centerline") is not None:
            centerline_id = self._sketch_ref_to_id(operation.parameters["centerline"], "centerline")
        if len(set(profile_ids)) != len(profile_ids):
            raise BackendUnavailable(f"Loft profiles must be unique sketches: {operation.id}")

        selected_sketch_ids = set(profile_ids) | set(guide_ids)
        if centerline_id is not None:
            selected_sketch_ids.add(centerline_id)
        if self.active_sketch_id is not None:
            if self.active_sketch_id not in selected_sketch_ids:
                raise BackendUnavailable(f"Loft cannot close unrelated active sketch {self.active_sketch_id}: {operation.id}")
            self.sketch_manager.InsertSketch(True)
            self.active_sketch_id = None

        closed = bool(operation.parameters.get("closed", False))
        keep_tangency = bool(operation.parameters.get("keep_tangency", True))
        force_non_rational = bool(operation.parameters.get("force_non_rational", False))
        tess_tolerance_factor = float(operation.parameters.get("tess_tolerance_factor", 1))
        start_matching_type = int(operation.parameters.get("start_matching_type", 0))
        end_matching_type = int(operation.parameters.get("end_matching_type", 0))
        start_tangent_length = float(operation.parameters.get("start_tangent_length", 1))
        end_tangent_length = float(operation.parameters.get("end_tangent_length", 1))
        start_tangent_direction = bool(operation.parameters.get("start_tangent_direction", False))
        end_tangent_direction = bool(operation.parameters.get("end_tangent_direction", False))
        is_thin_body = bool(operation.parameters.get("is_thin_body", False))
        thickness1 = self._mm_to_m(operation.parameters.get("thickness1", 0))
        thickness2 = self._mm_to_m(operation.parameters.get("thickness2", 0))
        thin_type = int(operation.parameters.get("thin_type", 0))
        merge = bool(operation.parameters.get("merge", True))
        use_feature_scope = bool(operation.parameters.get("use_feature_scope", False))
        use_auto_select = bool(operation.parameters.get("use_auto_select", True))
        guide_curve_influence = self._enum_value(
            operation.parameters.get("guide_curve_influence", 0),
            LOFT_GUIDE_CURVE_INFLUENCES,
        )

        feature = None
        for profile_mark in [1, 0]:
            self.model.ClearSelection2(True)
            if not self._select_loft_profiles(profile_ids, mark=profile_mark):
                continue
            guide_selection_failed = False
            for guide_id in guide_ids:
                if not self._select_guide_curve(guide_id, append=True):
                    guide_selection_failed = True
                    break
            if guide_selection_failed:
                continue
            if centerline_id is not None and not self._select_centerline_curve(centerline_id, append=True):
                continue
            try:
                if is_cut:
                    feature = self.feature_manager.InsertCutBlend(
                        closed,
                        keep_tangency,
                        force_non_rational,
                        tess_tolerance_factor,
                        start_matching_type,
                        end_matching_type,
                        is_thin_body,
                        thickness1,
                        thickness2,
                        thin_type,
                        use_feature_scope,
                        use_auto_select,
                    )
                else:
                    feature = self.feature_manager.InsertProtrusionBlend2(
                        closed,
                        keep_tangency,
                        force_non_rational,
                        tess_tolerance_factor,
                        start_matching_type,
                        end_matching_type,
                        start_tangent_length,
                        end_tangent_length,
                        start_tangent_direction,
                        end_tangent_direction,
                        is_thin_body,
                        thickness1,
                        thickness2,
                        thin_type,
                        merge,
                        use_feature_scope,
                        use_auto_select,
                        guide_curve_influence,
                    )
            except Exception:
                feature = None
            if feature is not None:
                break

        self.model.ClearSelection2(True)
        if feature is None:
            feature_type = "cut loft" if is_cut else "loft"
            raise BackendUnavailable(f"SolidWorks failed to create {feature_type}: {operation.id}")

        feature_name = self._register_feature(operation.id, feature)
        return {
            "operation_id": operation.id,
            "operation_type": operation.type,
            "profiles": profile_ids,
            "guide_curves": guide_ids,
            "centerline": centerline_id,
            "closed": closed,
            "merge": merge if not is_cut else None,
            "guide_curve_influence": guide_curve_influence,
            "is_cut": is_cut,
            "feature_id": operation.id,
            "feature_name": feature_name,
        }

    def _resolve_entity(self, ref: dict[str, Any]):
        ref_type = str(ref["type"])
        if ref_type in {"point", "circle", "line", "centerline", "axis", "arc"}:
            return self.geometry[str(ref["id"])]
        if ref_type == "spline":
            return self.geometry[str(ref["id"])]
        if ref_type == "spline_point":
            spline_id = str(ref["spline"])
            point_name = str(ref.get("point", "")).lower()
            entity_id = f"{spline_id}_point_{int(ref.get('index', 0))}"
            if point_name == "start":
                entity_id = f"{spline_id}_start"
            elif point_name == "end":
                entity_id = f"{spline_id}_end"
            try:
                return self.geometry[entity_id]
            except KeyError as exc:
                raise BackendUnavailable(f"Unknown spline point reference: {entity_id}") from exc
        if ref_type == "circle_center":
            circle = self.geometry[str(ref["circle"])]
            return _maybe_call(circle.GetCenterPoint2)
        if ref_type in {"line_point", "centerline_point", "axis_point"}:
            line = self.geometry[str(ref["id"])]
            point_name = str(ref.get("point", "start")).lower()
            if point_name == "start":
                return _maybe_call(line.GetStartPoint2)
            if point_name == "end":
                return _maybe_call(line.GetEndPoint2)
            raise BackendUnavailable(f"Unsupported line point selector: {point_name}")
        if ref_type == "profile_segment":
            segments = self._resolve_profile_segments(str(ref["profile"]))
            return segments[int(ref["index"])]
        if ref_type == "profile_point":
            segments = self._resolve_profile_segments(str(ref["profile"]))
            segment = segments[int(ref["index"])]
            point_name = str(ref.get("point", "start")).lower()
            if point_name == "start":
                return _maybe_call(segment.GetStartPoint2)
            if point_name == "end":
                return _maybe_call(segment.GetEndPoint2)
            raise BackendUnavailable(f"Unsupported profile point selector: {point_name}")
        if ref_type == "arc_point":
            arc = self.geometry[str(ref["id"])]
            point_name = str(ref.get("point", "start")).lower()
            if point_name == "start":
                return _maybe_call(arc.GetStartPoint2)
            if point_name == "end":
                return _maybe_call(arc.GetEndPoint2)
            if point_name == "center":
                return _maybe_call(arc.GetCenterPoint2)
            raise BackendUnavailable(f"Unsupported arc point selector: {point_name}")
        if ref_type == "arc_center":
            arc = self.geometry[str(ref["id"])]
            return _maybe_call(arc.GetCenterPoint2)
        if ref_type == "profile_edge":
            edges = self._classify_profile_edges(str(ref["profile"]))
            return edges[str(ref["edge"])]
        raise BackendUnavailable(f"Unsupported primitive entity reference: {ref_type}")

    def _resolve_entity_collection(self, ref: dict[str, Any]) -> list[Any]:
        ref_type = str(ref["type"])
        if ref_type in {"profile", "operation", "group", "converted_entities", "offset_entities"}:
            entity = self.geometry[str(ref["id"])]
            if isinstance(entity, list):
                return entity
            return [entity]
        if ref_type == "entities":
            return [
                entity
                for item in ref["entities"]
                for entity in self._resolve_entity_collection(item)
            ]
        return [self._resolve_entity(ref)]

    @staticmethod
    def _sketch_ref_to_id(ref: object, field_name: str) -> str:
        if isinstance(ref, dict):
            sketch_id = str(ref.get("sketch", "")).strip()
        else:
            sketch_id = str(ref).strip()
        if not sketch_id:
            raise BackendUnavailable(f"Sweep {field_name} must reference a sketch.")
        return sketch_id

    def _resolve_profile_segments(self, profile_id: str) -> list[Any]:
        profile = self.geometry.get(profile_id)
        if not isinstance(profile, list) or not profile:
            raise BackendUnavailable(f"Unknown primitive profile: {profile_id}")
        return profile

    def _classify_profile_edges(self, profile_id: str) -> dict[str, Any]:
        horizontal: list[tuple[float, Any]] = []
        vertical: list[tuple[float, Any]] = []
        for segment in self._resolve_profile_segments(profile_id):
            start_x, start_y = _point_tuple(_maybe_call(segment.GetStartPoint2))
            end_x, end_y = _point_tuple(_maybe_call(segment.GetEndPoint2))
            if abs(start_y - end_y) <= 1e-9:
                horizontal.append(((start_y + end_y) / 2, segment))
            elif abs(start_x - end_x) <= 1e-9:
                vertical.append(((start_x + end_x) / 2, segment))
        if len(horizontal) < 2 or len(vertical) < 2:
            raise BackendUnavailable(f"Primitive profile is not rectangular enough for edge references: {profile_id}")
        horizontal.sort(key=lambda item: item[0])
        vertical.sort(key=lambda item: item[0])
        return {
            "bottom": horizontal[0][1],
            "top": horizontal[-1][1],
            "left": vertical[0][1],
            "right": vertical[-1][1],
        }

    def _select_base_plane(self) -> str:
        return self._select_original_plane("front") or self._select_first_ref_plane()

    def _select_first_ref_plane(self) -> str:
        feature = _maybe_call(self.model.FirstFeature)
        while feature:
            name = str(_maybe_call(feature.Name))
            feature_type = str(_maybe_call(feature.GetTypeName2))
            if feature_type == "RefPlane" and feature.Select2(False, 0):
                return name
            feature = _maybe_call(feature.GetNextFeature)
        raise BackendUnavailable("Could not select a base plane in the SolidWorks part template.")

    def _select_sketch_plane(self, plane_ref: str) -> str:
        if plane_ref.lower() in {"base", "default"}:
            return self._select_base_plane()

        original_plane = self._select_original_plane(plane_ref)
        if original_plane is not None:
            return original_plane

        reference_plane = self.reference_planes.get(plane_ref)
        if reference_plane is None:
            raise BackendUnavailable(f"Unknown sketch plane: {plane_ref}")
        if not self._select_entity(reference_plane):
            raise BackendUnavailable(f"SolidWorks failed to select sketch plane: {plane_ref}")
        try:
            return str(_maybe_call(reference_plane.Name))
        except Exception:
            return plane_ref

    def _select_original_plane(self, plane_ref: str) -> str | None:
        normalized_ref = plane_ref.strip().lower().replace(" ", "_")
        wanted = {plane_ref.strip(), normalized_ref}
        for aliases in ORIGINAL_PLANE_ALIASES.values():
            if normalized_ref in aliases or plane_ref.strip() in aliases:
                wanted = aliases
                break

        feature = _maybe_call(self.model.FirstFeature)
        while feature:
            name = str(_maybe_call(feature.Name))
            feature_type = str(_maybe_call(feature.GetTypeName2))
            normalized_name = name.strip().lower().replace(" ", "_")
            if feature_type == "RefPlane" and (name in wanted or normalized_name in wanted):
                if feature.Select2(False, 0):
                    return name
            feature = _maybe_call(feature.GetNextFeature)

        try:
            extension = self.model.Extension
            for candidate in wanted:
                if extension.SelectByID2(candidate, "PLANE", 0, 0, 0, False, 0, None, 0):
                    return candidate
        except Exception:
            pass
        return None

    def _select_sketch(self, sketch_id: str, append: bool = False, mark: int = 0) -> bool:
        sketch_info = self.sketches.get(sketch_id, {})
        sketch_object = sketch_info.get("sketch_object")
        if sketch_object is not None and self._select_entity(sketch_object, append=append, mark=mark):
            return True
        try:
            extension = self.model.Extension
            return bool(extension.SelectByID2(sketch_id, "SKETCH", 0, 0, 0, append, mark, None, 0))
        except Exception:
            return False

    def _select_guide_curve(self, sketch_id: str, append: bool = True) -> bool:
        return self._select_sketch_curve(sketch_id, append=append, mark=2)

    def _select_centerline_curve(self, sketch_id: str, append: bool = True) -> bool:
        return self._select_sketch_curve(sketch_id, append=append, mark=4)

    def _select_sketch_curve(self, sketch_id: str, append: bool = True, mark: int = 0) -> bool:
        curves = self.sketch_geometry.get(sketch_id, [])
        selected_any = False
        for curve in curves:
            if self._select_entity(curve, append=append or selected_any, mark=mark):
                selected_any = True
            elif not selected_any:
                return False
        if selected_any:
            return True
        return self._select_sketch(sketch_id, append=append, mark=mark)

    def _select_loft_profiles(self, profile_ids: list[str], mark: int) -> bool:
        for index, profile_id in enumerate(profile_ids):
            if not self._select_sketch(profile_id, append=index > 0, mark=mark):
                return False
        return True

    def _register_sketch_geometry(self, sketch_id: str, entities: list[Any]) -> None:
        self.sketch_geometry.setdefault(sketch_id, []).extend(entities)

    def _select_offset_plane_base(self, target: object, operation_id: str) -> dict[str, object]:
        if isinstance(target, str):
            plane_name = self._select_sketch_plane(target)
            return {
                "selection_mode": "plane",
                "plane_ref": target,
                "plane": plane_name,
            }

        if not isinstance(target, dict):
            raise BackendUnavailable(f"Offset plane base must be a plane reference or face target: {operation_id}")

        target_type = str(target.get("type", "body_face")).lower()
        if target_type in {"plane", "reference_plane", "datum_plane"}:
            plane_ref = str(
                target.get("name")
                or target.get("plane")
                or target.get("ref")
                or target.get("id")
                or ""
            ).strip()
            if not plane_ref:
                raise BackendUnavailable(f"Offset plane target is missing a plane reference: {operation_id}")
            plane_name = self._select_sketch_plane(plane_ref)
            return {
                "selection_mode": target_type,
                "plane_ref": plane_ref,
                "plane": plane_name,
            }

        face, face_report = self._find_planar_face(target)
        if not self._select_entity(face):
            raise BackendUnavailable(f"SolidWorks failed to select base face for offset plane: {operation_id}")
        return face_report

    def _find_conversion_face(self, target: dict[str, Any]) -> tuple[Any, dict[str, object]]:
        target_type = str(target.get("type", "body_face")).lower()
        if target_type in {"body_face_edges", "face_edges"}:
            face_target = dict(target)
            face_target["type"] = "body_face"
            face, report = self._find_planar_face(face_target)
            report["selection_mode"] = target_type
            return face, report
        if target_type == "named_face_edges":
            face_target = {
                "type": "named_face",
                "name": target["name"],
            }
            face, report = self._find_planar_face(face_target)
            report["selection_mode"] = target_type
            return face, report
        return self._find_planar_face(target)

    def _face_edges_by_loop(self, face, loop_mode: str) -> list[Any]:
        loops = self._face_loops(face)
        selected_edges: list[Any] = []
        for loop in loops:
            is_outer = bool(_maybe_call(loop.IsOuter))
            if loop_mode == "outer" and not is_outer:
                continue
            if loop_mode == "inner" and is_outer:
                continue
            edges = self._loop_edges(loop)
            selected_edges.extend(edges)
        if not selected_edges:
            raise BackendUnavailable(f"No face edges matched loop selector: {loop_mode}")
        return selected_edges

    @staticmethod
    def _face_loops(face) -> list[Any]:
        try:
            loops = _maybe_call(face.GetLoops)
        except Exception:
            loops = None
        if loops is not None:
            return list(loops) if isinstance(loops, tuple | list) else [loops]

        result: list[Any] = []
        try:
            loop = _maybe_call(face.GetFirstLoop)
        except Exception:
            loop = None
        while loop is not None:
            result.append(loop)
            try:
                loop = _maybe_call(loop.GetNext)
            except Exception:
                break
        return result

    @staticmethod
    def _loop_edges(loop) -> list[Any]:
        try:
            edges = _maybe_call(loop.GetEdges)
        except Exception:
            edges = None
        if edges is None:
            return []
        return list(edges) if isinstance(edges, tuple | list) else [edges]

    def _project_face_edges_as_sketch_segments(self, sketch_id: str, edges: list[Any], operation_id: str) -> list[Any]:
        segments = []
        endpoint_refs: list[tuple[Any, tuple[float, float]]] = []
        for index, edge in enumerate(edges):
            try:
                start_point, end_point = self._edge_endpoints(edge)
            except Exception as exc:
                raise BackendUnavailable(f"SolidWorks failed to read edge endpoints: {operation_id}[{index}]") from exc
            start_x = float(start_point[0])
            start_y = float(start_point[1])
            end_x = float(end_point[0])
            end_y = float(end_point[1])
            segment = self.sketch_manager.CreateLine(start_x, start_y, 0, end_x, end_y, 0)
            if segment is None:
                raise BackendUnavailable(
                    f"SolidWorks failed to project face edge into sketch: {operation_id}[{index}] "
                    f"({start_point} -> {end_point})"
                )
            segments.append(segment)
            endpoint_refs.append((_maybe_call(segment.GetStartPoint2), (start_x, start_y)))
            endpoint_refs.append((_maybe_call(segment.GetEndPoint2), (end_x, end_y)))

        coincident_relations = 0
        for index, (first_point, first_xy) in enumerate(endpoint_refs):
            for second_point, second_xy in endpoint_refs[index + 1:]:
                if abs(first_xy[0] - second_xy[0]) <= 1e-8 and abs(first_xy[1] - second_xy[1]) <= 1e-8:
                    if self._add_relation_to_entities([first_point, second_point], "sgCOINCIDENT"):
                        coincident_relations += 1
        self.relations_added += coincident_relations
        return segments

    @staticmethod
    def _edge_endpoints(edge) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        start_vertex = _maybe_call(edge.GetStartVertex)
        end_vertex = _maybe_call(edge.GetEndVertex)
        if start_vertex is None or end_vertex is None:
            raise BackendUnavailable("Edge has no start or end vertex.")
        start_point = _maybe_call(start_vertex.GetPoint)
        end_point = _maybe_call(end_vertex.GetPoint)
        if start_point is None or end_point is None or len(start_point) < 3 or len(end_point) < 3:
            raise BackendUnavailable("Edge vertex has no 3D point.")
        return (
            (float(start_point[0]), float(start_point[1]), float(start_point[2])),
            (float(end_point[0]), float(end_point[1]), float(end_point[2])),
        )

    def _find_planar_face(self, target: dict[str, Any]) -> tuple[Any, dict[str, object]]:
        target_type = str(target.get("type", "body_face"))
        if target_type == "named_face":
            name = str(target["name"])
            named_face = self.named_faces.get(name)
            if named_face is None:
                raise BackendUnavailable(f"Unknown named face: {name}")
            report = dict(named_face["report"])
            report["selection_mode"] = "named_face"
            report["name"] = name
            return named_face["face"], report

        if target_type != "body_face":
            raise BackendUnavailable(f"Unsupported face target type: {target_type}")

        normal = self._normalize_vector(target["normal"])
        position = str(target.get("position", "max")).lower()
        min_dot = float(target.get("min_dot", 0.95))
        area_mode = str(target.get("area", "largest")).lower()
        if area_mode not in {"largest", "smallest"}:
            raise BackendUnavailable(f"Unsupported face area selector: {area_mode}")
        try:
            area_rank = int(target.get("area_rank", 0))
        except (TypeError, ValueError) as exc:
            raise BackendUnavailable("Face target area_rank must be a non-negative integer.") from exc
        if area_rank < 0:
            raise BackendUnavailable("Face target area_rank must be a non-negative integer.")
        position_tolerance = float(target.get("position_tolerance", 0.01))
        if self.active_sketch_id is None:
            try:
                self.model.EditRebuild3()
            except Exception:
                pass

        candidates: list[tuple[float, float, Any, dict[str, object]]] = []
        source_faces, source_feature = self._target_candidate_faces(target)
        for face in source_faces:
            face_report = self._planar_face_report(face, normal)
            if face_report is None:
                continue
            alignment = abs(float(face_report["alignment"]))
            if alignment < min_dot:
                continue
            center = face_report["center"]
            score = sum(float(center[index]) * normal[index] for index in range(3))
            area = float(face_report.get("area", 0.0))
            candidates.append((score, area, face, face_report))

        if not candidates:
            scope = f" on feature {source_feature}" if source_feature else ""
            raise BackendUnavailable(f"No planar body face{scope} matched target normal: {target.get('normal')}")

        if position == "max":
            extreme_score = max(item[0] for item in candidates)
            positional_candidates = [item for item in candidates if abs(item[0] - extreme_score) <= position_tolerance]
        elif position == "min":
            extreme_score = min(item[0] for item in candidates)
            positional_candidates = [item for item in candidates if abs(item[0] - extreme_score) <= position_tolerance]
        else:
            raise BackendUnavailable(f"Unsupported face position selector: {position}")

        if not positional_candidates:
            positional_candidates = candidates

        positional_candidates.sort(key=lambda item: item[1], reverse=area_mode == "largest")
        if area_rank >= len(positional_candidates):
            raise BackendUnavailable(
                f"Face target area_rank {area_rank} is out of range; "
                f"{len(positional_candidates)} positional candidates matched."
            )

        score, _, face, report = positional_candidates[area_rank]
        report["selection_mode"] = "body_face"
        report["source_feature"] = source_feature
        report["position"] = position
        report["position_score"] = round(score, 6)
        report["position_tolerance"] = round(position_tolerance, 6)
        report["area_selector"] = area_mode
        report["area_rank"] = area_rank
        report["candidate_count"] = len(candidates)
        report["positional_candidate_count"] = len(positional_candidates)
        return face, report

    def _register_feature(self, feature_id: str, feature, feature_name: str | None = None) -> str:
        name = feature_name or feature_id
        try:
            feature.Name = name
        except Exception:
            pass
        self.features[feature_id] = feature
        if feature_name:
            self.features[feature_name] = feature
        try:
            return str(_maybe_call(feature.Name))
        except Exception:
            return name

    def _target_candidate_faces(self, target: dict[str, Any]) -> tuple[list[Any], str | None]:
        feature_ref = target.get("feature") or target.get("feature_id")
        if feature_ref:
            feature_id = str(feature_ref)
            feature = self.features.get(feature_id)
            if feature is None:
                raise BackendUnavailable(f"Unknown feature id for face selection: {feature_id}")
            faces = self._feature_faces(feature)
            if not faces:
                raise BackendUnavailable(f"SolidWorks did not expose generated faces for feature: {feature_id}")
            return faces, feature_id

        faces: list[Any] = []
        for body in self._solid_bodies():
            faces.extend(self._body_faces(body))
        return faces, None

    @staticmethod
    def _feature_faces(feature) -> list[Any]:
        try:
            faces = _maybe_call(feature.GetFaces)
        except Exception:
            return []
        if faces is None:
            return []
        if isinstance(faces, tuple | list):
            return list(faces)
        return [faces]

    def _solid_bodies(self) -> list[Any]:
        try:
            bodies = self.model.GetBodies2(0, True)
        except Exception as exc:
            raise BackendUnavailable("SolidWorks failed to enumerate solid bodies.") from exc
        if bodies is None:
            return []
        if isinstance(bodies, tuple | list):
            return list(bodies)
        return [bodies]

    @staticmethod
    def _body_faces(body) -> list[Any]:
        try:
            faces = body.GetFaces()
        except Exception:
            return []
        if faces is None:
            return []
        if isinstance(faces, tuple | list):
            return list(faces)
        return [faces]

    @staticmethod
    def _spline_points(spline) -> list[Any]:
        candidates = [spline]
        for method_name in ["GetSpecificFeature2", "GetSpecificFeature"]:
            try:
                specific = getattr(spline, method_name)()
            except Exception:
                specific = None
            if specific is not None:
                candidates.append(specific)

        for candidate in candidates:
            for method_name in ["GetPoints2", "GetPoints"]:
                try:
                    points = getattr(candidate, method_name)()
                except Exception:
                    points = None
                if points is None:
                    continue
                if isinstance(points, tuple | list):
                    return list(points)
                return [points]

        points = []
        for method_name in ["GetStartPoint2", "GetEndPoint2"]:
            try:
                point = getattr(spline, method_name)()
            except Exception:
                point = None
            if point is not None:
                points.append(point)
        return points

    def _planar_face_report(self, face, target_normal: tuple[float, float, float]) -> dict[str, object] | None:
        normal_from_face = False
        try:
            normal = self._normalize_vector(_maybe_call(face.Normal))
            normal_from_face = True
        except Exception:
            normal_from_face = False

        if not normal_from_face:
            try:
                surface = _maybe_call(face.GetSurface)
            except Exception:
                return None
            try:
                if not bool(_maybe_call(surface.IsPlane)):
                    return None
            except Exception:
                return None
            try:
                plane_params = list(_maybe_call(surface.PlaneParams))
            except Exception:
                return None
            if len(plane_params) < 6:
                return None
            normal = self._normalize_vector(plane_params[3:6])
            try:
                if not bool(_maybe_call(face.FaceInSurfaceSense)):
                    normal = (-normal[0], -normal[1], -normal[2])
            except Exception:
                pass

        box = self._face_box(face)
        extent = sum(abs((box[index + 3] - box[index]) * target_normal[index]) for index in range(3))
        if extent > 1e-6:
            return None

        try:
            area = float(_maybe_call(face.GetArea))
        except Exception:
            area = 0.0
        center = (
            (box[0] + box[3]) / 2,
            (box[1] + box[4]) / 2,
            (box[2] + box[5]) / 2,
        )
        alignment = sum(normal[index] * target_normal[index] for index in range(3))
        return {
            "center": [round(value * 1000, 6) for value in center],
            "normal": [round(value, 6) for value in normal],
            "alignment": round(alignment, 6),
            "area": area,
            "box": [round(value * 1000, 6) for value in box],
        }

    @staticmethod
    def _face_box(face) -> tuple[float, float, float, float, float, float]:
        try:
            box = list(_maybe_call(face.GetBox))
        except Exception:
            box = []
        if len(box) >= 6:
            return tuple(float(value) for value in box[:6])
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    @staticmethod
    def _normalize_vector(values) -> tuple[float, float, float]:
        vector = tuple(float(values[index]) for index in range(3))
        length = math.sqrt(sum(value * value for value in vector))
        if length <= 1e-12:
            raise BackendUnavailable("Face target normal cannot be a zero vector.")
        return tuple(value / length for value in vector)

    def _require_active_sketch(self, sketch_id: str) -> None:
        if self.active_sketch_id != sketch_id:
            raise BackendUnavailable(f"Primitive operation requires active sketch: {sketch_id}")

    @staticmethod
    def _try_rename_entity(entity, name: str) -> None:
        try:
            entity.Name = name
        except Exception:
            pass

    @staticmethod
    def _mm_to_m(value: float) -> float:
        return float(value) / 1000.0

    @staticmethod
    def _arc_direction(value: object) -> int:
        normalized = str(value).strip().lower()
        if normalized in {"clockwise", "cw", "-1"}:
            return -1
        return 1

    @staticmethod
    def _enum_value(value: object, aliases: dict[str, int]) -> int:
        if isinstance(value, int):
            return value
        text = str(value).strip().lower()
        if text in aliases:
            return aliases[text]
        return int(value)

    def _position(self, position: list[float]) -> tuple[float, float, float]:
        return (self._mm_to_m(position[0]), self._mm_to_m(position[1]), 0.0)

    def _trim_selection(self, operation: PrimitiveOperation) -> tuple[list[Any], list[tuple[float, float, float] | None], int, int]:
        parameters = operation.parameters
        if "boundary_entities" in parameters or "trim_targets" in parameters:
            boundary_refs = list(parameters.get("boundary_entities", []))
            target_refs = list(parameters.get("trim_targets", []))
            entity_refs = boundary_refs + target_refs
            boundary_points = self._optional_trim_points(parameters.get("boundary_pick_points"), len(boundary_refs))
            target_points = self._optional_trim_points(parameters.get("trim_pick_points"), len(target_refs))
            entities = [self._resolve_entity(item) for item in entity_refs]
            return entities, boundary_points + target_points, len(boundary_refs), len(target_refs)

        entity_refs = list(parameters["entities"])
        raw_pick_points = self._trim_pick_points(operation)
        selection_points: list[tuple[float, float, float] | None] = [
            raw_pick_points[index] if index < len(raw_pick_points) else None
            for index, _ in enumerate(entity_refs)
        ]
        entities = [self._resolve_entity(item) for item in entity_refs]
        return entities, selection_points, 0, len(entity_refs)

    def _optional_trim_points(self, points: object, expected: int) -> list[tuple[float, float, float] | None]:
        if points is None:
            return [None] * expected
        raw_points = list(points)
        return [self._trim_point_to_m(point) for point in raw_points]

    def _trim_pick_points(self, operation: PrimitiveOperation) -> list[tuple[float, float, float]]:
        if "pick_points" in operation.parameters:
            raw_points = operation.parameters["pick_points"]
            return [self._trim_point_to_m(point) for point in raw_points]
        if "pick_point" in operation.parameters:
            return [self._trim_point_to_m(operation.parameters["pick_point"])]
        return []

    def _trim_point(
        self,
        operation: PrimitiveOperation,
        pick_points: list[tuple[float, float, float] | None],
    ) -> tuple[float, float, float]:
        for key in ("trim_point", "point", "pick_point"):
            if key in operation.parameters:
                return self._trim_point_to_m(operation.parameters[key])
        for point in pick_points:
            if point is not None:
                return point
        raise BackendUnavailable(f"Sketch trim operation requires trim_point or pick_point: {operation.id}")

    def _trim_selection_point(
        self,
        pick_points: list[tuple[float, float, float] | None],
        index: int,
        entity,
    ) -> tuple[float, float, float]:
        if index < len(pick_points) and pick_points[index] is not None:
            return pick_points[index]
        return self._entity_midpoint_m(entity)

    def _trim_point_to_m(self, point: object) -> tuple[float, float, float]:
        if isinstance(point, dict):
            raw_point = point.get("point", point.get("position"))
        else:
            raw_point = point
        if not isinstance(raw_point, list | tuple) or len(raw_point) not in {2, 3}:
            raise BackendUnavailable("Sketch trim pick point must be a two- or three-number list.")
        x = self._mm_to_m(raw_point[0])
        y = self._mm_to_m(raw_point[1])
        z = self._mm_to_m(raw_point[2]) if len(raw_point) == 3 else self._active_sketch_pick_z_m()
        return (x, y, z)

    def _active_sketch_pick_z_m(self) -> float:
        if self.active_sketch_id is None:
            return 0.0
        face_report = self.sketches.get(self.active_sketch_id, {}).get("face")
        if isinstance(face_report, dict):
            center = face_report.get("center")
            normal = face_report.get("normal")
            if (
                isinstance(center, list | tuple)
                and len(center) >= 3
                and isinstance(normal, list | tuple)
                and len(normal) >= 3
                and abs(float(normal[2])) > 0.95
            ):
                return self._mm_to_m(center[2])
        return 0.0

    def _entity_midpoint_m(self, entity) -> tuple[float, float, float]:
        try:
            start = _maybe_call(entity.GetStartPoint2)
            end = _maybe_call(entity.GetEndPoint2)
            start_x, start_y = _point_tuple(start)
            end_x, end_y = _point_tuple(end)
            return ((start_x + end_x) / 2, (start_y + end_y) / 2, 0.0)
        except Exception as exc:
            raise BackendUnavailable("Sketch trim entity needs an explicit pick_point.") from exc

    def _select_sketch_segment_for_trim(
        self,
        entity,
        point: tuple[float, float, float],
        *,
        append: bool,
        mark: int,
    ) -> bool:
        x, y, z = point
        extension = self.model.Extension
        for name in ["", *self._entity_names(entity)]:
            try:
                if extension.SelectByID2(name, "SKETCHSEGMENT", x, y, z, append, mark, None, 0):
                    return True
            except Exception:
                continue
        return self._select_entity(entity, append=append, mark=mark)

    @staticmethod
    def _entity_names(entity) -> list[str]:
        names: list[str] = []
        for attribute in ("Name", "GetName"):
            try:
                value = getattr(entity, attribute)
            except Exception:
                continue
            try:
                name = str(_maybe_call(value)).strip()
            except Exception:
                continue
            if name and name not in names:
                names.append(name)
        return names

    def _call_sketch_trim(self, trim_option: int, point: tuple[float, float, float]) -> bool:
        x, y, z = point
        trim_errors: list[str] = []
        for owner_name, owner, args in [
            ("SketchManager.SketchTrim", self.sketch_manager, (trim_option, x, y, z)),
            ("ModelDoc2.SketchTrim", self.model, (trim_option, x, y, z)),
            ("ModelDoc2.SketchTrimLegacy", self.model, (trim_option, 0, x, y)),
        ]:
            try:
                method = getattr(owner, "SketchTrim")
            except Exception:
                continue
            try:
                result = method(*args)
                return True if result is None else bool(result)
            except Exception as exc:
                trim_errors.append(f"{owner_name}: {exc}")
        error_suffix = f" ({'; '.join(trim_errors)})" if trim_errors else ""
        raise BackendUnavailable(f"SolidWorks sketch trim API call failed{error_suffix}")

    def _active_sketch_segments(self) -> list[Any]:
        sketches = []
        for getter in [
            lambda: _maybe_call(self.sketch_manager.ActiveSketch),
            lambda: _maybe_call(self.model.GetActiveSketch2),
            lambda: _maybe_call(self.model.GetActiveSketch),
        ]:
            try:
                sketch = getter()
            except Exception:
                sketch = None
            if sketch is not None:
                sketches.append(sketch)
        if self.active_sketch_id is not None:
            sketch_object = self.sketches.get(self.active_sketch_id, {}).get("sketch_object")
            if sketch_object is not None:
                sketches.append(sketch_object)

        best_segments: list[Any] = []
        for sketch in sketches:
            try:
                segments = _maybe_call(sketch.GetSketchSegments)
            except Exception:
                continue
            if segments is None:
                continue
            segment_list = list(segments) if isinstance(segments, tuple | list) else [segments]
            if len(segment_list) > len(best_segments):
                best_segments = segment_list
        return best_segments

    def _sketch_origin_reference(self, sketch_id: str):
        reference = self.sketch_origin_refs.get(sketch_id)
        if reference is not None:
            return reference
        self._require_active_sketch(sketch_id)
        reference = self.sketch_manager.CreatePoint(0, 0, 0)
        if reference is None:
            raise BackendUnavailable(f"SolidWorks failed to create sketch origin reference: {sketch_id}")
        if self._add_relation(reference, "sgFIXED"):
            self.relations_added += 1
        else:
            raise BackendUnavailable(f"SolidWorks failed to fix sketch origin reference: {sketch_id}")
        reference_id = f"{sketch_id}_origin_reference"
        self.geometry[reference_id] = reference
        self.sketch_origin_refs[sketch_id] = reference
        self._register_sketch_geometry(sketch_id, [reference])
        return reference

    def _define_point_from_reference(self, reference, point, point_x: float, point_y: float) -> tuple[int, int]:
        dimensions_added = 0
        relations_added = 0
        if abs(point_x) <= 1e-9:
            if not self._add_relation_to_entities([reference, point], "sgVERTICAL2D"):
                raise BackendUnavailable("SolidWorks failed to add vertical point reference relation.")
            relations_added += 1
            self.relations_added += 1
        else:
            dim_x = self._mm_to_m(point_x / 2)
            dim_y = self._mm_to_m(point_y + (8 if point_y >= 0 else -8))
            if not self._dimension_horizontal(reference, point, dim_x, dim_y, 0):
                raise BackendUnavailable("SolidWorks failed to add horizontal point definition dimension.")
            dimensions_added += 1
            self.dimensions_added += 1

        if abs(point_y) <= 1e-9:
            if not self._add_relation_to_entities([reference, point], "sgHORIZONTAL2D"):
                raise BackendUnavailable("SolidWorks failed to add horizontal point reference relation.")
            relations_added += 1
            self.relations_added += 1
        else:
            dim_x = self._mm_to_m(point_x + (8 if point_x >= 0 else -8))
            dim_y = self._mm_to_m(point_y / 2)
            if not self._dimension_vertical(reference, point, dim_x, dim_y, 0):
                raise BackendUnavailable("SolidWorks failed to add vertical point definition dimension.")
            dimensions_added += 1
            self.dimensions_added += 1

        return dimensions_added, relations_added

    def _add_relation(self, entity, relation: str) -> bool:
        return self._add_relation_to_entities([entity], relation)

    def _select_entities(self, entities: list[Any], *, mark: int = 0) -> bool:
        selected_any = False
        for index, entity in enumerate(entities):
            append = index > 0
            if not self._select_model_edge_by_midpoint(entity, append=append, mark=mark) and not self._select_entity(entity, append=append, mark=mark):
                return False
            selected_any = True
        return selected_any

    def _select_model_edge_by_midpoint(self, entity, append: bool = False, mark: int = 0) -> bool:
        try:
            start_point, end_point = self._edge_endpoints(entity)
        except Exception:
            start_point = end_point = None
        try:
            if start_point is None or end_point is None:
                params = _maybe_call(entity.GetCurveParams2)
                if params is None or len(params) < 6:
                    return False
                start_point = (float(params[0]), float(params[1]), float(params[2]))
                end_point = (float(params[3]), float(params[4]), float(params[5]))
            x = (float(start_point[0]) + float(end_point[0])) / 2
            y = (float(start_point[1]) + float(end_point[1])) / 2
            z = (float(start_point[2]) + float(end_point[2])) / 2
            extension = self.model.Extension
            return bool(extension.SelectByID2("", "EDGE", x, y, z, append, mark, None, 0))
        except Exception:
            return False

    def _select_face_by_report(self, face, report: dict[str, object], append: bool = False, mark: int = 0) -> bool:
        center = report.get("center")
        if isinstance(center, list | tuple) and len(center) == 3:
            try:
                extension = self.model.Extension
                if extension.SelectByID2(
                    "",
                    "FACE",
                    self._mm_to_m(center[0]),
                    self._mm_to_m(center[1]),
                    self._mm_to_m(center[2]),
                    append,
                    mark,
                    None,
                    0,
                ):
                    return True
            except Exception:
                pass
        return self._select_entity(face, append=append, mark=mark)

    def _add_relation_to_entities(self, entities: list[Any], relation: str) -> bool:
        self.model.ClearSelection2(True)
        try:
            for index, entity in enumerate(entities):
                if not self._select_entity(entity, append=index > 0):
                    return False
            self.model.SketchAddConstraints(relation)
            return True
        except Exception:
            return False
        finally:
            self.model.ClearSelection2(True)

    def _dimension_entity(self, entity, x: float, y: float, z: float) -> bool:
        self.model.ClearSelection2(True)
        if not self._select_entity(entity):
            return False
        try:
            return bool(self.model.AddDimension2(x, y, z))
        except Exception:
            return False
        finally:
            self.model.ClearSelection2(True)

    def _dimension_horizontal(self, first, second, x: float, y: float, z: float) -> bool:
        self.model.ClearSelection2(True)
        if not self._select_entity(first):
            return False
        if not self._select_entity(second, append=True):
            return False
        try:
            return bool(self.model.AddHorizontalDimension2(x, y, z))
        except Exception:
            return False
        finally:
            self.model.ClearSelection2(True)

    def _dimension_vertical(self, first, second, x: float, y: float, z: float) -> bool:
        self.model.ClearSelection2(True)
        if not self._select_entity(first):
            return False
        if not self._select_entity(second, append=True):
            return False
        try:
            return bool(self.model.AddVerticalDimension2(x, y, z))
        except Exception:
            return False
        finally:
            self.model.ClearSelection2(True)

    @staticmethod
    def _select_entity(entity, append: bool = False, mark: int = 0) -> bool:
        for method_name, args in [
            ("Select2", (append, mark)),
            ("Select4", (append, None)),
            ("Select", (append,)),
        ]:
            try:
                method = getattr(entity, method_name)
            except Exception:
                continue
            try:
                if bool(method(*args)):
                    return True
            except Exception:
                continue
        return False
