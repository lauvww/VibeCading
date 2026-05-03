from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from core.dsl import CadJob
from core.feature_plan import _BASE_BODY_FEATURE_ID, _predicted_feature_ids, build_feature_plan_reference_registry


PART_CONTEXT_VERSION = "part_context.v1"


def _job_dict(job: CadJob | dict[str, Any]) -> dict[str, Any]:
    if isinstance(job, CadJob):
        return job.to_dict()
    return copy.deepcopy(job)


def _set_nested_value(container: Any, path: list[str], value: float) -> None:
    current = container
    for key in path[:-1]:
        if isinstance(current, list):
            current = current[int(key)]
        else:
            current = current.setdefault(key, {})
    leaf = path[-1]
    if isinstance(current, list):
        current[int(leaf)] = value
    else:
        current[leaf] = value


def _apply_literal_updates(container: Any, updates: list[dict[str, Any]]) -> None:
    for update in updates:
        path = update.get("path")
        if not isinstance(path, list) or not path:
            continue
        current = container
        for key in path[:-1]:
            if isinstance(current, list):
                current = current[int(key)]
            else:
                current = current.setdefault(str(key), {})
        leaf = path[-1]
        value = copy.deepcopy(update.get("value"))
        if isinstance(current, list):
            current[int(leaf)] = value
        else:
            current[str(leaf)] = value


