from __future__ import annotations

import copy
from typing import Any

from core.edit_planner import EDIT_DSL_VERSION
from core.feature_plan import compile_feature_plan_to_primitive_job


SUPPORTED_EDIT_DSL_MODES = {"new_part", "rebuild_from_context"}
SUPPORTED_EDIT_OPERATIONS = {
    "update_parameters",
    "append_feature",
    "replace_feature",
    "local_rebuild",
    "rebuild_revision",
}


def validate_edit_dsl(edit_dsl: dict[str, Any]) -> None:
    if not isinstance(edit_dsl, dict):
        raise ValueError("edit_part DSL must be an object.")
    if str(edit_dsl.get("version", "")) != EDIT_DSL_VERSION:
        raise ValueError(f"Unsupported edit_part DSL version: {edit_dsl.get('version')}.")
    mode = str(edit_dsl.get("mode", ""))
    if mode not in SUPPORTED_EDIT_DSL_MODES:
        raise ValueError(f"Unsupported edit_part DSL mode: {mode}.")
    operations = edit_dsl.get("operations", [])
    if not isinstance(operations, list):
        raise ValueError("edit_part DSL operations must be a list.")
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValueError(f"edit_part DSL operations[{index}] must be an object.")
        operation_type = str(operation.get("type", ""))
        if operation_type not in SUPPORTED_EDIT_OPERATIONS:
            raise ValueError(f"Unsupported edit_part operation type: {operation_type}.")
        if operation_type == "update_parameters":
            if operation.get("target_scope") not in {"part", "feature"}:
                raise ValueError("update_parameters requires target_scope part or feature.")
            if not isinstance(operation.get("parameters"), dict) or not operation["parameters"]:
                raise ValueError("update_parameters requires non-empty parameters.")
        elif operation_type == "append_feature":
            if operation.get("target_scope") != "feature_append":
                raise ValueError("append_feature requires target_scope=feature_append.")
        elif operation_type == "replace_feature":
            if operation.get("target_scope") != "feature":
                raise ValueError("replace_feature requires target_scope=feature.")
            if not isinstance(operation.get("target_feature_selector"), dict):
                raise ValueError("replace_feature requires target_feature_selector.")
            if not isinstance(operation.get("replacement_feature"), dict):
                raise ValueError("replace_feature requires replacement_feature.")
            compatibility = operation.get("replacement_compatibility")
            if not isinstance(compatibility, dict):
                raise ValueError("replace_feature requires replacement_compatibility.")
            classification = str(compatibility.get("classification", ""))
            if classification not in {"same_manufacturing_semantic_replacement", "cross_modeling_family_replacement", "mixed_semantic_replacement"}:
                raise ValueError("replace_feature replacement_compatibility.classification is not supported.")
            if classification == "cross_modeling_family_replacement" and not bool(compatibility.get("requires_manual_confirmation", False)):
                raise ValueError("cross_modeling_family_replacement must require manual confirmation.")
            boundary = operation.get("boundary")
            if not isinstance(boundary, dict):
                raise ValueError("replace_feature requires structured boundary metadata.")
            if str(boundary.get("edit_scope", "")) != "single_feature_replacement":
                raise ValueError("replace_feature boundary.edit_scope is not supported.")
            dependency_summary = boundary.get("dependency_summary")
            if not isinstance(dependency_summary, dict):
                raise ValueError("replace_feature requires dependency_summary inside boundary.")
            if not bool(dependency_summary.get("affects_host_features", False)):
                raise ValueError("replace_feature dependency_summary must mark host-feature impact.")
            for key in [
                "host_feature_selectors",
                "affects_same_plane_derived_features",
                "same_plane_derived_feature_selectors",
                "affects_downstream_subtractive_features",
                "downstream_feature_selectors",
                "affects_base_body",
                "rebuild_entry_nodes",
            ]:
                if key not in dependency_summary:
                    raise ValueError(f"replace_feature dependency_summary missing {key}.")
            preflight = operation.get("preflight")
            if not isinstance(preflight, dict):
                raise ValueError("replace_feature requires structured preflight metadata.")
            if not bool(preflight.get("requires_unique_target_feature_selector", False)):
                raise ValueError("replace_feature preflight must require a unique target selector.")
            if not bool(preflight.get("requires_compile_ready_replacement_feature", False)):
                raise ValueError("replace_feature replacement feature is not compile-ready.")
            if not bool(preflight.get("requires_supported_replacement_family", False)):
                raise ValueError("replace_feature replacement family is not marked supported.")
            if not bool(preflight.get("supported_transition_for_execution", False)):
                raise ValueError("replace_feature transition is not supported for execution.")
            minimum_confidence = float(preflight.get("minimum_match_confidence", 0.75))
            current_confidence = float(operation.get("match_confidence", preflight.get("current_match_confidence", 0.0)))
            if current_confidence < minimum_confidence:
                raise ValueError("replace_feature match confidence is below the execution threshold.")
        elif operation_type == "local_rebuild":
            if operation.get("target_scope") != "dependency_chain":
                raise ValueError("local_rebuild requires target_scope=dependency_chain.")
            affected = operation.get("affected_feature_selectors")
            if not isinstance(affected, list) or not affected:
                raise ValueError("local_rebuild requires non-empty affected_feature_selectors.")
            boundary = operation.get("boundary")
            if not isinstance(boundary, dict):
                raise ValueError("local_rebuild requires structured boundary metadata.")
            if str(boundary.get("rebuild_scope", "")) != "affected_feature_dependency_chain":
                raise ValueError("local_rebuild boundary.rebuild_scope is not supported.")
            if str(boundary.get("executor_scope", "")) != "recompile_feature_plan_then_rebuild_revision":
                raise ValueError("local_rebuild boundary.executor_scope is not supported.")
            dependency_summary = boundary.get("dependency_summary")
            if not isinstance(dependency_summary, dict):
                raise ValueError("local_rebuild requires dependency_summary inside boundary.")
            for key in [
                "affects_host_features",
                "host_feature_selectors",
                "affects_same_plane_derived_features",
                "same_plane_derived_feature_selectors",
                "affects_downstream_subtractive_features",
                "downstream_feature_selectors",
                "affects_base_body",
                "rebuild_entry_nodes",
            ]:
                if key not in dependency_summary:
                    raise ValueError(f"local_rebuild dependency_summary missing {key}.")
            preflight = operation.get("preflight")
            if not isinstance(preflight, dict):
                raise ValueError("local_rebuild requires structured preflight metadata.")
            if not bool(preflight.get("requires_affected_feature_selectors", False)):
                raise ValueError("local_rebuild preflight must require affected feature selectors.")
            if not bool(preflight.get("requires_revision_output", False)):
                raise ValueError("local_rebuild preflight must require revision output.")
            if not bool(preflight.get("requires_feature_plan_recompile", False)):
                raise ValueError("local_rebuild preflight must require feature-plan recompile.")
            if int(preflight.get("affected_feature_count", 0)) < 1:
                raise ValueError("local_rebuild preflight affected_feature_count must be positive.")
        elif operation_type == "rebuild_revision":
            if "revision_index" not in operation:
                raise ValueError("rebuild_revision requires revision_index.")
    if mode == "rebuild_from_context" and operations:
        if str(operations[-1].get("type", "")) != "rebuild_revision":
            raise ValueError("rebuild_from_context edit_part DSL must end with rebuild_revision.")


