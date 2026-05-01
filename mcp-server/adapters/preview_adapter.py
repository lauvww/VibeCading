from __future__ import annotations

import json
import math
from pathlib import Path

from adapters.base import BackendResult
from core.dsl import CadJob, PrimitivePart
from core.template_compiler import compile_to_primitive_job


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_simple_pdf(lines: list[str], path: Path) -> None:
    content_lines = ["BT", "/F1 11 Tf", "50 780 Td", "14 TL"]
    for index, line in enumerate(lines):
        encoded = "FEFF" + line.encode("utf-16-be").hex().upper()
        if index == 0:
            content_lines.append(f"<{encoded}> Tj")
        else:
            content_lines.append(f"T* <{encoded}> Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 6 0 R >>",
        (
            b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light "
            b"/Encoding /UniGB-UCS2-H /DescendantFonts [5 0 R] >>"
        ),
        (
            b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> >>"
        ),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(output))


def write_top_view_svg(job: CadJob, path: Path) -> None:
    part = job.part
    margin = max(part.length, part.width) * 0.08
    view_width = part.length + margin * 2
    view_height = part.width + margin * 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{view_width}mm" height="{view_height}mm" viewBox="0 0 {view_width} {view_height}">',
        '<rect width="100%" height="100%" fill="#f7f7f3"/>',
        f'<rect x="{margin}" y="{margin}" width="{part.length}" height="{part.width}" rx="{part.corner_radius}" fill="#d9dee4" stroke="#1f2933" stroke-width="1.2"/>',
    ]
    for hole in part.holes:
        cx = margin + hole.x
        cy = margin + hole.y
        radius = hole.diameter / 2
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="#f7f7f3" stroke="#1f2933" stroke-width="1"/>'
        )
        if hole.label:
            parts.append(
                f'<text x="{cx + radius + 2}" y="{cy - radius - 2}" font-family="Arial" font-size="4" fill="#374151">{hole.label}</text>'
            )
    parts.extend(
        [
            f'<text x="{margin}" y="{view_height - margin / 2}" font-family="Arial" font-size="5" fill="#111827">{part.name} - {part.length} x {part.width} x {part.thickness} {job.units}</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(parts), encoding="utf-8")


def write_report_pdf(job: CadJob, path: Path, backend: str, generated_step: bool) -> None:
    part = job.part
    lines = [
        "VibeCading CAD Agent - Mounting Plate Report",
        f"Job ID: {job.job_id}",
        f"Backend: {backend}",
        f"Part: {part.name}",
        f"Material: {part.material or 'unspecified'}",
        f"Size: {part.length} x {part.width} x {part.thickness} {job.units}",
        f"Corner radius: {part.corner_radius} {job.units}",
        f"Holes: {len(part.holes)}",
        f"STEP generated: {'yes' if generated_step else 'no'}",
    ]
    for index, hole in enumerate(part.holes, start=1):
        lines.append(f"Hole {index}: x={hole.x}, y={hole.y}, diameter={hole.diameter}, label={hole.label or '-'}")
    write_simple_pdf(lines, path)


def write_feature_part_svg(job: CadJob, path: Path) -> None:
    part = job.part
    operation = part.operations[0]
    params = operation.parameters
    base_length = float(params["base_length"])
    height = float(params["height"])
    width = float(params["width"])
    base_thickness = float(params["base_thickness"])
    wall_thickness = float(params["wall_thickness"])
    margin = max(base_length, height) * 0.08
    view_width = base_length + margin * 2
    view_height = height + margin * 2
    x0 = margin
    y0 = margin
    points = [
        (x0, y0 + height),
        (x0 + base_length, y0 + height),
        (x0 + base_length, y0 + height - base_thickness),
        (x0 + wall_thickness, y0 + height - base_thickness),
        (x0 + wall_thickness, y0),
        (x0, y0),
    ]
    point_text = " ".join(f"{x},{y}" for x, y in points)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{view_width}mm" height="{view_height}mm" viewBox="0 0 {view_width} {view_height}">',
        '<rect width="100%" height="100%" fill="#f7f7f3"/>',
        f'<polygon points="{point_text}" fill="#d9dee4" stroke="#1f2933" stroke-width="1.2"/>',
        f'<text x="{margin}" y="{view_height - margin / 2}" font-family="Arial" font-size="5" fill="#111827">{part.name} - L profile, extrusion width {width} {job.units}</text>',
        "</svg>",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")


def write_feature_part_report_pdf(job: CadJob, path: Path, backend: str, generated_step: bool) -> None:
    part = job.part
    lines = [
        "VibeCading CAD Agent - Feature Part Report",
        f"Job ID: {job.job_id}",
        f"Backend: {backend}",
        f"Part: {part.name}",
        f"Material: {part.material or 'unspecified'}",
        f"Operations: {len(part.operations)}",
        f"STEP generated: {'yes' if generated_step else 'no'}",
    ]
    for index, operation in enumerate(part.operations, start=1):
        lines.append(f"Operation {index}: {operation.id} / {operation.type}")
        for key, value in operation.parameters.items():
            lines.append(f"  {key}: {value}")
    write_simple_pdf(lines, path)


def _primitive_centerlines(part: PrimitivePart) -> dict[str, tuple[list[float], list[float]]]:
    centerlines: dict[str, tuple[list[float], list[float]]] = {}
    for operation in part.operations:
        if operation.type == "add_centerline":
            centerlines[operation.id] = (
                [float(item) for item in operation.parameters["start"]],
                [float(item) for item in operation.parameters["end"]],
            )
    return centerlines


def _mirror_point(point: list[float], axis: object, centerlines: dict[str, tuple[list[float], list[float]]]) -> list[float]:
    if isinstance(axis, dict) and str(axis.get("id", "")) in centerlines:
        start, end = centerlines[str(axis["id"])]
        x1, y1 = start
        x2, y2 = end
        dx = x2 - x1
        dy = y2 - y1
        length_squared = dx * dx + dy * dy
        if length_squared > 0:
            t = ((point[0] - x1) * dx + (point[1] - y1) * dy) / length_squared
            projected_x = x1 + t * dx
            projected_y = y1 + t * dy
            return [2 * projected_x - point[0], 2 * projected_y - point[1]]

    orientation = str(axis.get("orientation", axis.get("axis", "vertical")) if isinstance(axis, dict) else axis).lower()
    offset = float(axis.get("offset", 0) if isinstance(axis, dict) else 0)
    if orientation in {"x", "horizontal"}:
        return [point[0], 2 * offset - point[1]]
    return [2 * offset - point[0], point[1]]


def _primitive_circle_instances(part: PrimitivePart) -> list[dict[str, object]]:
    circles: list[dict[str, object]] = []
    circle_specs: dict[str, dict[str, object]] = {}
    centerlines = _primitive_centerlines(part)
    for operation in part.operations:
        if operation.type == "add_circle":
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            circle = {
                "id": operation.id,
                "sketch": operation.parameters["sketch"],
                "center": [center_x, center_y],
                "diameter": float(operation.parameters["diameter"]),
            }
            circles.append(circle)
            circle_specs[operation.id] = circle
        elif operation.type == "add_mirrored_circle":
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            circle = {
                "id": operation.id,
                "sketch": operation.parameters["sketch"],
                "center": [center_x, center_y],
                "diameter": float(operation.parameters["diameter"]),
            }
            mirrored = dict(circle)
            mirrored["id"] = f"{operation.id}_mirrored"
            mirrored["center"] = _mirror_point([center_x, center_y], operation.parameters["axis"], centerlines)
            circles.extend([circle, mirrored])
            circle_specs[operation.id] = circle
        elif operation.type == "add_circle_linear_pattern":
            source = circle_specs.get(str(operation.parameters["source"]))
            if source is None:
                continue
            count = int(operation.parameters["count"])
            spacing_x, spacing_y = [float(item) for item in operation.parameters["spacing"]]
            source_center_x, source_center_y = source["center"]
            for index in range(1, count):
                circle = {
                    "id": f"{operation.id}_{index}",
                    "sketch": operation.parameters["sketch"],
                    "center": [source_center_x + spacing_x * index, source_center_y + spacing_y * index],
                    "diameter": float(source["diameter"]),
                }
                circles.append(circle)
                circle_specs[str(circle["id"])] = circle
    return circles


def _primitive_outline(part: PrimitivePart) -> tuple[list[list[float]], list[dict[str, object]]]:
    outline: list[list[float]] = []
    for operation in part.operations:
        if operation.type == "add_center_rectangle" and not outline:
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            size_x, size_y = [float(item) for item in operation.parameters["size"]]
            outline = [
                [center_x - size_x / 2, center_y - size_y / 2],
                [center_x + size_x / 2, center_y - size_y / 2],
                [center_x + size_x / 2, center_y + size_y / 2],
                [center_x - size_x / 2, center_y + size_y / 2],
            ]
        elif operation.type == "add_polyline" and not outline:
            outline = [[float(point[0]), float(point[1])] for point in operation.parameters["points"]]
        elif operation.type == "add_chamfered_rectangle" and not outline:
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            size_x, size_y = [float(item) for item in operation.parameters["size"]]
            chamfer = float(operation.parameters["chamfer"])
            x0 = center_x - size_x / 2
            x1 = center_x + size_x / 2
            y0 = center_y - size_y / 2
            y1 = center_y + size_y / 2
            outline = [
                [x0 + chamfer, y0],
                [x1 - chamfer, y0],
                [x1, y0 + chamfer],
                [x1, y1 - chamfer],
                [x1 - chamfer, y1],
                [x0 + chamfer, y1],
                [x0, y1 - chamfer],
                [x0, y0 + chamfer],
            ]
        elif operation.type == "add_straight_slot" and not outline:
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            length = float(operation.parameters["length"])
            width = float(operation.parameters["width"])
            angle = math.radians(float(operation.parameters.get("angle", 0)))
            outline = _straight_slot_points(center_x, center_y, length, width, angle)
        elif operation.type == "add_polygon" and not outline:
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            radius = float(operation.parameters["radius"])
            sides = int(operation.parameters["sides"])
            angle = math.radians(float(operation.parameters.get("angle", 0)))
            outline = _regular_polygon_points(center_x, center_y, radius, sides, angle)
    return outline, _primitive_circle_instances(part)


def _straight_slot_points(center_x: float, center_y: float, length: float, width: float, angle: float) -> list[list[float]]:
    radius = width / 2
    axis_length = length - width
    ux = math.cos(angle)
    uy = math.sin(angle)
    nx = -uy
    ny = ux
    start_x = center_x - ux * axis_length / 2
    start_y = center_y - uy * axis_length / 2
    end_x = center_x + ux * axis_length / 2
    end_y = center_y + uy * axis_length / 2
    points: list[list[float]] = [
        [start_x + nx * radius, start_y + ny * radius],
        [end_x + nx * radius, end_y + ny * radius],
    ]
    for index in range(1, 8):
        theta = angle + math.pi / 2 - math.pi * index / 8
        points.append([end_x + math.cos(theta) * radius, end_y + math.sin(theta) * radius])
    points.append([start_x - nx * radius, start_y - ny * radius])
    for index in range(1, 8):
        theta = angle - math.pi / 2 - math.pi * index / 8
        points.append([start_x + math.cos(theta) * radius, start_y + math.sin(theta) * radius])
    return points


def _regular_polygon_points(
    center_x: float,
    center_y: float,
    radius: float,
    sides: int,
    angle: float,
) -> list[list[float]]:
    return [
        [
            center_x + math.cos(angle + 2 * math.pi * index / sides) * radius,
            center_y + math.sin(angle + 2 * math.pi * index / sides) * radius,
        ]
        for index in range(sides)
    ]


def _sketch_ref_to_id(ref: object) -> str:
    if isinstance(ref, dict):
        return str(ref.get("sketch", "")).strip()
    return str(ref).strip()


def _primitive_sketch_geometry(
    part: PrimitivePart,
) -> tuple[
    dict[str, list[list[list[float]]]],
    dict[str, list[dict[str, object]]],
    dict[str, list[dict[str, object]]],
    dict[str, list[dict[str, object]]],
]:
    polylines_by_sketch: dict[str, list[list[list[float]]]] = {}
    circles_by_sketch: dict[str, list[dict[str, object]]] = {}
    arcs_by_sketch: dict[str, list[dict[str, object]]] = {}
    rectangles_by_sketch: dict[str, list[dict[str, object]]] = {}
    for operation in part.operations:
        if operation.type == "add_polyline":
            sketch = str(operation.parameters["sketch"])
            points = [[float(point[0]), float(point[1])] for point in operation.parameters["points"]]
            polylines_by_sketch.setdefault(sketch, []).append(points)
        elif operation.type == "add_arc":
            sketch = str(operation.parameters["sketch"])
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            start_x, start_y = [float(item) for item in operation.parameters["start"]]
            end_x, end_y = [float(item) for item in operation.parameters["end"]]
            radius = max(
                ((start_x - center_x) ** 2 + (start_y - center_y) ** 2) ** 0.5,
                ((end_x - center_x) ** 2 + (end_y - center_y) ** 2) ** 0.5,
            )
            arcs_by_sketch.setdefault(sketch, []).append(
                {
                    "id": operation.id,
                    "center": [center_x, center_y],
                    "start": [start_x, start_y],
                    "end": [end_x, end_y],
                    "radius": radius,
                }
            )
        elif operation.type == "add_center_rectangle":
            sketch = str(operation.parameters["sketch"])
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            size_x, size_y = [float(item) for item in operation.parameters["size"]]
            rectangles_by_sketch.setdefault(sketch, []).append(
                {
                    "id": operation.id,
                    "center": [center_x, center_y],
                    "size": [size_x, size_y],
                }
            )
        elif operation.type == "add_chamfered_rectangle":
            sketch = str(operation.parameters["sketch"])
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            size_x, size_y = [float(item) for item in operation.parameters["size"]]
            rectangles_by_sketch.setdefault(sketch, []).append(
                {
                    "id": operation.id,
                    "center": [center_x, center_y],
                    "size": [size_x, size_y],
                }
            )
        elif operation.type == "add_straight_slot":
            sketch = str(operation.parameters["sketch"])
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            length = float(operation.parameters["length"])
            width = float(operation.parameters["width"])
            angle = math.radians(float(operation.parameters.get("angle", 0)))
            polylines_by_sketch.setdefault(sketch, []).append(
                _straight_slot_points(center_x, center_y, length, width, angle)
            )
        elif operation.type == "add_polygon":
            sketch = str(operation.parameters["sketch"])
            center_x, center_y = [float(item) for item in operation.parameters["center"]]
            radius = float(operation.parameters["radius"])
            sides = int(operation.parameters["sides"])
            angle = math.radians(float(operation.parameters.get("angle", 0)))
            polylines_by_sketch.setdefault(sketch, []).append(
                _regular_polygon_points(center_x, center_y, radius, sides, angle)
            )
        elif operation.type == "add_spline":
            sketch = str(operation.parameters["sketch"])
            points = [[float(point[0]), float(point[1])] for point in operation.parameters["points"]]
            polylines_by_sketch.setdefault(sketch, []).append(points)
    for circle in _primitive_circle_instances(part):
        sketch = str(circle["sketch"])
        circles_by_sketch.setdefault(sketch, []).append(
            {
                "id": circle["id"],
                "center": circle["center"],
                "diameter": float(circle["diameter"]),
            }
        )
    return polylines_by_sketch, circles_by_sketch, arcs_by_sketch, rectangles_by_sketch


def _plane_ref_from_target(target: object) -> str | None:
    if isinstance(target, str):
        return target
    if not isinstance(target, dict):
        return None
    target_type = str(target.get("type", "body_face")).lower()
    if target_type not in {"plane", "reference_plane", "datum_plane"}:
        return None
    plane_ref = target.get("name") or target.get("plane") or target.get("ref") or target.get("id")
    return str(plane_ref).strip() if plane_ref is not None else None


def _primitive_sketch_planes(part: PrimitivePart) -> dict[str, str]:
    sketch_planes: dict[str, str] = {}
    for operation in part.operations:
        if operation.type == "start_sketch":
            sketch_planes[str(operation.parameters["sketch"])] = str(operation.parameters.get("plane", "base"))
    return sketch_planes


def _primitive_reference_plane_offsets(part: PrimitivePart) -> dict[str, float]:
    offsets: dict[str, float] = {
        "base": 0.0,
        "default": 0.0,
        "front": 0.0,
        "front_plane": 0.0,
        "top": 0.0,
        "top_plane": 0.0,
        "right": 0.0,
        "right_plane": 0.0,
        "前视": 0.0,
        "前视基准面": 0.0,
        "上视": 0.0,
        "上视基准面": 0.0,
        "右视": 0.0,
        "右视基准面": 0.0,
    }
    for operation in part.operations:
        if operation.type != "create_offset_plane":
            continue
        name = str(operation.parameters["name"])
        base_target = operation.parameters.get("base", operation.parameters.get("target"))
        base_ref = _plane_ref_from_target(base_target)
        base_offset = offsets.get(base_ref or "", 0.0)
        offset = float(operation.parameters["offset"])
        if bool(operation.parameters.get("reverse", False)):
            offset = -offset
        offsets[name] = base_offset + offset
    return offsets


def _profile_extent_points(
    profile_id: str,
    polylines_by_sketch: dict[str, list[list[list[float]]]],
    circles_by_sketch: dict[str, list[dict[str, object]]],
    rectangles_by_sketch: dict[str, list[dict[str, object]]],
) -> list[list[float]]:
    points = [
        point
        for polyline in polylines_by_sketch.get(profile_id, [])
        for point in polyline
    ]
    for circle in circles_by_sketch.get(profile_id, []):
        center_x, center_y = circle["center"]
        radius = float(circle["diameter"]) / 2
        points.extend(
            [
                [center_x - radius, center_y - radius],
                [center_x + radius, center_y + radius],
            ]
        )
    for rectangle in rectangles_by_sketch.get(profile_id, []):
        center_x, center_y = rectangle["center"]
        size_x, size_y = rectangle["size"]
        points.extend(
            [
                [center_x - float(size_x) / 2, center_y - float(size_y) / 2],
                [center_x + float(size_x) / 2, center_y + float(size_y) / 2],
            ]
        )
    return points


def primitive_bounds(part: PrimitivePart) -> dict[str, float]:
    outline, circles = _primitive_outline(part)
    points = list(outline)
    polylines_by_sketch, circles_by_sketch, arcs_by_sketch, rectangles_by_sketch = _primitive_sketch_geometry(part)
    sketch_planes = _primitive_sketch_planes(part)
    plane_offsets = _primitive_reference_plane_offsets(part)
    for circle in circles:
        center_x, center_y = circle["center"]
        radius = float(circle["diameter"]) / 2
        points.extend(
            [
                [center_x - radius, center_y - radius],
                [center_x + radius, center_y + radius],
            ]
        )
    if points:
        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)
    else:
        min_x = min_y = 0.0
        max_x = max_y = 1.0
    length = max_x - min_x
    width = max_y - min_y
    depth = 0.0
    for operation in part.operations:
        if operation.type == "extrude":
            depth = max(depth, float(operation.parameters["depth"]))
        elif operation.type in {"revolve", "cut_revolve"} and points:
            max_radius = max(abs(point[1]) for point in points)
            width = max(width, max_radius * 2)
            depth = max(depth, max_radius * 2)
        elif operation.type in {"sweep", "cut_sweep"}:
            path_id = _sketch_ref_to_id(operation.parameters["path"])
            profile_id = _sketch_ref_to_id(operation.parameters["profile"])
            path_points = [
                point
                for polyline in polylines_by_sketch.get(path_id, [])
                for point in polyline
            ]
            for arc in arcs_by_sketch.get(path_id, []):
                center_x, center_y = arc["center"]
                radius = float(arc["radius"])
                path_points.extend(
                    [
                        arc["start"],
                        arc["end"],
                        [center_x - radius, center_y - radius],
                        [center_x + radius, center_y + radius],
                    ]
                )
            profile_radius = max(
                (float(circle["diameter"]) / 2 for circle in circles_by_sketch.get(profile_id, [])),
                default=0.0,
            )
            profile_radius = max(
                profile_radius,
                max(
                    (
                        max(float(rectangle["size"][0]), float(rectangle["size"][1])) / 2
                        for rectangle in rectangles_by_sketch.get(profile_id, [])
                    ),
                    default=0.0,
                ),
            )
            if path_points:
                min_x = min(min_x, min(point[0] for point in path_points) - profile_radius)
                max_x = max(max_x, max(point[0] for point in path_points) + profile_radius)
                min_y = min(min_y, min(point[1] for point in path_points) - profile_radius)
                max_y = max(max_y, max(point[1] for point in path_points) + profile_radius)
                length = max_x - min_x
                width = max_y - min_y
            depth = max(depth, profile_radius * 2)
        elif operation.type in {"loft", "cut_loft"}:
            profile_ids = [_sketch_ref_to_id(profile) for profile in operation.parameters["profiles"]]
            loft_points = [
                point
                for profile_id in profile_ids
                for point in _profile_extent_points(profile_id, polylines_by_sketch, circles_by_sketch, rectangles_by_sketch)
            ]
            if loft_points:
                min_x = min(min_x, min(point[0] for point in loft_points))
                max_x = max(max_x, max(point[0] for point in loft_points))
                min_y = min(min_y, min(point[1] for point in loft_points))
                max_y = max(max_y, max(point[1] for point in loft_points))
                length = max_x - min_x
                width = max_y - min_y
            profile_offsets = [
                plane_offsets.get(sketch_planes.get(profile_id, ""), 0.0)
                for profile_id in profile_ids
            ]
            if profile_offsets:
                depth = max(depth, max(profile_offsets) - min(profile_offsets))
    return {
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "length": length,
        "width": width,
        "depth": depth,
    }


def primitive_hole_count(part: PrimitivePart) -> int:
    feature_profile_sketches = {
        _sketch_ref_to_id(operation.parameters["profile"])
        for operation in part.operations
        if operation.type in {"sweep", "cut_sweep"}
    }
    for operation in part.operations:
        if operation.type in {"loft", "cut_loft"}:
            feature_profile_sketches.update(_sketch_ref_to_id(profile) for profile in operation.parameters["profiles"])
    return sum(
        1
        for circle in _primitive_circle_instances(part)
        if str(circle["sketch"]) not in feature_profile_sketches
    )


def write_primitive_part_svg(job: CadJob, path: Path) -> None:
    part = job.part
    outline, circles = _primitive_outline(part)
    bounds = primitive_bounds(part)
    margin = max(bounds["length"], bounds["width"], 1.0) * 0.08
    view_width = bounds["length"] + margin * 2
    view_height = bounds["width"] + margin * 2

    def map_point(point: list[float]) -> tuple[float, float]:
        x = margin + point[0] - bounds["min_x"]
        y = margin + bounds["max_y"] - point[1]
        return x, y

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{view_width}mm" height="{view_height}mm" viewBox="0 0 {view_width} {view_height}">',
        '<rect width="100%" height="100%" fill="#f7f7f3"/>',
    ]
    if outline:
        point_text = " ".join(f"{x},{y}" for x, y in (map_point(point) for point in outline))
        parts.append(f'<polygon points="{point_text}" fill="#d9dee4" stroke="#1f2933" stroke-width="1.2"/>')
    for circle in circles:
        cx, cy = map_point(circle["center"])
        radius = float(circle["diameter"]) / 2
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="#f7f7f3" stroke="#1f2933" stroke-width="1"/>')
    parts.extend(
        [
            f'<text x="{margin}" y="{view_height - margin / 2}" font-family="Arial" font-size="5" fill="#111827">{part.name} - primitive operations: {len(part.operations)}</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(parts), encoding="utf-8")


def write_primitive_part_report_pdf(job: CadJob, path: Path, backend: str, generated_step: bool) -> None:
    part = job.part
    lines = [
        "VibeCading CAD Agent - Primitive Part Report",
        f"Job ID: {job.job_id}",
        f"Backend: {backend}",
        f"Part: {part.name}",
        f"Source kind: {part.source_kind}",
        f"Material: {part.material or 'unspecified'}",
        f"Primitive operations: {len(part.operations)}",
        f"STEP generated: {'yes' if generated_step else 'no'}",
    ]
    for index, operation in enumerate(part.operations, start=1):
        lines.append(f"Operation {index}: {operation.id} / {operation.type}")
    write_simple_pdf(lines, path)


class PreviewAdapter:
    name = "preview"

    def run_mounting_plate(self, job: CadJob, output_dir: Path) -> BackendResult:
        return self.run_primitive_part(compile_to_primitive_job(job), output_dir)

    def run_feature_part(self, job: CadJob, output_dir: Path) -> BackendResult:
        return self.run_primitive_part(compile_to_primitive_job(job), output_dir)

    def run_primitive_part(self, job: CadJob, output_dir: Path) -> BackendResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        part = job.part
        result = BackendResult(backend=self.name, ok=True)

        spec_path = output_dir / "job_spec.json"
        spec_path.write_text(json.dumps(job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        result.add_artifact(spec_path)

        if "svg" in part.export_formats:
            svg_path = output_dir / f"{part.name}_primitive.svg"
            write_primitive_part_svg(job, svg_path)
            result.add_artifact(svg_path)

        if "pdf" in part.export_formats:
            pdf_path = output_dir / f"{part.name}_report.pdf"
            write_primitive_part_report_pdf(job, pdf_path, backend=self.name, generated_step=False)
            result.add_artifact(pdf_path)

        unsupported = sorted(set(part.export_formats) - {"json", "pdf", "svg"})
        for item in unsupported:
            result.warnings.append(f"Preview backend cannot generate real {item.upper()} CAD output.")

        bounds = primitive_bounds(part)
        primitive_types = [operation.type for operation in part.operations]
        result.metadata.update(
            {
                "bounding_box": {
                    "length": bounds["length"],
                    "width": bounds["width"],
                    "thickness": bounds["depth"],
                    "units": job.units,
                },
                "source_kind": part.source_kind,
                "operation_count": len(part.operations),
                "operation_types": primitive_types,
                "primitive_operation_types": primitive_types,
                "hole_count": primitive_hole_count(part),
                "completed_exports": [item for item in part.export_formats if item in {"json", "pdf", "svg"}],
                "unsupported_exports": unsupported,
            }
        )
        return result