def _numeric_parameter_roles(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []

    def visit(value: Any, path: list[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, [*path, str(key)])
            return
        if isinstance(value, (int, float)) and path:
            role = str(path[-1])
            roles.append(
                {
                    "parameter_role": role,
                    "context_parameter_paths": [path],
                    "feature_parameter_paths": [path],
                    "value_mm": float(value),
                }
            )
            return
        if isinstance(value, list) and path and all(isinstance(item, (int, float)) for item in value):
            axis_names = ["x", "y", "z"]
            for index, item in enumerate(value[:3]):
                roles.append(
                    {
                        "parameter_role": f"{path[-1]}_{axis_names[index]}",
                        "context_parameter_paths": [[*path, str(index)]],
                        "feature_parameter_paths": [[*path, str(index)]],
                        "value_mm": float(item),
                    }
                )

    visit(parameters, [])
    return roles


def _hole_like_parameter_roles(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    holes = parameters.get("holes")
    if not isinstance(holes, list) or not holes:
        return roles

    diameters = []
    for index, hole in enumerate(holes):
        if not isinstance(hole, dict):
            return roles
        diameter = hole.get("diameter", hole.get("finished_diameter"))
        center = hole.get("center")
        if isinstance(diameter, (int, float)):
            diameters.append((index, float(diameter)))
        if len(holes) == 1 and isinstance(center, list) and len(center) >= 2 and all(isinstance(item, (int, float)) for item in center[:2]):
            roles.append(
                {
                    "parameter_role": "center_x",
                    "context_parameter_paths": [["holes", str(index), "center", "0"]],
                    "feature_parameter_paths": [["holes", str(index), "center", "0"]],
                    "value_mm": float(center[0]),
                }
            )
            roles.append(
                {
                    "parameter_role": "center_y",
                    "context_parameter_paths": [["holes", str(index), "center", "1"]],
                    "feature_parameter_paths": [["holes", str(index), "center", "1"]],
                    "value_mm": float(center[1]),
                }
            )
    if diameters and all(abs(value - diameters[0][1]) <= 1e-6 for _, value in diameters):
        hole_paths = [["holes", str(index), "diameter"] for index, _ in diameters]
        context_paths = [["hole_diameter"]]
        context_paths.extend(hole_paths)
        roles.append(
            {
                "parameter_role": "diameter",
                "context_parameter_paths": context_paths,
                "feature_parameter_paths": hole_paths,
                "value_mm": diameters[0][1],
            }
        )
    return roles


def _native_feature_type_for_feature(feature: dict[str, Any]) -> str:
    kind = str(feature.get("kind", ""))
    method = str(feature.get("method", ""))
    if kind == "base_body":
        return "Extrusion" if method == "extrude" else "Revolution"
    if kind in {"hole", "hole_pattern", "slot_or_pocket", "countersink", "counterbore", "threaded_hole"}:
        return "HoleWzd" if method == "hole_wizard" else "ICE"
    if kind in {"boss", "rib"}:
        return "Extrusion"
    if kind == "groove":
        return "CutRevolve"
    return ""


def _native_feature_name_bindings(feature_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(feature_plan, dict):
        return []
    features = list(feature_plan.get("features", []))
    predicted_ids = _predicted_feature_ids(feature_plan)
    bindings: list[dict[str, Any]] = []
    slot_index = 0
    boss_rib_index = 0
    for feature in features:
        if feature.get("required_parameters"):
            continue
        kind = str(feature.get("kind", ""))
        native_feature_name = ""
        if kind == "base_body":
            native_feature_name = _BASE_BODY_FEATURE_ID if str(feature_plan.get("dominant_geometry", "")) == "prismatic" else "旋转_外形成型"
        elif kind == "slot_or_pocket":
            slot_index += 1
            native_feature_name = predicted_ids["slot_or_pocket"].get(slot_index, "")
        elif kind in {"boss", "rib"}:
            boss_rib_index += 1
            native_feature_name = predicted_ids[kind].get(boss_rib_index, "")
        elif kind in {"hole", "hole_pattern"}:
            if bool(feature.get("parameters", {}).get("use_hole_wizard")) or str(feature.get("method", "")) == "hole_wizard":
                native_feature_name = f"孔向导_{feature.get('id', kind)}"
            else:
                native_feature_name = "拉伸切除_安装孔"
        elif kind in {"threaded_hole", "countersink", "counterbore"}:
            if bool(feature.get("parameters", {}).get("use_hole_wizard")) or str(feature.get("method", "")) == "hole_wizard":
                native_feature_name = f"孔向导_{feature.get('id', kind)}"
            else:
                native_feature_name = f"拉伸切除_{feature.get('id', kind)}"
        elif kind == "groove":
            native_feature_name = str(feature.get("functional_role") or feature.get("id") or "annular_groove")
        if not native_feature_name:
            continue
        parameter_roles = _numeric_parameter_roles(dict(feature.get("parameters", {})))
        if kind in {"hole", "hole_pattern", "threaded_hole", "countersink", "counterbore"}:
            parameter_roles.extend(_hole_like_parameter_roles(dict(feature.get("parameters", {}))))
        bindings.append(
            {
                "feature_id": str(feature.get("id", "")),
                "kind": kind,
                "functional_role": str(feature.get("functional_role", "")),
                "method": str(feature.get("method", "")),
                "native_feature_name": native_feature_name,
                "native_feature_type": _native_feature_type_for_feature(feature),
                "parameters_snapshot": copy.deepcopy(feature.get("parameters", {})),
                "parameter_roles": parameter_roles,
            }
        )
    return bindings


def build_part_context(
    *,
    job: CadJob | dict[str, Any],
    feature_plan: dict[str, Any] | None = None,
    request: str | None = None,
    strategy: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    existing_part_context: dict[str, Any] | None = None,
    edit_plan: dict[str, Any] | None = None,
    edit_dsl: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_data = _job_dict(job)
    part = dict(job_data.get("part", {}))
    summary_data = copy.deepcopy(summary or {})
    feature_plan_data = copy.deepcopy(feature_plan) if feature_plan else None
    previous_revision = int(existing_part_context.get("revision_index", 0)) if existing_part_context else 0
    revision_index = previous_revision + 1 if existing_part_context else 1
    lineage = list(existing_part_context.get("lineage", [])) if existing_part_context else []
    if existing_part_context and existing_part_context.get("job_id"):
        lineage = [*lineage, str(existing_part_context["job_id"])]
    context: dict[str, Any] = {
        "version": PART_CONTEXT_VERSION,
        "job_id": str(job_data.get("job_id", "")),
        "kind": str(job_data.get("kind", "")),
        "units": str(job_data.get("units", "mm")),
        "backend": str(job_data.get("backend", "auto")),
        "part_name": str(part.get("name", "")),
        "material": str(part.get("material", "")),
        "source_kind": str(part.get("source_kind", job_data.get("kind", ""))),
        "dominant_geometry": str(feature_plan_data.get("dominant_geometry", "")) if feature_plan_data else "",
        "parameters": copy.deepcopy(feature_plan_data.get("parameters", {})) if feature_plan_data else {},
        "engineering_context": copy.deepcopy(feature_plan_data.get("engineering_context", {})) if feature_plan_data else {},
        "feature_plan": feature_plan_data,
        "reference_registry": build_feature_plan_reference_registry(feature_plan_data) if feature_plan_data else {},
        "native_feature_bindings": _native_feature_name_bindings(feature_plan_data),
        "request": request or (feature_plan_data.get("request") if feature_plan_data else ""),
        "strategy": copy.deepcopy(strategy or {}),
        "edit_plan": copy.deepcopy(edit_plan or {}),
        "edit_dsl": copy.deepcopy(edit_dsl or {}),
        "revision_index": revision_index,
        "parent_job_id": str(existing_part_context.get("job_id", "")) if existing_part_context else "",
        "parent_context_path": str(existing_part_context.get("context_path", "")) if existing_part_context else "",
        "lineage": lineage,
        "summary_path": str(summary_data.get("summary_path", "")),
        "output_dir": str(summary_data.get("output_dir", "")),
    }
    metadata = summary_data.get("metadata") if isinstance(summary_data, dict) else None
    if isinstance(metadata, dict):
        native_feature_tree = metadata.get("native_feature_tree")
        if isinstance(native_feature_tree, dict):
            context["native_feature_tree"] = copy.deepcopy(native_feature_tree)
    return context


def build_native_edit_part_context(
    *,
    existing_part_context: dict[str, Any],
    summary: dict[str, Any],
    job_id: str,
    operation: str,
) -> dict[str, Any]:
    summary_data = copy.deepcopy(summary or {})
    metadata = summary_data.get("metadata") if isinstance(summary_data, dict) else {}
    previous_revision = int(existing_part_context.get("revision_index", 0))
    lineage = [*list(existing_part_context.get("lineage", [])), str(existing_part_context.get("job_id", ""))]
    native_tree = {}
    if isinstance(metadata, dict):
        native_tree = copy.deepcopy(metadata.get("native_feature_tree_after") or metadata.get("native_feature_tree") or {})
    context: dict[str, Any] = {
        "version": PART_CONTEXT_VERSION,
        "job_id": job_id,
        "kind": "native_feature_tree_edit",
        "units": str(existing_part_context.get("units", "mm")),
        "backend": str(summary_data.get("backend", existing_part_context.get("backend", "solidworks"))),
        "part_name": str(existing_part_context.get("part_name", "")),
        "material": str(existing_part_context.get("material", "")),
        "source_kind": "native_solidworks_feature_tree_edit",
        "dominant_geometry": str(existing_part_context.get("dominant_geometry", "")),
        "parameters": copy.deepcopy(existing_part_context.get("parameters", {})),
        "engineering_context": copy.deepcopy(existing_part_context.get("engineering_context", {})),
        "feature_plan": copy.deepcopy(existing_part_context.get("feature_plan")),
        "reference_registry": copy.deepcopy(existing_part_context.get("reference_registry", {})),
        "native_feature_bindings": copy.deepcopy(existing_part_context.get("native_feature_bindings", [])),
        "request": f"native:{operation}",
        "strategy": {"native_feature_tree_edit": True, "operation": operation},
        "edit_plan": {},
        "edit_dsl": {},
        "revision_index": previous_revision + 1,
        "parent_job_id": str(existing_part_context.get("job_id", "")),
        "parent_context_path": str(existing_part_context.get("context_path", "")),
        "lineage": [item for item in lineage if item],
        "summary_path": str(summary_data.get("summary_path", "")),
        "output_dir": str(summary_data.get("output_dir", "")),
        "native_feature_tree": native_tree,
        "native_edit": {
            "operation": operation,
            "selector": copy.deepcopy(metadata.get("selector", {})) if isinstance(metadata, dict) else {},
            "dimension_change": copy.deepcopy(metadata.get("dimension_change", {})) if isinstance(metadata, dict) else {},
            "feature_plan_sync": str(metadata.get("feature_plan_sync", "stale_after_native_tree_edit")) if isinstance(metadata, dict) else "stale_after_native_tree_edit",
        },
        "feature_plan_sync": "stale_after_native_tree_edit",
    }
    if isinstance(metadata, dict):
        sync_info = metadata.get("feature_plan_sync_info")
        if isinstance(sync_info, dict):
            context["feature_plan_sync_info"] = copy.deepcopy(sync_info)
            sync_status = str(sync_info.get("status", "")).strip()
            if sync_status:
                context["feature_plan_sync"] = sync_status
            if sync_status == "native_parameter_role_synced":
                feature_id = str(sync_info.get("feature_id", "")).strip()
                dimension_change = context["native_edit"].get("dimension_change", {})
                after_mm = dimension_change.get("after_mm", dimension_change.get("after_mm_target"))
                context_paths = sync_info.get("context_parameter_paths", [])
                feature_paths = sync_info.get("feature_parameter_paths", [])
                if isinstance(after_mm, (int, float)):
                    try:
                        if isinstance(context.get("parameters"), dict) and isinstance(context_paths, list):
                            for role_path in context_paths:
                                if isinstance(role_path, list):
                                    _set_nested_value(context["parameters"], [str(item) for item in role_path], float(after_mm))
                            _apply_literal_updates(context["parameters"], list(sync_info.get("context_literal_updates", [])))
                    except Exception:
                        pass
                    feature_plan = context.get("feature_plan")
                    if isinstance(feature_plan, dict):
                        try:
                            for feature in feature_plan.get("features", []):
                                if str(feature.get("id", "")).strip() == feature_id and isinstance(feature.get("parameters"), dict):
                                    if isinstance(feature_paths, list):
                                        for role_path in feature_paths:
                                            if isinstance(role_path, list):
                                                _set_nested_value(feature["parameters"], [str(item) for item in role_path], float(after_mm))
                                        _apply_literal_updates(feature["parameters"], list(sync_info.get("feature_literal_updates", [])))
                                    break
                        except Exception:
                            pass
    return context


def write_part_context(path: Path, context: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _ensure_native_feature_bindings(context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        return context
    if isinstance(context.get("native_feature_bindings"), list) and context["native_feature_bindings"]:
        return context
    feature_plan = context.get("feature_plan")
    if isinstance(feature_plan, dict):
        context["native_feature_bindings"] = _native_feature_name_bindings(feature_plan)
    return context


def load_part_context(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("version") == PART_CONTEXT_VERSION:
        loaded = copy.deepcopy(data)
        loaded["context_path"] = str(file_path)
        return _ensure_native_feature_bindings(loaded)
    if isinstance(data, dict) and isinstance(data.get("part_context"), dict):
        loaded = copy.deepcopy(data["part_context"])
        loaded["context_path"] = str(file_path)
        return _ensure_native_feature_bindings(loaded)
    metadata = data.get("metadata") if isinstance(data, dict) else None
    if isinstance(metadata, dict) and isinstance(metadata.get("part_context"), dict):
        loaded = copy.deepcopy(metadata["part_context"])
        loaded["context_path"] = str(file_path)
        return _ensure_native_feature_bindings(loaded)
    if isinstance(data, dict) and isinstance(data.get("natural_language"), dict):
        natural_language = data["natural_language"]
        if isinstance(natural_language.get("feature_plan"), dict) and isinstance(data.get("job"), dict):
            return _ensure_native_feature_bindings(build_part_context(
                job=data["job"],
                feature_plan=natural_language["feature_plan"],
                request=natural_language.get("request"),
                strategy=natural_language.get("strategy"),
                summary=data if "summary_path" in data else None,
            ))
    raise ValueError(f"Unsupported part context file format: {file_path}")