def _feature_matches_selector(feature: dict[str, Any], selector: dict[str, Any]) -> bool:
    if not isinstance(selector, dict):
        return False
    for key in ["id", "kind", "functional_role", "method"]:
        expected = str(selector.get(key, "")).strip()
        if expected and str(feature.get(key, "")).strip() != expected:
            return False
    return True


def _find_feature_index(features: list[dict[str, Any]], selector: dict[str, Any]) -> int | None:
    matches = [index for index, feature in enumerate(features) if _feature_matches_selector(feature, selector)]
    if len(matches) == 1:
        return matches[0]
    return None


def _merge_parameters(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(existing)
    for key, value in updates.items():
        if isinstance(value, dict):
            base = dict(merged.get(key, {})) if isinstance(merged.get(key), dict) else {}
            merged[key] = _merge_parameters(base, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_engineering_context(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(previous)
    for key, value in current.items():
        if isinstance(value, list):
            merged[key] = list(dict.fromkeys([*(merged.get(key, []) or []), *value]))
        elif value not in (None, "", {}, []):
            merged[key] = copy.deepcopy(value)
    return merged


def _ensure_unique_feature_ids(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    unique: list[dict[str, Any]] = []
    for feature in features:
        copied = copy.deepcopy(feature)
        base_id = str(copied.get("id", "feature"))
        counts[base_id] = counts.get(base_id, 0) + 1
        if counts[base_id] > 1:
            copied["id"] = f"{base_id}_{counts[base_id]}"
        unique.append(copied)
    return unique


def apply_edit_dsl_to_feature_plan(
    *,
    edit_dsl: dict[str, Any],
    existing_feature_plan: dict[str, Any] | None,
    requested_feature_plan: dict[str, Any],
) -> dict[str, Any]:
    validate_edit_dsl(edit_dsl)
    if not existing_feature_plan or str(edit_dsl.get("mode", "")) == "new_part":
        return copy.deepcopy(requested_feature_plan)

    updated = copy.deepcopy(existing_feature_plan)
    requested = copy.deepcopy(requested_feature_plan)
    existing_features = list(updated.get("features", []))
    requested_features = list(requested.get("features", []))
    requested_base = requested_features[0] if requested_features and str(requested_features[0].get("kind", "")) == "base_body" else None
    if requested_base is not None:
        requested_features = requested_features[1:]

    if requested_base is not None:
        base_index = _find_feature_index(existing_features, {"kind": "base_body"})
        if base_index is None:
            existing_features.insert(0, requested_base)
        else:
            merged_base = copy.deepcopy(existing_features[base_index])
            merged_base["parameters"] = _merge_parameters(
                dict(merged_base.get("parameters", {})),
                dict(requested_base.get("parameters", {})),
            )
            if isinstance(requested_base.get("references"), dict):
                merged_base["references"] = _merge_parameters(
                    dict(merged_base.get("references", {})),
                    dict(requested_base.get("references", {})),
                )
            existing_features[base_index] = merged_base

    requested_lookup = {
        str(feature.get("id", "")): feature
        for feature in requested_features
    }

    for operation in edit_dsl.get("operations", []):
        op_type = str(operation.get("type", ""))
        if op_type == "update_parameters":
            if str(operation.get("target_scope", "")) == "part":
                updated["parameters"] = _merge_parameters(
                    dict(updated.get("parameters", {})),
                    dict(operation.get("parameters", {})),
                )
                continue
            selector = dict(operation.get("target_feature_selector", {}))
            feature_index = _find_feature_index(existing_features, selector)
            if feature_index is None:
                raise ValueError(f"edit_part update_parameters could not uniquely match feature selector: {selector}")
            existing_features[feature_index]["parameters"] = _merge_parameters(
                dict(existing_features[feature_index].get("parameters", {})),
                dict(operation.get("parameters", {})),
            )
        elif op_type == "append_feature":
            selector = dict(operation.get("feature_selector", {}))
            feature_id = str(selector.get("id", ""))
            feature = requested_lookup.get(feature_id)
            if feature is None:
                raise ValueError(f"edit_part append_feature could not find requested feature: {selector}")
            existing_features.append(copy.deepcopy(feature))
        elif op_type == "replace_feature":
            selector = dict(operation.get("target_feature_selector", {}))
            feature_index = _find_feature_index(existing_features, selector)
            if feature_index is None:
                raise ValueError(f"edit_part replace_feature could not uniquely match feature selector: {selector}")
            replacement_selector = dict(operation.get("replacement_feature", {}))
            replacement_id = str(replacement_selector.get("id", ""))
            replacement_feature = requested_lookup.get(replacement_id)
            if replacement_feature is None:
                raise ValueError(f"edit_part replace_feature could not find replacement feature: {replacement_selector}")
            existing_features[feature_index] = copy.deepcopy(replacement_feature)
        elif op_type in {"local_rebuild", "rebuild_revision"}:
            continue

    updated["features"] = _ensure_unique_feature_ids(existing_features)
    updated["request"] = str(requested.get("request", updated.get("request", "")))
    updated["strategy"] = copy.deepcopy(requested.get("strategy", updated.get("strategy", {})))
    updated["engineering_context"] = _merge_engineering_context(
        dict(updated.get("engineering_context", {})),
        dict(requested.get("engineering_context", {})),
    )
    updated["questions"] = list(requested.get("questions", []))
    updated["warnings"] = list(requested.get("warnings", []))
    updated["missing_capabilities"] = list(requested.get("missing_capabilities", []))
    updated["parameters"] = _merge_parameters(
        dict(updated.get("parameters", {})),
        dict(requested.get("parameters", {})),
    )
    assumptions = list(updated.get("engineering_context", {}).get("semantic_assumptions", []))
    updated.setdefault("engineering_context", {})["semantic_assumptions"] = list(
        dict.fromkeys([*assumptions, "rebuild_from_existing_part_context"])
    )
    return updated


def compile_edit_dsl_to_job(
    *,
    edit_dsl: dict[str, Any],
    feature_plan: dict[str, Any],
    job_id: str,
    part_name: str,
    material: str,
    export_formats: list[str],
) -> dict[str, Any]:
    validate_edit_dsl(edit_dsl)
    return compile_feature_plan_to_primitive_job(
        feature_plan,
        job_id=job_id,
        part_name=part_name,
        material=material,
        export_formats=export_formats,
    )
