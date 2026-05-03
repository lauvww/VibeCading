from __future__ import annotations

import copy
import contextlib
import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import winreg
from datetime import datetime
from pathlib import Path
from typing import Any

from adapters.base import BackendResult, BackendUnavailable
from adapters.preview_adapter import (
    primitive_drawing_annotation_plan,
    primitive_engineering_hole_callouts,
    primitive_bounds,
    primitive_hole_count,
    write_primitive_part_report_pdf,
    write_primitive_part_svg,
)
from adapters.solidworks_primitive_executor import SolidWorksPrimitiveExecutor
from core.dsl import CadJob
from core.template_compiler import compile_to_primitive_job


def _maybe_call(value: Any, *args: Any) -> Any:
    if callable(value):
        return value(*args)
    return value


_SOLIDWORKS_COM_LOCK = threading.RLock()


class SolidWorksComAdapter:
    name = "solidworks"
    server_root = Path(__file__).resolve().parents[1]
    _last_save_report: list[dict[str, object]] = []
    _swgen_module = None
    _NATIVE_EDITABLE_FEATURE_TYPES = {
        "RefPlane",
        "ProfileFeature",
        "BossExtrude",
        "CutExtrude",
        "Extrusion",
        "ICE",
        "BossRevolve",
        "CutRevolve",
        "Sweep",
        "CutSweep",
        "Loft",
        "CutLoft",
        "Fillet",
        "Chamfer",
        "HoleWzd",
        "CirPattern",
        "MirrorPattern",
    }
    _NATIVE_SUPPRESSION_FEATURE_TYPES = {
        "BossExtrude",
        "CutExtrude",
        "Extrusion",
        "ICE",
        "BossRevolve",
        "CutRevolve",
        "Sweep",
        "CutSweep",
        "Loft",
        "CutLoft",
        "Fillet",
        "Chamfer",
        "HoleWzd",
        "CirPattern",
        "MirrorPattern",
    }
    _NATIVE_DIMENSION_EDIT_FEATURE_TYPES = {
        "BossExtrude",
        "CutExtrude",
        "Extrusion",
        "ICE",
        "HoleWzd",
    }
    _PARAMETER_ROLE_RULES = {
        "length": {
            "aliases": {"length", "overall_length"},
            "preferred_owner_order": ["sketch", "feature"],
            "single_owner_fallback": {"sketch", "feature"},
        },
        "width": {
            "aliases": {"width", "overall_width"},
            "preferred_owner_order": ["sketch", "feature"],
            "single_owner_fallback": {"sketch", "feature"},
        },
        "thickness": {
            "aliases": {"thickness"},
            "preferred_owner_order": ["sketch", "feature"],
            "single_owner_fallback": {"sketch", "feature"},
        },
        "depth": {
            "aliases": {"depth", "height"},
            "preferred_owner_order": ["feature", "sketch"],
            "single_owner_fallback": {"feature"},
        },
        "height": {
            "aliases": {"height", "depth"},
            "preferred_owner_order": ["feature", "sketch"],
            "single_owner_fallback": {"feature"},
        },
        "diameter": {
            "aliases": {"diameter", "hole_diameter", "bore_diameter", "major_diameter"},
            "preferred_owner_order": ["sketch", "feature"],
            "single_owner_fallback": {"sketch", "feature"},
            "allow_multi_match_same_value": True,
        },
        "center_x": {
            "aliases": {"center_x", "offset_x", "position_x"},
            "preferred_owner_order": ["sketch", "feature"],
            "single_owner_fallback": {"sketch", "feature"},
        },
        "center_y": {
            "aliases": {"center_y", "offset_y", "position_y"},
            "preferred_owner_order": ["sketch", "feature"],
            "single_owner_fallback": {"sketch", "feature"},
        },
        "nominal_size": {
            "aliases": {"nominal_size", "size_label", "fastener_size"},
            "preferred_owner_order": ["feature", "sketch"],
            "single_owner_fallback": set(),
        },
        "thread_size": {
            "aliases": {"thread_size", "size_label", "fastener_size"},
            "preferred_owner_order": ["feature", "sketch"],
            "single_owner_fallback": set(),
        },
        "counterbore_diameter": {
            "aliases": {"counterbore_diameter", "head_diameter", "seat_diameter"},
            "preferred_owner_order": ["feature", "sketch"],
            "single_owner_fallback": set(),
        },
        "counterbore_depth": {
            "aliases": {"counterbore_depth", "seat_depth"},
            "preferred_owner_order": ["feature", "sketch"],
            "single_owner_fallback": set(),
        },
        "countersink_diameter": {
            "aliases": {"countersink_diameter", "head_diameter", "seat_diameter"},
            "preferred_owner_order": ["feature", "sketch"],
            "single_owner_fallback": set(),
        },
    }
    _SOLIDWORKS_TYPELIB_GUID = "83A33D31-27C5-11CE-BFD4-00400513BB57"
    _NATIVE_CAPABILITY_REGISTRY = [
        {
            "name": "extrude_feature_definition_depth_like",
            "feature_types": {"Extrusion", "ICE"},
            "parameter_roles": {"depth", "height", "thickness"},
            "edit_path": "feature_definition_modify",
            "sync_policy": "definition_depth_like",
            "requires_single_feature_owned_dimension": True,
        },
        {
            "name": "hole_wizard_size_change",
            "feature_types": {"HoleWzd"},
            "parameter_roles": {"nominal_size", "thread_size"},
            "edit_path": "feature_definition_modify",
            "sync_policy": "hole_wizard_size_change",
            "requires_binding": True,
        },
        {
            "name": "hole_wizard_counterbore_definition",
            "feature_types": {"HoleWzd"},
            "parameter_roles": {"counterbore_diameter", "counterbore_depth"},
            "edit_path": "feature_definition_modify",
            "sync_policy": "hole_wizard_counterbore_definition",
            "requires_binding": True,
        },
        {
            "name": "hole_wizard_countersink_definition",
            "feature_types": {"HoleWzd"},
            "parameter_roles": {"countersink_diameter"},
            "edit_path": "feature_definition_modify",
            "sync_policy": "hole_wizard_countersink_definition",
            "requires_binding": True,
        },
        {
            "name": "dimension_parameter_fallback",
            "feature_types": {"Extrusion", "ICE", "HoleWzd"},
            "parameter_roles": {
                "length",
                "width",
                "thickness",
                "depth",
                "height",
                "diameter",
                "center_x",
                "center_y",
                "nominal_size",
                "thread_size",
                "counterbore_diameter",
                "counterbore_depth",
                "countersink_diameter",
            },
            "edit_path": "dimension_parameter",
            "sync_policy": "role_resolution_rules",
        },
    ]

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("win32com") is not None

    @classmethod
    def template_candidates(cls) -> list[Path]:
        return sorted(cls.server_root.rglob("*.PRTDOT"), key=lambda path: (len(path.parts), str(path).lower()))

    @classmethod
    def find_part_template(cls) -> Path:
        for path in cls.template_candidates():
            if path.exists():
                return path
        raise BackendUnavailable(f"No SolidWorks part template was found under: {cls.server_root}")

    def check_connection(self, visible: bool = True) -> dict[str, object]:
        with self._solidworks_session():
            sw = self._connect(visible=visible)
            template = self.find_part_template()
            return {
                "ok": True,
                "backend": self.name,
                "revision": str(sw.RevisionNumber),
                "visible": bool(sw.Visible),
                "part_template": str(template),
                "part_template_exists": template.exists(),
                "active_doc": bool(sw.ActiveDoc),
            }

    def _connect(self, visible: bool = True):
        if not self.is_available():
            raise BackendUnavailable("pywin32/win32com is not available in this Python environment.")

        import win32com.client  # type: ignore[import-not-found]

        try:
            sw = win32com.client.GetActiveObject("SldWorks.Application")
            _ = str(sw.RevisionNumber)
        except Exception:
            try:
                sw = win32com.client.Dispatch("SldWorks.Application")
            except Exception as exc:
                raise self._solidworks_process_unstable_message("Dispatch(SldWorks.Application)", exc) from exc
        try:
            _ = str(sw.RevisionNumber)
            sw.Visible = visible
        except Exception as exc:
            raise self._solidworks_process_unstable_message("SolidWorks session health probe", exc) from exc
        return sw

    @contextlib.contextmanager
    def _solidworks_session(self, timeout_ms: int = 120000):
        import pythoncom  # type: ignore[import-not-found]

        pythoncom.CoInitialize()
        acquired = False
        try:
            acquired = _SOLIDWORKS_COM_LOCK.acquire(timeout=max(timeout_ms / 1000.0, 0.1))
            if not acquired:
                raise BackendUnavailable("另一个 SolidWorks API 会话仍在运行，当前为了避免进程级异常，已拒绝并发进入。")
            self._assert_single_solidworks_process()
            yield
        finally:
            try:
                if acquired:
                    _SOLIDWORKS_COM_LOCK.release()
            except Exception:
                pass
            pythoncom.CoUninitialize()

    @staticmethod
    def _solidworks_processes() -> list[dict[str, str]]:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=False,
            )
        except Exception:
            return []
        rows: list[dict[str, str]] = []
        for raw in result.stdout.splitlines():
            line = raw.strip()
            if not line or "没有运行的任务" in line or "No tasks are running" in line:
                continue
            try:
                parsed = next(csv.reader([line]))
            except Exception:
                continue
            if len(parsed) < 2:
                continue
            if parsed[0].strip().upper() != "SLDWORKS.EXE":
                continue
            rows.append({"image_name": parsed[0].strip(), "pid": parsed[1].strip()})
        return rows

    @classmethod
    def _assert_single_solidworks_process(cls) -> None:
        processes = cls._solidworks_processes()
        if len(processes) <= 1:
            return
        process_ids = ", ".join(item.get("pid", "?") for item in processes)
        raise BackendUnavailable(
            "检测到多个 SolidWorks 进程，当前 COM 状态可能不稳定。"
            f" 当前 SLDWORKS.exe 数量={len(processes)}，PID={process_ids}。"
            " 请先手动关闭异常弹窗并只保留一个 SolidWorks 实例后重试。"
        )

    @staticmethod
    def _solidworks_process_unstable_message(action: str, exc: Exception) -> BackendUnavailable:
        return BackendUnavailable(
            "SolidWorks COM 调用失败，当前进程可能已经因为前一次建模异常进入不稳定状态。"
            f" 操作={action}；异常={exc!r}。请关闭当前 SolidWorks 弹窗并重启 SolidWorks 后再重试。"
        )

    @staticmethod
    def _doc_type_from_path(path: Path) -> tuple[int, str]:
        suffix = path.suffix.lower()
        if suffix in {".sldprt", ".prtdot"}:
            return 1, "part"
        if suffix in {".sldasm", ".asmdot"}:
            return 2, "assembly"
        if suffix in {".slddrw", ".drwdot"}:
            return 3, "drawing"
        raise BackendUnavailable(f"Unsupported SolidWorks document type for inspection: {path.suffix}")

    @classmethod
    def _solidworks_typelib_path(cls) -> Path:
        direct = Path("D:/SW/SOLIDWORKS/sldworks.tlb")
        if direct.exists():
            return direct
        try:
            key_path = fr"TypeLib\{{{cls._SOLIDWORKS_TYPELIB_GUID}}}"
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path) as key:
                version_count = winreg.QueryInfoKey(key)[0]
                versions = [winreg.EnumKey(key, index) for index in range(version_count)]
            for version in sorted(versions, reverse=True):
                for arch in ["win64", "win32"]:
                    try:
                        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, fr"{key_path}\{version}\0\{arch}") as subkey:
                            value, _ = winreg.QueryValueEx(subkey, None)
                            candidate = Path(str(value))
                            if candidate.exists():
                                return candidate
                    except Exception:
                        continue
        except Exception:
            pass
        raise BackendUnavailable("Could not locate SolidWorks type library for makepy generation.")

    @classmethod
    def _load_swgen_module(cls):
        if cls._swgen_module is not None:
            return cls._swgen_module
        from win32com.client import gencache, makepy  # type: ignore[import-not-found]

        generate_path = Path(gencache.GetGeneratePath())
        generated = sorted(generate_path.glob(f"{cls._SOLIDWORKS_TYPELIB_GUID}x*.py"))
        if not generated:
            makepy.GenerateFromTypeLibSpec(str(cls._solidworks_typelib_path()))
            generated = sorted(generate_path.glob(f"{cls._SOLIDWORKS_TYPELIB_GUID}x*.py"))
        if not generated:
            raise BackendUnavailable("SolidWorks makepy wrapper generation did not produce a module.")
        module_path = generated[-1]
        spec = importlib.util.spec_from_file_location("vibecading_swgen", module_path)
        if spec is None or spec.loader is None:
            raise BackendUnavailable(f"Could not load SolidWorks generated wrapper module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls._swgen_module = module
        return module

    @staticmethod
    def _feature_tree_selector(
        *,
        feature_name: str,
        feature_type: str,
        tree_index: int,
        depth: int,
        parent_feature_name: str | None,
        is_subfeature: bool,
    ) -> dict[str, object]:
        selector: dict[str, object] = {
            "feature_name": feature_name,
            "feature_type": feature_type,
            "tree_index": tree_index,
            "depth": depth,
            "is_subfeature": is_subfeature,
        }
        if parent_feature_name:
            selector["parent_feature_name"] = parent_feature_name
        return selector

    @classmethod
    def _feature_snapshot(
        cls,
        *,
        feature,
        tree_index: int,
        depth: int,
        parent_feature_name: str | None,
        relation: str,
        display_name: str | None = None,
        include_object: bool = False,
    ) -> dict[str, object]:
        feature_name = str(_maybe_call(feature.Name) or "")
        feature_type = str(_maybe_call(feature.GetTypeName2) or _maybe_call(feature.GetTypeName) or "")
        sketch_name = feature_name if feature_type in {"ProfileFeature", "3DProfileFeature"} else None
        children: list[str] = []
        try:
            child_array = _maybe_call(feature.GetChildren)
            if child_array:
                for child in child_array:
                    child_name = str(_maybe_call(child.Name) or "").strip()
                    if child_name:
                        children.append(child_name)
        except Exception:
            pass
        specific_type = None
        for getter_name in ["GetSpecificFeature2", "GetSpecificFeature"]:
            try:
                specific = _maybe_call(getattr(feature, getter_name))
                if specific is not None:
                    specific_type = type(specific).__name__
                    break
            except Exception:
                continue
        snapshot: dict[str, object] = {
            "tree_index": tree_index,
            "depth": depth,
            "name": feature_name,
            "type": feature_type,
            "relation": relation,
            "is_subfeature": relation != "top_level",
            "native_edit_candidate": feature_type in cls._NATIVE_EDITABLE_FEATURE_TYPES,
            "selector": cls._feature_tree_selector(
                feature_name=feature_name,
                feature_type=feature_type,
                tree_index=tree_index,
                depth=depth,
                parent_feature_name=parent_feature_name,
                is_subfeature=relation != "top_level",
            ),
        }
        if display_name and display_name != feature_name:
            snapshot["display_name"] = display_name
        if parent_feature_name:
            snapshot["parent_feature_name"] = parent_feature_name
        if sketch_name:
            snapshot["sketch_name"] = sketch_name
        if children:
            snapshot["child_feature_names"] = children
        if specific_type:
            snapshot["specific_feature_type"] = specific_type
        if include_object:
            snapshot["_feature_object"] = feature
        return snapshot

    @classmethod
    def _collect_feature_tree(cls, model, *, include_objects: bool = False) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        tree_index = 1

        def walk_tree_item(node, depth: int, parent_name: str | None) -> None:
            nonlocal tree_index
            while node:
                node_object = getattr(node, "Object", None)
                if node_object is not None:
                    snapshot = cls._feature_snapshot(
                        feature=node_object,
                        tree_index=tree_index,
                        depth=depth,
                        parent_feature_name=parent_name,
                        relation="top_level" if depth == 0 else "subfeature",
                        display_name=str(getattr(node, "Text", "") or ""),
                        include_object=include_objects,
                    )
                    rows.append(snapshot)
                    tree_index += 1
                    child = getattr(node, "GetFirstChild", None)
                    if child:
                        walk_tree_item(child, depth + 1, str(snapshot["name"]))
                node = getattr(node, "GetNext", None)

        try:
            feature_manager = model.FeatureManager
            root = _maybe_call(feature_manager.GetFeatureTreeRootItem2, 1)
            first = getattr(root, "GetFirstChild", None) if root is not None else None
            if first:
                walk_tree_item(first, 0, None)
                return rows
        except Exception:
            pass

        def walk_subfeatures(parent_feature, parent_name: str, depth: int) -> None:
            nonlocal tree_index
            subfeature = _maybe_call(parent_feature.GetFirstSubFeature)
            while subfeature:
                snapshot = cls._feature_snapshot(
                    feature=subfeature,
                    tree_index=tree_index,
                    depth=depth,
                    parent_feature_name=parent_name,
                    relation="subfeature",
                    include_object=include_objects,
                )
                rows.append(snapshot)
                tree_index += 1
                walk_subfeatures(subfeature, str(snapshot["name"]), depth + 1)
                subfeature = _maybe_call(subfeature.GetNextSubFeature)

        feature = _maybe_call(model.FirstFeature)
        while feature:
            snapshot = cls._feature_snapshot(
                feature=feature,
                tree_index=tree_index,
                depth=0,
                parent_feature_name=None,
                relation="top_level",
                include_object=include_objects,
            )
            rows.append(snapshot)
            tree_index += 1
            walk_subfeatures(feature, str(snapshot["name"]), 1)
            feature = _maybe_call(feature.GetNextFeature)
        return rows

    @staticmethod
    def _serializable_feature_rows(features: list[dict[str, object]]) -> list[dict[str, object]]:
        cleaned: list[dict[str, object]] = []
        for feature in features:
            copied = {key: value for key, value in feature.items() if key != "_feature_object"}
            cleaned.append(copied)
        return cleaned

    @staticmethod
    def _native_selector_matches(feature: dict[str, object], selector: dict[str, object]) -> bool:
        if not isinstance(selector, dict):
            return False
        match_keys = [
            "feature_name",
            "feature_type",
            "tree_index",
            "depth",
            "parent_feature_name",
            "is_subfeature",
        ]
        feature_selector = feature.get("selector", {})
        if not isinstance(feature_selector, dict):
            return False
        for key in match_keys:
            expected = selector.get(key)
            if expected in (None, "", []):
                continue
            if feature_selector.get(key) != expected:
                return False
        return True

    @classmethod
    def _match_native_feature(cls, features: list[dict[str, object]], selector: dict[str, object]) -> list[dict[str, object]]:
        return [feature for feature in features if cls._native_selector_matches(feature, selector)]

    @staticmethod
    def _selector_index(features: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
        by_type: dict[str, list[dict[str, object]]] = {}
        native_candidates: list[dict[str, object]] = []
        for feature in features:
            selector = dict(feature.get("selector", {}))
            feature_type = str(feature.get("type", ""))
            by_type.setdefault(feature_type, []).append(selector)
            if bool(feature.get("native_edit_candidate")):
                native_candidates.append(selector)
        return {
            "native_edit_candidates": native_candidates,
            "by_type": by_type,
        }

    @classmethod
    def _editable_top_level_candidates(cls, model, features: list[dict[str, object]]) -> list[dict[str, object]]:
        candidates: list[dict[str, object]] = []
        for feature in features:
            if bool(feature.get("is_subfeature", False)):
                continue
            feature_type = str(feature.get("type", ""))
            if feature_type not in cls._NATIVE_SUPPRESSION_FEATURE_TYPES and feature_type not in cls._NATIVE_DIMENSION_EDIT_FEATURE_TYPES:
                continue
            selector = dict(feature.get("selector", {}))
            if selector:
                candidate = dict(selector)
                supported_operations: list[str] = []
                if feature_type in cls._NATIVE_SUPPRESSION_FEATURE_TYPES:
                    supported_operations.extend(["suppress_feature", "unsuppress_feature"])
                if feature_type in cls._NATIVE_DIMENSION_EDIT_FEATURE_TYPES:
                    supported_operations.append("update_dimension")
                    dimensions = cls._feature_dimension_candidates(model, feature)
                    if dimensions:
                        candidate["dimension_candidates"] = dimensions
                    candidate["supported_parameter_roles"] = cls._supported_parameter_roles_for_feature_type(feature_type)
                candidate["supported_operations"] = supported_operations
                candidates.append(candidate)
        return candidates

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
    def _body_edges(body) -> list[Any]:
        try:
            edges = body.GetEdges()
        except Exception:
            return []
        if edges is None:
            return []
        if isinstance(edges, tuple | list):
            return list(edges)
        return [edges]

    @classmethod
    def _model_geometry_snapshot(cls, model) -> dict[str, object]:
        try:
            bodies = model.GetBodies2(0, True)
        except Exception:
            bodies = None
        if bodies is None:
            body_list: list[Any] = []
        elif isinstance(bodies, tuple | list):
            body_list = list(bodies)
        else:
            body_list = [bodies]
        face_count = 0
        edge_count = 0
        bounds = None
        for body in body_list:
            face_count += len(cls._body_faces(body))
            edge_count += len(cls._body_edges(body))
            try:
                box = body.GetBodyBox()
            except Exception:
                box = None
            if box and len(box) == 6:
                if bounds is None:
                    bounds = list(box)
                else:
                    bounds[0] = min(bounds[0], box[0])
                    bounds[1] = min(bounds[1], box[1])
                    bounds[2] = min(bounds[2], box[2])
                    bounds[3] = max(bounds[3], box[3])
                    bounds[4] = max(bounds[4], box[4])
                    bounds[5] = max(bounds[5], box[5])
        snapshot = {
            "body_count": len(body_list),
            "face_count": face_count,
            "edge_count": edge_count,
        }
        if bounds is not None:
            snapshot["bounding_box"] = {
                "min": bounds[:3],
                "max": bounds[3:],
                "size": [bounds[3] - bounds[0], bounds[4] - bounds[1], bounds[5] - bounds[2]],
            }
        return snapshot

    @classmethod
    def _feature_dimension_candidates(cls, model, feature: dict[str, object]) -> list[dict[str, object]]:
        if str(feature.get("type", "")) not in cls._NATIVE_DIMENSION_EDIT_FEATURE_TYPES:
            return []
        owner_names: list[tuple[str, str]] = []
        explicit_parent = str(feature.get("name", "")).strip()
        if explicit_parent:
            owner_names.append((explicit_parent, "feature"))
        candidate_sketch_rows = [
            row for row in cls._collect_feature_tree(model)
            if str(row.get("parent_feature_name", "")).strip() == explicit_parent
            and str(row.get("type", "")) == "ProfileFeature"
        ]
        for row in candidate_sketch_rows:
            sketch_name = str(row.get("name", "")).strip()
            if sketch_name:
                owner_names.append((sketch_name, "sketch"))
        dimensions: list[dict[str, object]] = []
        seen: set[str] = set()
        for owner_name, owner_kind in list(dict.fromkeys(owner_names)):
            misses = 0
            for index in range(1, 33):
                dimension_id = f"D{index}@{owner_name}"
                try:
                    parameter = model.Parameter(dimension_id)
                except Exception:
                    parameter = None
                if parameter is None:
                    misses += 1
                    if misses >= 4 and index > 4:
                        break
                    continue
                misses = 0
                try:
                    full_name = str(parameter.FullName)
                except Exception:
                    full_name = dimension_id
                if full_name in seen:
                    continue
                seen.add(full_name)
                try:
                    system_value = float(parameter.SystemValue)
                except Exception:
                    continue
                dimensions.append(
                    {
                        "dimension_name": dimension_id,
                        "full_name": full_name,
                        "owner_name": owner_name,
                        "owner_kind": owner_kind,
                        "sketch_name": owner_name if owner_kind == "sketch" else "",
                        "system_value": system_value,
                        "value_mm": system_value * 1000.0,
                    }
                )
        return dimensions

    @classmethod
    def _parameter_role_rule(cls, parameter_role: str) -> dict[str, object]:
        role = str(parameter_role).strip().lower()
        default_rule = {
            "aliases": {role},
            "preferred_owner_order": ["sketch", "feature"],
            "single_owner_fallback": {"sketch", "feature"},
        }
        for canonical_role, rule in cls._PARAMETER_ROLE_RULES.items():
            aliases = set(rule.get("aliases", []))
            if role == canonical_role or role in aliases:
                merged = dict(default_rule)
                merged.update(rule)
                merged["canonical_role"] = canonical_role
                return merged
        default_rule["canonical_role"] = role
        return default_rule

    @classmethod
    def _prefer_dimension_matches(
        cls,
        matches: list[dict[str, object]],
        preferred_owner_order: list[str],
    ) -> list[dict[str, object]]:
        if len(matches) <= 1:
            return matches
        for owner_kind in preferred_owner_order:
            owned = [item for item in matches if str(item.get("owner_kind", "")) == owner_kind]
            if owned:
                return owned
        return matches

    @classmethod
    def _match_native_binding(
        cls,
        native_feature_bindings: list[dict[str, object]] | None,
        selected_feature: dict[str, object],
    ) -> dict[str, object] | None:
        if not isinstance(native_feature_bindings, list):
            return None
        name = str(selected_feature.get("name", "")).strip()
        feature_type = str(selected_feature.get("type", "")).strip()
        exact_name_matches = [
            item
            for item in native_feature_bindings
            if str(item.get("native_feature_name", "")).strip() == name
        ]
        if len(exact_name_matches) == 1:
            return exact_name_matches[0]
        if not exact_name_matches:
            exact_name_matches = [
                item
                for item in native_feature_bindings
                if name.startswith(str(item.get("native_feature_name", "")).strip() + "_")
            ]
            if len(exact_name_matches) == 1:
                return exact_name_matches[0]
        typed_matches = [
            item
            for item in exact_name_matches
            if not str(item.get("native_feature_type", "")).strip()
            or str(item.get("native_feature_type", "")).strip() == feature_type
        ]
        return typed_matches[0] if len(typed_matches) == 1 else None

    @classmethod
    def _resolve_native_capability(
        cls,
        *,
        selected_feature: dict[str, object],
        canonical_role: str,
        native_feature_bindings: list[dict[str, object]] | None,
        candidates_to_update: list[dict[str, object]],
    ) -> dict[str, object] | None:
        binding = cls._match_native_binding(native_feature_bindings, selected_feature)
        feature_type = str(selected_feature.get("type", "")).strip()
        for capability in cls._NATIVE_CAPABILITY_REGISTRY:
            if feature_type not in capability["feature_types"]:
                continue
            if canonical_role not in capability["parameter_roles"]:
                continue
            if capability.get("requires_binding") and binding is None:
                continue
            if capability.get("requires_single_feature_owned_dimension"):
                if len(candidates_to_update) != 1 or str(candidates_to_update[0].get("owner_kind", "")) != "feature":
                    continue
            return capability
        return None

    @classmethod
    def _supported_parameter_roles_for_feature_type(cls, feature_type: str) -> list[str]:
        roles: list[str] = []
        for capability in cls._NATIVE_CAPABILITY_REGISTRY:
            if feature_type not in capability["feature_types"]:
                continue
            roles.extend(str(role) for role in capability["parameter_roles"])
        return sorted(dict.fromkeys(roles))

    @staticmethod
    def _sync_override_for_binding(binding: dict[str, object], canonical_role: str) -> dict[str, object] | None:
        kind = str(binding.get("kind", "")).strip()
        method = str(binding.get("method", "")).strip()
        if canonical_role == "thickness" and kind == "base_body" and method == "extrude":
            return {
                "context_parameter_paths": [["thickness"]],
                "feature_parameter_paths": [["thickness"]],
            }
        if canonical_role in {"height", "depth"} and kind in {"boss", "rib"} and method == "extrude":
            return {
                "context_parameter_paths": [["height"]],
                "feature_parameter_paths": [["height"]],
            }
        if canonical_role in {"depth", "height"} and kind in {"hole", "hole_pattern", "threaded_hole", "counterbore", "countersink"} and method == "cut_extrude":
            return {
                "context_parameter_paths": [["depth"]],
                "feature_parameter_paths": [["depth"]],
                "context_literal_updates": [{"path": ["through"], "value": False}],
                "feature_literal_updates": [{"path": ["through"], "value": False}],
            }
        return None

    @staticmethod
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

    @staticmethod
    def _metric_size_label(value_mm: float) -> str:
        rounded = round(float(value_mm), 3)
        if abs(rounded - round(rounded)) <= 1e-6:
            return f"M{int(round(rounded))}"
        return f"M{rounded:g}"

    @classmethod
    def _hole_wizard_sync_info(
        cls,
        *,
        binding: dict[str, object],
        canonical_role: str,
        target_mm: float,
    ) -> dict[str, object]:
        params = copy.deepcopy(binding.get("parameters_snapshot", {}))
        holes = params.get("holes") if isinstance(params.get("holes"), list) else []
        context_paths: list[list[str]] = []
        feature_paths: list[list[str]] = []
        context_literals: list[dict[str, object]] = []
        feature_literals: list[dict[str, object]] = []
        size_label = cls._metric_size_label(target_mm)
        if canonical_role in {"nominal_size", "thread_size"}:
            context_literals.append({"path": ["size_label"], "value": size_label})
            feature_literals.append({"path": ["size_label"], "value": size_label})
        if canonical_role == "thread_size":
            context_paths.append(["thread_size"])
            feature_paths.append(["thread_size"])
            thread_pitch = {
                3.0: 0.5,
                4.0: 0.7,
                5.0: 0.8,
                6.0: 1.0,
                8.0: 1.25,
                10.0: 1.5,
                12.0: 1.75,
            }.get(round(float(target_mm), 1))
            tap_drill = {
                3.0: 2.5,
                4.0: 3.3,
                5.0: 4.2,
                6.0: 5.0,
                8.0: 6.8,
                10.0: 8.5,
                12.0: 10.2,
            }.get(round(float(target_mm), 1))
            context_literals.append({"path": ["callout"], "value": f"M{target_mm:g}"})
            feature_literals.append({"path": ["callout"], "value": f"M{target_mm:g}"})
            if thread_pitch is not None:
                context_literals.append({"path": ["thread_pitch"], "value": thread_pitch})
                feature_literals.append({"path": ["thread_pitch"], "value": thread_pitch})
            if tap_drill is not None:
                context_literals.append({"path": ["tap_drill_diameter"], "value": tap_drill})
                feature_literals.append({"path": ["tap_drill_diameter"], "value": tap_drill})
        elif canonical_role == "nominal_size":
            context_paths.append(["nominal_size"])
            feature_paths.append(["nominal_size"])
            clearance_class = str(params.get("clearance_class", "")).strip() or "normal"
            finished = cls._metric_clearance_diameter(target_mm, clearance_class)
            if finished is not None:
                context_paths.append(["hole_diameter"])
                context_literals.append({"path": ["hole_diameter"], "value": finished})
        elif canonical_role == "counterbore_diameter":
            context_paths.append(["head_diameter"])
            feature_paths.append(["head_diameter"])
        elif canonical_role == "counterbore_depth":
            context_paths.append(["seat_depth"])
            feature_paths.append(["seat_depth"])
        elif canonical_role == "countersink_diameter":
            context_paths.append(["head_diameter"])
            feature_paths.append(["head_diameter"])

        for index, hole in enumerate(holes):
            if canonical_role == "thread_size":
                feature_paths.append(["holes", str(index), "thread_size"])
                context_paths.append(["holes", str(index), "thread_size"])
            elif canonical_role == "nominal_size":
                feature_paths.append(["holes", str(index), "nominal_size"])
                context_paths.append(["holes", str(index), "nominal_size"])
                clearance_class = str(hole.get("clearance_class", params.get("clearance_class", ""))).strip() or "normal"
                finished = cls._metric_clearance_diameter(target_mm, clearance_class)
                if finished is not None:
                    feature_literals.append({"path": ["holes", str(index), "diameter"], "value": finished})
                    feature_literals.append({"path": ["holes", str(index), "finished_diameter"], "value": finished})
                    context_literals.append({"path": ["holes", str(index), "diameter"], "value": finished})
                    context_literals.append({"path": ["holes", str(index), "finished_diameter"], "value": finished})
            elif canonical_role == "counterbore_diameter":
                feature_paths.append(["holes", str(index), "head_diameter"])
                context_paths.append(["holes", str(index), "head_diameter"])
            elif canonical_role == "counterbore_depth":
                feature_paths.append(["holes", str(index), "seat_depth"])
                context_paths.append(["holes", str(index), "seat_depth"])
            elif canonical_role == "countersink_diameter":
                feature_paths.append(["holes", str(index), "head_diameter"])
                context_paths.append(["holes", str(index), "head_diameter"])

        return {
            "status": "native_parameter_role_synced",
            "feature_id": str(binding.get("feature_id", "")),
            "functional_role": str(binding.get("functional_role", "")),
            "parameter_role": canonical_role,
            "native_feature_name": str(binding.get("native_feature_name", "")),
            "context_parameter_paths": context_paths,
            "feature_parameter_paths": feature_paths,
            "context_literal_updates": context_literals,
            "feature_literal_updates": feature_literals,
        }

    @classmethod
    def _hole_wizard_definition_update(
        cls,
        *,
        model,
        feature_object,
        canonical_role: str,
        target_mm: float,
    ) -> dict[str, object]:
        swgen = cls._load_swgen_module()
        wrapped_feature = swgen.IFeature(feature_object._oleobj_)
        definition_dispatch = wrapped_feature.GetDefinition()
        definition = swgen.WizardHoleFeatureData2(definition_dispatch._oleobj_)
        before_size = str(getattr(definition, "FastenerSize", ""))
        before_standard_type = int(getattr(definition, "Standard2", 0))
        before_fastener_type = int(getattr(definition, "FastenerType2", 0))
        before_counterbore_diameter = float(getattr(definition, "CounterBoreDiameter", 0.0)) * 1000.0
        before_counterbore_depth = float(getattr(definition, "CounterBoreDepth", 0.0)) * 1000.0
        before_countersink_diameter = float(getattr(definition, "CounterSinkDiameter", 0.0)) * 1000.0
        if not bool(definition.AccessSelections(model, None)):
            raise BackendUnavailable("SolidWorks Hole Wizard FeatureData access failed during native definition edit.")
        try:
            if canonical_role in {"nominal_size", "thread_size"}:
                size_label = cls._metric_size_label(target_mm)
                change_ok = bool(definition.ChangeStandard(before_standard_type, before_fastener_type, size_label))
            elif canonical_role == "counterbore_diameter":
                definition.CounterBoreDiameter = float(target_mm) / 1000.0
                change_ok = True
            elif canonical_role == "counterbore_depth":
                definition.CounterBoreDepth = float(target_mm) / 1000.0
                change_ok = True
            elif canonical_role == "countersink_diameter":
                definition.CounterSinkDiameter = float(target_mm) / 1000.0
                change_ok = True
            else:
                raise BackendUnavailable(f"Hole Wizard definition edit does not support role: {canonical_role}")
            modify_ok = bool(wrapped_feature.ModifyDefinition(definition, model, None))
        finally:
            try:
                definition.ReleaseSelectionAccess()
            except Exception:
                pass
        if not change_ok:
            raise BackendUnavailable("SolidWorks Hole Wizard ChangeStandard returned false.")
        if not modify_ok:
            raise BackendUnavailable("SolidWorks Hole Wizard ModifyDefinition returned false.")
        definition_after = swgen.WizardHoleFeatureData2(wrapped_feature.GetDefinition()._oleobj_)
        after_size = str(getattr(definition_after, "FastenerSize", ""))
        result = {
            "native_edit_path": "feature_definition_modify",
            "before_size_label": before_size,
            "after_size_label": after_size,
        }
        if canonical_role == "nominal_size":
            result["before_mm"] = float(before_size.strip().lstrip("M") or 0.0)
            result["after_mm"] = float(target_mm)
        elif canonical_role == "thread_size":
            result["before_mm"] = float(before_size.strip().lstrip("M") or 0.0)
            result["after_mm"] = float(target_mm)
        elif canonical_role == "counterbore_diameter":
            result["before_mm"] = before_counterbore_diameter
            result["after_mm"] = float(getattr(definition_after, "CounterBoreDiameter", 0.0)) * 1000.0
        elif canonical_role == "counterbore_depth":
            result["before_mm"] = before_counterbore_depth
            result["after_mm"] = float(getattr(definition_after, "CounterBoreDepth", 0.0)) * 1000.0
        elif canonical_role == "countersink_diameter":
            result["before_mm"] = before_countersink_diameter
            result["after_mm"] = float(getattr(definition_after, "CounterSinkDiameter", 0.0)) * 1000.0
        return result

    @classmethod
    def _resolve_dimension_candidate_by_role(
        cls,
        *,
        selected_feature: dict[str, object],
        dimension_candidates: list[dict[str, object]],
        parameter_role: str,
        native_feature_bindings: list[dict[str, object]] | None,
    ) -> tuple[list[dict[str, object]], dict[str, object] | None]:
        binding = cls._match_native_binding(native_feature_bindings, selected_feature)
        role_rule = cls._parameter_role_rule(parameter_role)
        canonical_role = str(role_rule.get("canonical_role", parameter_role))
        aliases = set(role_rule.get("aliases", []))
        preferred_owner_order = list(role_rule.get("preferred_owner_order", ["sketch", "feature"]))
        single_owner_fallback = set(role_rule.get("single_owner_fallback", {"sketch", "feature"}))
        allow_multi = bool(role_rule.get("allow_multi_match_same_value", False))
        if binding is not None:
            role_entries = [
                item
                for item in binding.get("parameter_roles", [])
                if str(item.get("parameter_role", "")).strip().lower() in aliases
            ]
            if len(role_entries) == 1:
                role_entry = role_entries[0]
                target_value = float(role_entry["value_mm"])
                tolerance = 1e-6
                matches = [
                    item
                    for item in dimension_candidates
                    if abs(float(item.get("value_mm", 0.0)) - target_value) <= tolerance
                ]
                preferred_matches = cls._prefer_dimension_matches(matches, preferred_owner_order)
                if len(preferred_matches) == 1 or (allow_multi and preferred_matches):
                    sync_info = {
                        "status": "native_parameter_role_synced",
                        "feature_id": str(binding.get("feature_id", "")),
                        "functional_role": str(binding.get("functional_role", "")),
                        "parameter_role": str(role_entry.get("parameter_role", "")),
                        "context_parameter_paths": copy.deepcopy(role_entry.get("context_parameter_paths", [])),
                        "feature_parameter_paths": copy.deepcopy(role_entry.get("feature_parameter_paths", [])),
                        "native_feature_name": str(binding.get("native_feature_name", "")),
                        "resolved_dimension_names": [str(item.get("dimension_name", "")) for item in preferred_matches],
                    }
                    return preferred_matches, sync_info

        override = cls._sync_override_for_binding(binding, canonical_role) if binding is not None else None

        for owner_kind in preferred_owner_order:
            if owner_kind not in single_owner_fallback:
                continue
            owned = [item for item in dimension_candidates if str(item.get("owner_kind", "")) == owner_kind]
            if len(owned) == 1:
                sync_info = None
                if binding is not None and override is not None:
                    sync_info = {
                        "status": "native_parameter_role_synced",
                        "feature_id": str(binding.get("feature_id", "")),
                        "functional_role": str(binding.get("functional_role", "")),
                        "parameter_role": canonical_role,
                        "native_feature_name": str(binding.get("native_feature_name", "")),
                        "context_parameter_paths": copy.deepcopy(override.get("context_parameter_paths", [])),
                        "feature_parameter_paths": copy.deepcopy(override.get("feature_parameter_paths", [])),
                        "context_literal_updates": copy.deepcopy(override.get("context_literal_updates", [])),
                        "feature_literal_updates": copy.deepcopy(override.get("feature_literal_updates", [])),
                        "resolved_dimension_name": str(owned[0].get("dimension_name", "")),
                    }
                elif binding is not None:
                    sync_info = {
                        "status": "native_parameter_role_resolved_without_feature_plan_sync",
                        "feature_id": str(binding.get("feature_id", "")),
                        "functional_role": str(binding.get("functional_role", "")),
                        "parameter_role": canonical_role,
                        "native_feature_name": str(binding.get("native_feature_name", "")),
                        "resolved_dimension_name": str(owned[0].get("dimension_name", "")),
                    }
                return [owned[0]], sync_info
        return [], None

    @classmethod
    @classmethod
    def _feature_definition_update_dimension(
        cls,
        *,
        model,
        feature_object,
        target_mm: float,
    ) -> dict[str, object]:
        swgen = cls._load_swgen_module()
        wrapped_feature = swgen.IFeature(feature_object._oleobj_)
        definition_dispatch = wrapped_feature.GetDefinition()
        definition = swgen.ExtrudeFeatureData2(definition_dispatch._oleobj_)
        before_depth = float(definition.GetDepth(True)) * 1000.0
        if not bool(definition.AccessSelections(model, None)):
            raise BackendUnavailable("SolidWorks FeatureData access failed during native definition edit.")
        try:
            definition.SetDepth(True, float(target_mm) / 1000.0)
            modify_ok = bool(wrapped_feature.ModifyDefinition(definition, model, None))
        finally:
            try:
                definition.ReleaseSelectionAccess()
            except Exception:
                pass
        if not modify_ok:
            raise BackendUnavailable("SolidWorks ModifyDefinition failed during native definition edit.")
        definition_after = swgen.ExtrudeFeatureData2(wrapped_feature.GetDefinition()._oleobj_)
        after_depth = float(definition_after.GetDepth(True)) * 1000.0
        return {
            "native_edit_path": "feature_definition_modify",
            "before_mm": before_depth,
            "after_mm": after_depth,
        }

    def inspect_feature_tree(
        self,
        *,
        file_path: str | Path | None = None,
        use_active_doc: bool = False,
        visible: bool = True,
    ) -> dict[str, object]:
        with self._solidworks_session():
            sw = self._connect(visible=visible)
            opened_title: str | None = None
            model = None
            source = "active_doc"

            if file_path is not None:
                path = Path(file_path).resolve()
                if not path.exists():
                    raise BackendUnavailable(f"SolidWorks inspection file does not exist: {path}")
                doc_type, _ = self._doc_type_from_path(path)
                errors = self._byref_int()
                warnings = self._byref_int()
                model = sw.OpenDoc6(str(path), doc_type, 1, "", errors, warnings)
                if model is None:
                    raise BackendUnavailable(
                        f"SolidWorks failed to open document for feature-tree inspection: {path}; "
                        f"errors={self._variant_value(errors)} warnings={self._variant_value(warnings)}"
                    )
                opened_title = str(_maybe_call(model.GetTitle) or "")
                source = "file"
            elif use_active_doc:
                model = sw.ActiveDoc
                if model is None:
                    raise BackendUnavailable("SolidWorks has no active document to inspect.")
            else:
                model = sw.ActiveDoc
                if model is None:
                    raise BackendUnavailable("SolidWorks has no active document. Pass --file to inspect a saved part.")

            try:
                doc_type_value = int(_maybe_call(model.GetType) or 0)
            except Exception:
                doc_type_value = 0
            doc_type_name = {1: "part", 2: "assembly", 3: "drawing"}.get(doc_type_value, "unknown")
            features = self._collect_feature_tree(model)
            result = {
                "ok": True,
                "backend": self.name,
                "version": "solidworks_feature_tree.v1",
                "source": source,
                "model": {
                    "title": str(_maybe_call(model.GetTitle) or ""),
                    "path": str(_maybe_call(model.GetPathName) or ""),
                    "document_type": doc_type_name,
                    "solidworks_revision": str(sw.RevisionNumber),
                },
                "feature_count": len(features),
                "features": features,
                "selector_index": self._selector_index(features),
                "editable_top_level_candidates": self._editable_top_level_candidates(model, features),
                "geometry": self._model_geometry_snapshot(model),
            }
            if file_path is not None:
                result["requested_file"] = str(Path(file_path).resolve())
            try:
                config_name = str(_maybe_call(model.ConfigurationManager.ActiveConfiguration.Name) or "")
                if config_name:
                    result["model"]["active_configuration"] = config_name
            except Exception:
                pass
            try:
                extension = model.Extension
                result["model"]["selection_count"] = int(_maybe_call(extension.GetSelectedObjectCount2, -1) or 0)
            except Exception:
                pass
            finally:
                if opened_title:
                    try:
                        sw.CloseDoc(opened_title)
                    except Exception:
                        pass
            return result

    def native_edit_feature_tree(
        self,
        *,
        file_path: str | Path,
        selector: dict[str, object],
        operation: str,
        output_dir: Path,
        export_formats: list[str] | None = None,
        dimension_name: str | None = None,
        parameter_role: str | None = None,
        native_feature_bindings: list[dict[str, object]] | None = None,
        value_mm: float | None = None,
        visible: bool = True,
    ) -> dict[str, object]:
        with self._solidworks_session():
            return self._native_edit_feature_tree_unlocked(
                file_path=file_path,
                selector=selector,
                operation=operation,
                output_dir=output_dir,
                export_formats=export_formats,
                dimension_name=dimension_name,
                parameter_role=parameter_role,
                native_feature_bindings=native_feature_bindings,
                value_mm=value_mm,
                visible=visible,
            )

    def _native_edit_feature_tree_unlocked(
        self,
        *,
        file_path: str | Path,
        selector: dict[str, object],
        operation: str,
        output_dir: Path,
        export_formats: list[str] | None = None,
        dimension_name: str | None = None,
        parameter_role: str | None = None,
        native_feature_bindings: list[dict[str, object]] | None = None,
        value_mm: float | None = None,
        visible: bool = True,
    ) -> dict[str, object]:
        if operation not in {"suppress_feature", "unsuppress_feature", "update_dimension"}:
            raise BackendUnavailable(f"Unsupported native feature-tree operation: {operation}")

        path = Path(file_path).resolve()
        if not path.exists():
            raise BackendUnavailable(f"SolidWorks native edit file does not exist: {path}")
        doc_type, doc_kind = self._doc_type_from_path(path)
        if doc_kind != "part":
            raise BackendUnavailable("First-stage native SolidWorks tree edits are only enabled for SLDPRT files.")

        sw = self._connect(visible=visible)
        errors = self._byref_int()
        warnings = self._byref_int()
        model = sw.OpenDoc6(str(path), doc_type, 1, "", errors, warnings)
        if model is None:
            raise BackendUnavailable(
                f"SolidWorks failed to open document for native edit: {path}; "
                f"errors={self._variant_value(errors)} warnings={self._variant_value(warnings)}"
            )
        opened_title = str(_maybe_call(model.GetTitle) or "")

        try:
            live_tree_before = self._collect_feature_tree(model, include_objects=True)
            geometry_before = self._model_geometry_snapshot(model)
            matched = self._match_native_feature(live_tree_before, selector)
            if len(matched) != 1:
                raise BackendUnavailable(
                    f"SolidWorks native edit requires exactly one matched feature; matched={len(matched)} selector={json.dumps(selector, ensure_ascii=False)}"
                )
            selected = matched[0]
            feature_object = selected.get("_feature_object")
            if feature_object is None:
                raise BackendUnavailable("SolidWorks native edit matched feature has no live COM object.")
            if bool(selected.get("is_subfeature", False)):
                raise BackendUnavailable("First-stage native edits only support top-level features, not subfeatures.")
            if not bool(selected.get("native_edit_candidate", False)):
                raise BackendUnavailable(
                    f"Selected feature is not marked as a first-stage native edit candidate: {selected.get('type')}"
                )
            feature_type = str(selected.get("type", ""))
            if operation in {"suppress_feature", "unsuppress_feature"} and feature_type not in self._NATIVE_SUPPRESSION_FEATURE_TYPES:
                raise BackendUnavailable(
                    f"First-stage native {operation} is not enabled for feature type: {selected.get('type')}"
                )
            dimension_change: dict[str, object] | None = None

            if operation in {"suppress_feature", "unsuppress_feature"}:
                try:
                    model.ClearSelection2(True)
                except Exception:
                    pass
                if not bool(_maybe_call(feature_object.Select2, False, 0)):
                    raise BackendUnavailable(f"SolidWorks failed to select target feature for native edit: {selected.get('name')}")

                if operation == "suppress_feature":
                    op_ok = bool(_maybe_call(model.EditSuppress2))
                else:
                    op_ok = bool(_maybe_call(model.EditUnsuppress2))
                if not op_ok:
                    raise BackendUnavailable(f"SolidWorks failed to execute native operation {operation} on feature {selected.get('name')}.")
            else:
                if feature_type not in self._NATIVE_DIMENSION_EDIT_FEATURE_TYPES:
                    raise BackendUnavailable(
                        f"First-stage native update_dimension is not enabled for feature type: {selected.get('type')}"
                    )
                if not dimension_name and not parameter_role:
                    raise BackendUnavailable("update_dimension requires --dimension-name or --parameter-role.")
                if value_mm is None:
                    raise BackendUnavailable("update_dimension requires --value-mm.")
                canonical_role = str(self._parameter_role_rule(parameter_role or "").get("canonical_role", parameter_role or ""))
                binding = self._match_native_binding(native_feature_bindings, selected)
                dimension_candidates = self._feature_dimension_candidates(model, selected)
                sync_info = None
                candidates_to_update: list[dict[str, object]] = []
                if dimension_name:
                    candidate = next(
                        (
                            item
                            for item in dimension_candidates
                            if str(item.get("dimension_name", "")) == dimension_name or str(item.get("full_name", "")) == dimension_name
                        ),
                        None,
                    )
                    if candidate is not None:
                        candidates_to_update = [candidate]
                elif parameter_role:
                    candidates_to_update, sync_info = self._resolve_dimension_candidate_by_role(
                        selected_feature=selected,
                        dimension_candidates=dimension_candidates,
                        parameter_role=parameter_role,
                        native_feature_bindings=native_feature_bindings,
                    )
                provisional_capability = self._resolve_native_capability(
                    selected_feature=selected,
                    canonical_role=canonical_role,
                    native_feature_bindings=native_feature_bindings,
                    candidates_to_update=candidates_to_update,
                )
                if (
                    not candidates_to_update
                    and feature_type == "HoleWzd"
                    and provisional_capability is not None
                    and provisional_capability.get("edit_path") == "feature_definition_modify"
                    and binding is not None
                ):
                    sync_info = self._hole_wizard_sync_info(binding=binding, canonical_role=canonical_role, target_mm=float(value_mm))
                if not candidates_to_update and not (
                    feature_type == "HoleWzd"
                    and provisional_capability is not None
                    and provisional_capability.get("edit_path") == "feature_definition_modify"
                    and binding is not None
                ):
                    raise BackendUnavailable(
                        f"update_dimension could not resolve requested dimension under feature {selected.get('name')}: {dimension_name or parameter_role}"
                    )
                dimension_changes: list[dict[str, object]] = []
                capability = provisional_capability or self._resolve_native_capability(
                    selected_feature=selected,
                    canonical_role=canonical_role,
                    native_feature_bindings=native_feature_bindings,
                    candidates_to_update=candidates_to_update,
                )
                if capability and capability.get("edit_path") == "feature_definition_modify":
                    if feature_type == "HoleWzd":
                        definition_result = self._hole_wizard_definition_update(
                            model=model,
                            feature_object=feature_object,
                            canonical_role=canonical_role,
                            target_mm=float(value_mm),
                        )
                        candidate = {
                            "dimension_name": "",
                            "full_name": "",
                            "sketch_name": "",
                            "owner_name": str(selected.get("name", "")),
                            "owner_kind": "feature",
                        }
                    else:
                        definition_result = self._feature_definition_update_dimension(
                            model=model,
                            feature_object=feature_object,
                            target_mm=float(value_mm),
                        )
                        candidate = candidates_to_update[0]
                    dimension_changes.append(
                        {
                            "dimension_name": str(candidate["dimension_name"]),
                            "full_name": str(candidate["full_name"]),
                            "sketch_name": str(candidate["sketch_name"]),
                            "owner_name": str(candidate.get("owner_name", "")),
                            "owner_kind": str(candidate.get("owner_kind", "")),
                            "parameter_role": parameter_role or "",
                            "before_mm": definition_result["before_mm"],
                            "after_mm_target": float(value_mm),
                            "after_mm": definition_result["after_mm"],
                            "native_edit_path": definition_result["native_edit_path"],
                        }
                    )
                else:
                    target_system_value = float(value_mm) / 1000.0
                    for candidate in candidates_to_update:
                        parameter = model.Parameter(str(candidate["dimension_name"]))
                        if parameter is None:
                            raise BackendUnavailable(f"SolidWorks did not return a Parameter object for dimension {dimension_name or parameter_role}.")
                        before_system_value = float(parameter.SystemValue)
                        set_status = None
                        try:
                            set_status = parameter.SetSystemValue3(target_system_value, 1, None)
                        except Exception:
                            try:
                                parameter.SystemValue = target_system_value
                            except Exception as exc:
                                raise BackendUnavailable(f"SolidWorks failed to update dimension {dimension_name or parameter_role}: {exc}") from exc
                        dimension_changes.append(
                            {
                                "dimension_name": str(candidate["dimension_name"]),
                                "full_name": str(candidate["full_name"]),
                                "sketch_name": str(candidate["sketch_name"]),
                                "owner_name": str(candidate.get("owner_name", "")),
                                "owner_kind": str(candidate.get("owner_kind", "")),
                                "parameter_role": parameter_role or "",
                                "before_mm": before_system_value * 1000.0,
                                "after_mm_target": float(value_mm),
                                "set_status": set_status,
                                "native_edit_path": "dimension_parameter",
                            }
                        )
                dimension_change = dimension_changes[0]

            try:
                _maybe_call(model.EditRebuild3)
            except Exception:
                pass
            geometry_after = self._model_geometry_snapshot(model)
            if dimension_change is not None:
                for item in dimension_changes:
                    if "after_mm" in item:
                        continue
                    try:
                        parameter_after = model.Parameter(str(item["dimension_name"]))
                        if parameter_after is not None:
                            item["after_mm"] = float(parameter_after.SystemValue) * 1000.0
                    except Exception:
                        pass
                dimension_change = dimension_changes[0]
            sync_status = str(sync_info.get("status", "")) if isinstance(sync_info, dict) else ""
            warnings_list = [] if sync_status == "native_parameter_role_synced" else ["feature_plan_out_of_sync_after_native_tree_edit"]

            output_dir = output_dir.resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            target_sldprt = self._fresh_output_path(output_dir / path.name)
            if not self._save_as(model, target_sldprt, sw=sw):
                attempts = json.dumps(self._last_save_report[-4:], ensure_ascii=False)
                raise BackendUnavailable(f"SolidWorks failed to save native-edited part: {target_sldprt}; save_attempts={attempts}")

            artifacts = [str(target_sldprt)]
            completed_exports = ["sldprt"]
            unsupported_exports: list[str] = []
            if export_formats:
                normalized = [str(item).strip().lower() for item in export_formats]
                if "step" in normalized:
                    step_path = self._fresh_output_path(output_dir / f"{path.stem}.STEP")
                    if self._save_as(model, step_path, sw=sw):
                        artifacts.append(str(step_path))
                        completed_exports.append("step")
                    else:
                        unsupported_exports.append("step")

            live_tree_after = self._collect_feature_tree(model, include_objects=False)
            summary_path = output_dir / "native_edit_summary.json"
            result = {
                "ok": True,
                "backend": self.name,
                "operation": operation,
                "requested_file": str(path),
                "output_dir": str(output_dir),
                "artifacts": artifacts,
                "completed_exports": completed_exports,
                "unsupported_exports": sorted(set(unsupported_exports)),
                "warnings": warnings_list,
                "errors": [],
                "metadata": {
                    "solidworks_revision": str(sw.RevisionNumber),
                    "selector": selector,
                    "matched_feature_before": self._serializable_feature_rows([selected])[0],
                    "native_feature_tree_before": {
                        "version": "solidworks_feature_tree.v1",
                        "feature_count": len(live_tree_before),
                        "features": self._serializable_feature_rows(live_tree_before),
                        "geometry": geometry_before,
                    },
                    "native_feature_tree_after": {
                        "version": "solidworks_feature_tree.v1",
                        "feature_count": len(live_tree_after),
                        "features": self._serializable_feature_rows(live_tree_after),
                        "geometry": geometry_after,
                    },
                    "feature_plan_sync": "stale_after_native_tree_edit",
                },
            }
            if dimension_change is not None:
                result["metadata"]["dimension_change"] = dimension_change
                result["metadata"]["dimension_changes"] = dimension_changes
                if sync_info is not None:
                    result["metadata"]["feature_plan_sync_info"] = sync_info
            summary_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            result["summary_path"] = str(summary_path)
            return result
        finally:
            if opened_title:
                try:
                    sw.CloseDoc(opened_title)
                except Exception:
                    pass

    @staticmethod
    def _solidworks_stage_root() -> Path:
        candidates: list[Path] = []
        env_dir = os.environ.get("VIBECADING_SW_STAGE_DIR")
        if env_dir:
            candidates.append(Path(env_dir))
        candidates.append(SolidWorksComAdapter.server_root.parent / "outputs" / ".solidworks-stage")
        candidates.append(Path(tempfile.gettempdir()) / "VibeCadingSolidWorks")
        candidates.append(Path("D:/SW"))

        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application\CLSID") as key:
                clsid, _ = winreg.QueryValueEx(key, None)
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, fr"CLSID\{clsid}\LocalServer32") as key:
                local_server, _ = winreg.QueryValueEx(key, None)
            match = re.search(r'"([^"]+SLDWORKS\.exe)"|(\S+SLDWORKS\.exe)', str(local_server), re.IGNORECASE)
            if match:
                executable = Path(match.group(1) or match.group(2)).resolve()
                candidates.append(executable.parent.parent)
        except Exception:
            pass

        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / "_vibecading_write_probe.tmp"
                probe.write_text("ok", encoding="ascii")
                probe.unlink()
                return candidate
            except Exception:
                continue
        return Path(tempfile.gettempdir())

    @classmethod
    def _stage_save_path(cls, target_path: Path) -> Path:
        stage_root = cls._solidworks_stage_root()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_suffix = target_path.suffix.upper()
        return stage_root / f"_vibecading_stage_{timestamp}{safe_suffix}"

    @staticmethod
    def _path_ok(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    @staticmethod
    def _wait_for_path_ok(path: Path, timeout: float = 8.0) -> bool:
        deadline = time.time() + timeout
        last_size = -1
        stable_seen = 0
        while time.time() < deadline:
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            if size > 0:
                if size == last_size:
                    stable_seen += 1
                    if stable_seen >= 2:
                        return True
                else:
                    stable_seen = 0
                last_size = size
            time.sleep(0.25)
        return SolidWorksComAdapter._path_ok(path)

    @staticmethod
    def _byref_int(initial: int = 0):
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]

        return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, initial)

    @staticmethod
    def _variant_value(value) -> int | None:
        try:
            return int(value.value)
        except Exception:
            try:
                return int(value)
            except Exception:
                return None

    @staticmethod
    def _save_attempt_report(method: str, result, errors, warnings, path: Path, exception: Exception | None = None) -> dict[str, object]:
        if isinstance(result, tuple):
            ok = bool(result[0]) if result else False
        else:
            ok = bool(result)
        report: dict[str, object] = {
            "method": method,
            "ok": ok,
            "errors": SolidWorksComAdapter._variant_value(errors),
            "warnings": SolidWorksComAdapter._variant_value(warnings),
            "path": str(path),
            "file_ok": SolidWorksComAdapter._path_ok(path),
            "file_size": path.stat().st_size if path.exists() else 0,
        }
        if exception is not None:
            report["exception"] = repr(exception)
        return report

    @staticmethod
    def _try_save_call(method: str, call, path: Path) -> tuple[bool, dict[str, object]]:
        errors = SolidWorksComAdapter._byref_int()
        warnings = SolidWorksComAdapter._byref_int()
        try:
            result = call(errors, warnings)
            file_ok = SolidWorksComAdapter._wait_for_path_ok(path)
            report = SolidWorksComAdapter._save_attempt_report(method, result, errors, warnings, path)
            report["file_ok"] = file_ok
            report["file_size"] = path.stat().st_size if path.exists() else 0
            return bool(result) and file_ok and SolidWorksComAdapter._variant_value(errors) in (0, None), report
        except Exception as exc:
            return False, SolidWorksComAdapter._save_attempt_report(method, False, errors, warnings, path, exc)

    @staticmethod
    def _save_as_via_ui(sw, path: Path) -> bool:
        # UI keystroke fallback is intentionally kept disabled for the mainline.
        # It is not an officially supported API path, it is hard to make deterministic,
        # and after SolidWorks enters a bad state it can amplify instability instead of
        # recovering the save operation.
        return False

    @staticmethod
    def _legacy_save_as_via_ui(sw, path: Path) -> bool:
        try:
            import win32clipboard  # type: ignore[import-not-found]
            import win32con  # type: ignore[import-not-found]
            import win32gui  # type: ignore[import-not-found]
            import win32com.client  # type: ignore[import-not-found]
        except Exception:
            return False

        hwnd = None
        try:
            frame = sw.Frame()
            hwnd = frame.GetHWnd()
        except Exception:
            hwnd = None

        try:
            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

        shell = win32com.client.Dispatch("WScript.Shell")
        try:
            if hwnd:
                shell.AppActivate(hwnd)
        except Exception:
            pass

        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(str(path), win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            return False

        for shortcut in ["^+s", "{F12}", "%fa"]:
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
            shell.SendKeys(shortcut)
            time.sleep(1.5)
            shell.SendKeys("^v")
            time.sleep(0.5)
            shell.SendKeys("{ENTER}")

            deadline = time.time() + 8.0
            while time.time() < deadline:
                if SolidWorksComAdapter._path_ok(path):
                    return True
                time.sleep(0.5)
        return False

    @staticmethod
    def _fresh_output_path(path: Path) -> Path:
        if path.exists():
            try:
                path.unlink()
            except OSError:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                return path.with_name(f"{path.stem}_{stamp}{path.suffix}")
        return path

    @staticmethod
    def _save_as(model, path: Path, *, sw=None) -> bool:
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        save_reports: list[dict[str, object]] = []
        SolidWorksComAdapter._last_save_report = save_reports
        before_mtime = path.stat().st_mtime_ns if path.exists() else None
        try:
            model.ClearSelection2(True)
        except Exception:
            pass
        try:
            model.EditRebuild3()
        except Exception:
            pass

        stage_path = SolidWorksComAdapter._stage_save_path(path)
        try:
            if stage_path.exists():
                stage_path.unlink()
        except Exception:
            pass
        stage_saved = False
        extension = None
        try:
            extension = model.Extension
        except Exception:
            extension = None

        # Keep the mainline on the narrowest SolidWorks save path we can actually
        # validate in this Python COM environment. Broader fallback chains add more
        # COM surface area and have repeatedly made failure modes harder to control.
        save_calls = [
            ("ModelDoc2.SaveAs4", lambda errors, warnings: model.SaveAs4(str(stage_path), 0, 1, errors, warnings)),
            ("ModelDoc2.SaveAs3", lambda errors, warnings: model.SaveAs3(str(stage_path), 0, 1)),
        ]
        for method, save_call in save_calls:
            ok, report = SolidWorksComAdapter._try_save_call(method, save_call, stage_path)
            save_reports.append(report)
            if ok:
                stage_saved = True
                break

        if not stage_saved:
            try:
                if stage_path.exists() and stage_path.stat().st_size == 0:
                    stage_path.unlink()
            except Exception:
                pass
            return False
        try:
            save_errors = SolidWorksComAdapter._byref_int()
            save_warnings = SolidWorksComAdapter._byref_int()
            result = model.Save3(1, save_errors, save_warnings)
            save_reports.append(
                SolidWorksComAdapter._save_attempt_report(
                    "ModelDoc2.Save3.after_save_as",
                    result,
                    save_errors,
                    save_warnings,
                    stage_path,
                )
            )
        except Exception as exc:
            save_reports.append(
                {
                    "method": "ModelDoc2.Save3.after_save_as",
                    "ok": False,
                    "path": str(stage_path),
                    "exception": repr(exc),
                    "file_ok": SolidWorksComAdapter._path_ok(stage_path),
                    "file_size": stage_path.stat().st_size if stage_path.exists() else 0,
                }
            )
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        shutil.copy2(stage_path, path)
        try:
            stage_path.unlink()
        except Exception:
            pass
        if not SolidWorksComAdapter._path_ok(path):
            try:
                if stage_path.exists() and stage_path.stat().st_size == 0:
                    stage_path.unlink()
            except Exception:
                pass
            return False
        if before_mtime is None:
            return True
        return path.stat().st_mtime_ns > before_mtime

    def run_mounting_plate(self, job: CadJob, output_dir: Path) -> BackendResult:
        # Legacy compatibility wrapper. SolidWorks execution should converge on primitive_part.
        return self.run_primitive_part(compile_to_primitive_job(job), output_dir)

    def run_feature_part(self, job: CadJob, output_dir: Path) -> BackendResult:
        # Legacy compatibility wrapper. SolidWorks execution should converge on primitive_part.
        return self.run_primitive_part(compile_to_primitive_job(job), output_dir)

    def run_primitive_part(self, job: CadJob, output_dir: Path) -> BackendResult:
        primitive_job = compile_to_primitive_job(job)
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        part = primitive_job.part
        with self._solidworks_session():
            sw = self._connect(visible=True)
            template_path = self.find_part_template()

            try:
                model = sw.NewDocument(str(template_path), 0, 0, 0)
            except Exception as exc:
                raise self._solidworks_process_unstable_message("NewDocument", exc) from exc
            if model is None:
                raise BackendUnavailable(f"SolidWorks failed to create a part from template: {template_path}")
            created_doc_title = str(_maybe_call(model.GetTitle) or "")

            result = BackendResult(backend=self.name, ok=True)
            result.metadata["solidworks_revision"] = str(sw.RevisionNumber)
            result.metadata["part_template"] = str(template_path)

            try:
                spec_path = output_dir / "job_spec.json"
                spec_path.write_text(json.dumps(primitive_job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                result.add_artifact(spec_path)

                operation_reports = SolidWorksPrimitiveExecutor(sw, model).execute(part)
                result.metadata["primitive_operations"] = operation_reports
                try:
                    result.metadata["native_feature_tree"] = self.inspect_feature_tree(use_active_doc=True, visible=True)
                except Exception as exc:
                    result.warnings.append(f"SolidWorks native feature-tree inspection failed: {exc}")

                sldprt_path = self._fresh_output_path(output_dir / f"{part.name}.SLDPRT")
                if not self._save_as(model, sldprt_path, sw=sw):
                    attempts = json.dumps(self._last_save_report[-4:], ensure_ascii=False)
                    raise BackendUnavailable(
                        f"SolidWorks failed to save part file: {sldprt_path}; "
                        f"job_id={job.job_id}; backend={self.name}; save_attempts={attempts}"
                    )
                result.add_artifact(sldprt_path)

                completed_exports = ["sldprt"]
                if "json" in part.export_formats:
                    completed_exports.append("json")
                unsupported_exports: list[str] = []

                if "step" in part.export_formats:
                    step_path = self._fresh_output_path(output_dir / f"{part.name}.STEP")
                    if self._save_as(model, step_path, sw=sw):
                        result.add_artifact(step_path)
                        completed_exports.append("step")
                    else:
                        result.warnings.append("SolidWorks did not export STEP successfully.")
                        unsupported_exports.append("step")

                if "stl" in part.export_formats:
                    stl_path = self._fresh_output_path(output_dir / f"{part.name}.STL")
                    if self._save_as(model, stl_path, sw=sw):
                        result.add_artifact(stl_path)
                        completed_exports.append("stl")
                    else:
                        result.warnings.append("SolidWorks did not export STL successfully.")
                        unsupported_exports.append("stl")

                if "svg" in part.export_formats:
                    svg_path = output_dir / f"{part.name}_primitive.svg"
                    write_primitive_part_svg(primitive_job, svg_path)
                    result.add_artifact(svg_path)
                    completed_exports.append("svg")

                if "pdf" in part.export_formats:
                    pdf_path = output_dir / f"{part.name}_report.pdf"
                    write_primitive_part_report_pdf(
                        primitive_job,
                        pdf_path,
                        backend=self.name,
                        generated_step="step" in completed_exports,
                    )
                    result.add_artifact(pdf_path)
                    completed_exports.append("pdf")

                for export_format in part.export_formats:
                    if export_format not in {"json", "pdf", "svg", "step", "stl"}:
                        result.warnings.append(f"SolidWorks adapter does not support {export_format.upper()} export yet.")
                        unsupported_exports.append(export_format)

                bounds = primitive_bounds(part)
                primitive_types = [operation.type for operation in part.operations]
                result.metadata.update(
                    {
                        "source_kind": part.source_kind,
                        "operation_count": len(part.operations),
                        "primitive_operation_types": primitive_types,
                        "bounding_box": {
                            "length": bounds["length"],
                            "width": bounds["width"],
                            "thickness": bounds["depth"],
                            "units": primitive_job.units,
                        },
                        "hole_count": primitive_hole_count(part),
                        "engineering_hole_callouts": primitive_engineering_hole_callouts(part),
                        "drawing_annotation_plan": primitive_drawing_annotation_plan(part),
                        "completed_exports": completed_exports,
                        "unsupported_exports": sorted(set(unsupported_exports)),
                    }
                )
                return result
            finally:
                if created_doc_title:
                    try:
                        sw.CloseDoc(created_doc_title)
                    except Exception as exc:
                        result.warnings.append(f"SolidWorks failed to close created document: {created_doc_title}; detail={exc}")
