from __future__ import annotations

import copy
from typing import Any


EDIT_PLAN_VERSION = "edit_plan.v1"
EDIT_DSL_VERSION = "edit_part.v1"

SUPPORTED_REPLACEMENT_FAMILIES = {
    "prismatic_additive",
    "prismatic_subtractive",
    "rotational_base",
    "rotational_subtractive",
}

SUPPORTED_REPLACEMENT_SIGNATURE_TRANSITIONS: dict[tuple[tuple[str, str], tuple[str, str]], str] = {
    (("slot_or_pocket", "cut_extrude"), ("slot_or_pocket", "cut_extrude")): "direct_supported_rebuild",
    (("obround_slot", "cut_extrude"), ("obround_slot", "cut_extrude")): "direct_supported_rebuild",
    (("hole", "cut_extrude"), ("hole", "cut_extrude")): "direct_supported_rebuild",
    (("hole_pattern", "cut_extrude"), ("hole_pattern", "cut_extrude")): "direct_supported_rebuild",
    (("threaded_hole", "cut_extrude"), ("threaded_hole", "cut_extrude")): "direct_supported_rebuild",
    (("countersink", "cut_extrude"), ("countersink", "cut_extrude")): "direct_supported_rebuild",
    (("counterbore", "cut_extrude"), ("counterbore", "cut_extrude")): "direct_supported_rebuild",
    (("boss", "extrude"), ("boss", "extrude")): "direct_supported_rebuild",
    (("rib", "rib_or_extrude"), ("rib", "rib_or_extrude")): "direct_supported_rebuild",
    (("base_body", "extrude"), ("base_body", "extrude")): "direct_supported_rebuild",
    (("base_body", "revolve"), ("base_body", "revolve")): "direct_supported_rebuild",
    (("hole", "cut_revolve"), ("hole", "cut_revolve")): "direct_supported_rebuild",
    (("groove", "cut_revolve"), ("groove", "cut_revolve")): "direct_supported_rebuild",
    (("slot_or_pocket", "cut_extrude"), ("obround_slot", "cut_extrude")): "supported_with_manual_confirmation",
    (("obround_slot", "cut_extrude"), ("slot_or_pocket", "cut_extrude")): "supported_with_manual_confirmation",
}


def _feature_selector(feature: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(feature.get("id", "")),
        "kind": str(feature.get("kind", "")),
        "functional_role": str(feature.get("functional_role", "")),
        "method": str(feature.get("method", "")),
    }


def _parameter_selectors(parameters: dict[str, Any], prefix: list[str] | None = None) -> list[dict[str, Any]]:
    path_prefix = list(prefix or [])
    selectors: list[dict[str, Any]] = []
    for key, value in parameters.items():
        current_path = [*path_prefix, str(key)]
        if isinstance(value, dict):
            selectors.extend(_parameter_selectors(value, current_path))
        else:
            selectors.append(
                {
                    "parameter_path": current_path,
                    "value": copy.deepcopy(value),
                }
            )
    return selectors


def _host_reference(feature: dict[str, Any]) -> dict[str, Any] | None:
    references = dict(feature.get("references", {}))
    resolved_target = references.get("resolved_target")
    if isinstance(resolved_target, dict) and resolved_target:
        return copy.deepcopy(resolved_target)
    original_target = references.get("original_target_reference")
    if isinstance(original_target, dict) and original_target:
        return copy.deepcopy(original_target)
    return None


def _host_feature_selector(feature: dict[str, Any]) -> dict[str, Any] | None:
    references = dict(feature.get("references", {}))
    selector = references.get("host_feature_selector")
    if isinstance(selector, dict) and selector:
        return copy.deepcopy(selector)
    return None


def _matching_previous_feature(previous_features: list[dict[str, Any]], feature: dict[str, Any]) -> dict[str, Any] | None:
    selector = _feature_selector(feature)
    matches = [
        item
        for item in previous_features
        if str(item.get("kind", "")) == selector["kind"]
        and str(item.get("functional_role", "")) == selector["functional_role"]
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _matching_previous_feature_by_role(previous_features: list[dict[str, Any]], feature: dict[str, Any]) -> dict[str, Any] | None:
    functional_role = str(feature.get("functional_role", ""))
    if not functional_role:
        return None
    matches = [
        item
        for item in previous_features
        if str(item.get("functional_role", "")) == functional_role
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _changed_value(new_value: Any, old_value: Any) -> bool:
    if isinstance(new_value, float | int) and isinstance(old_value, float | int):
        return abs(float(new_value) - float(old_value)) > 1e-9
    return new_value != old_value


def _parameter_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for key, value in current.items():
        if isinstance(value, dict):
            previous_value = previous.get(key, {})
            if isinstance(previous_value, dict):
                nested = _parameter_diff(previous_value, value)
                if nested:
                    diff[key] = nested
            elif _changed_value(value, previous_value):
                diff[key] = copy.deepcopy(value)
        elif isinstance(value, list):
            if _changed_value(value, previous.get(key)):
                diff[key] = copy.deepcopy(value)
        elif _changed_value(value, previous.get(key)):
            diff[key] = value
    return diff


def _next_revision(existing_part_context: dict[str, Any] | None) -> tuple[int, str | None]:
    if not existing_part_context:
        return 1, None
    previous_revision = int(existing_part_context.get("revision_index", 1))
    previous_job_id = str(existing_part_context.get("job_id", "")).strip() or None
    return previous_revision + 1, previous_job_id


def _suggested_revision_job_id(existing_part_context: dict[str, Any] | None) -> str | None:
    if not existing_part_context:
        return None
    revision_index, previous_job_id = _next_revision(existing_part_context)
    if not previous_job_id:
        return None
    return f"{previous_job_id}-r{revision_index}"


def _part_parameter_updates_affect_base_body(parameter_updates: dict[str, Any]) -> bool:
    base_shape_keys = {
        "length",
        "width",
        "thickness",
        "total_length",
        "outer_diameter",
        "left_diameter",
        "left_length",
        "right_diameter",
        "right_length",
    }
    return any(key in parameter_updates for key in base_shape_keys)


def _selector_confidence(previous_feature: dict[str, Any] | None, current_feature: dict[str, Any] | None) -> float:
    if not previous_feature or not current_feature:
        return 0.0
    same_kind = str(previous_feature.get("kind", "")) == str(current_feature.get("kind", ""))
    same_role = str(previous_feature.get("functional_role", "")) == str(current_feature.get("functional_role", ""))
    if same_kind and same_role:
        return 0.95
    if same_role:
        return 0.82
    if same_kind:
        return 0.68
    return 0.4


def _selector_strategy(previous_feature: dict[str, Any] | None, current_feature: dict[str, Any] | None) -> str:
    if not previous_feature or not current_feature:
        return "unmatched"
    same_kind = str(previous_feature.get("kind", "")) == str(current_feature.get("kind", ""))
    same_role = str(previous_feature.get("functional_role", "")) == str(current_feature.get("functional_role", ""))
    same_id = str(previous_feature.get("id", "")) and str(previous_feature.get("id", "")) == str(current_feature.get("id", ""))
    if same_kind and (same_role or same_id):
        return "kind_and_functional_role"
    if same_role:
        return "functional_role_only"
    if same_kind:
        return "kind_only"
    return "manual_alignment_required"


def _modeling_family(feature: dict[str, Any]) -> str:
    kind = str(feature.get("kind", "")).lower()
    method = str(feature.get("method", "")).lower()
    if method in {"extrude", "cut_extrude", "hole_wizard", "rib_or_extrude"}:
        return "prismatic"
    if method in {"revolve", "cut_revolve"}:
        return "rotational"
    if method in {"sweep", "cut_sweep"}:
        return "path_driven"
    if method in {"loft", "cut_loft"} or "loft" in kind:
        return "multi_section_transition"
    if "face" in str(feature.get("sketch_strategy", {}).get("type", "")).lower():
        return "face_derived_prismatic"
    return "generic"


def _compile_signature(feature: dict[str, Any]) -> tuple[str, str]:
    return (
        str(feature.get("kind", "")).lower(),
        str(feature.get("method", "")).lower(),
    )


def _supported_replacement_family(feature: dict[str, Any]) -> str:
    kind = str(feature.get("kind", "")).lower()
    method = str(feature.get("method", "")).lower()
    if kind == "base_body" and method == "extrude":
        return "prismatic_additive"
    if kind in {"boss", "rib"} and method in {"extrude", "rib_or_extrude"}:
        return "prismatic_additive"
    if kind in {"hole", "hole_pattern", "threaded_hole", "countersink", "counterbore", "slot_or_pocket", "obround_slot"} and method in {"cut_extrude", "hole_wizard"}:
        return "prismatic_subtractive"
    if kind == "base_body" and method == "revolve":
        return "rotational_base"
    if kind in {"hole", "groove"} and method == "cut_revolve":
        return "rotational_subtractive"
    return "unsupported"


def _manufacturing_semantic_group(feature: dict[str, Any]) -> str:
    kind = str(feature.get("kind", "")).lower()
    method = str(feature.get("method", "")).lower()
    if kind in {"hole", "hole_pattern", "threaded_hole", "countersink", "counterbore", "slot_or_pocket", "obround_slot", "groove"} or method.startswith("cut_") or method == "hole_wizard":
        return "subtractive"
    if kind in {"boss", "rib", "base_body"} or method in {"extrude", "revolve", "sweep", "loft"}:
        return "additive"
    return "neutral"


def _replace_compatibility(previous_feature: dict[str, Any], current_feature: dict[str, Any]) -> dict[str, Any]:
    previous_family = _modeling_family(previous_feature)
    current_family = _modeling_family(current_feature)
    previous_semantic = _manufacturing_semantic_group(previous_feature)
    current_semantic = _manufacturing_semantic_group(current_feature)
    if previous_semantic == current_semantic:
        classification = "same_manufacturing_semantic_replacement"
    elif previous_family != current_family:
        classification = "cross_modeling_family_replacement"
    else:
        classification = "mixed_semantic_replacement"
    previous_supported_family = _supported_replacement_family(previous_feature)
    replacement_supported_family = _supported_replacement_family(current_feature)
    previous_signature = _compile_signature(previous_feature)
    replacement_signature = _compile_signature(current_feature)
    replacement_family_supported = (
        previous_supported_family in SUPPORTED_REPLACEMENT_FAMILIES
        and replacement_supported_family in SUPPORTED_REPLACEMENT_FAMILIES
    )
    signature_transition_support = SUPPORTED_REPLACEMENT_SIGNATURE_TRANSITIONS.get(
        (previous_signature, replacement_signature)
    )
    if not replacement_family_supported:
        transition_support = "unsupported_in_current_compiler"
    elif signature_transition_support is not None:
        transition_support = signature_transition_support
    else:
        transition_support = "unsupported_transition_pair"
    return {
        "classification": classification,
        "previous_modeling_family": previous_family,
        "replacement_modeling_family": current_family,
        "previous_manufacturing_semantic": previous_semantic,
        "replacement_manufacturing_semantic": current_semantic,
        "previous_supported_family": previous_supported_family,
        "replacement_supported_family": replacement_supported_family,
        "previous_compile_signature": list(previous_signature),
        "replacement_compile_signature": list(replacement_signature),
        "transition_support": transition_support,
        "requires_manual_confirmation": classification == "cross_modeling_family_replacement" or transition_support == "supported_with_manual_confirmation",
    }


def _is_subtractive_feature(feature: dict[str, Any]) -> bool:
    return _manufacturing_semantic_group(feature) == "subtractive"


def _downstream_subtractive_features(previous_features: list[dict[str, Any]], selector: dict[str, Any]) -> list[dict[str, Any]]:
    feature = _matching_previous_feature(previous_features, selector) if selector else None
    if feature is None:
        matches = [item for item in previous_features if _feature_selector(item) == selector]
        feature = matches[0] if len(matches) == 1 else None
    if feature is None:
        return []
    try:
        index = previous_features.index(feature)
    except ValueError:
        return []
    downstream = [
        _feature_selector(item)
        for item in previous_features[index + 1 :]
        if _is_subtractive_feature(item)
    ]
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in downstream:
        key = (
            str(item.get("id", "")),
            str(item.get("kind", "")),
            str(item.get("functional_role", "")),
            str(item.get("method", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _same_plane_derived_features(
    previous_features: list[dict[str, Any]],
    *,
    host_reference: dict[str, Any] | None = None,
    host_selector: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not host_reference and not host_selector:
        return []
    matches: list[dict[str, Any]] = []
    host_signature = None
    if isinstance(host_reference, dict):
        host_signature = (
            str(host_reference.get("type", "")),
            str(host_reference.get("feature", "")),
            tuple(host_reference.get("normal", [])) if isinstance(host_reference.get("normal"), list) else (),
            str(host_reference.get("position", "")),
        )
    for feature in previous_features:
        references = dict(feature.get("references", {}))
        resolved_target = references.get("resolved_target")
        target_semantic = str(references.get("target_semantic", "")).strip()
        feature_host_selector = references.get("host_feature_selector")
        same_plane = False
        if isinstance(host_reference, dict) and isinstance(resolved_target, dict):
            candidate_signature = (
                str(resolved_target.get("type", "")),
                str(resolved_target.get("feature", "")),
                tuple(resolved_target.get("normal", [])) if isinstance(resolved_target.get("normal"), list) else (),
                str(resolved_target.get("position", "")),
            )
            if host_signature == candidate_signature:
                same_plane = True
        if not same_plane and isinstance(host_selector, dict) and isinstance(feature_host_selector, dict):
            same_plane = _feature_selector({"id": feature_host_selector.get("id", ""), "kind": feature_host_selector.get("kind", ""), "functional_role": feature_host_selector.get("functional_role", ""), "method": feature_host_selector.get("method", "")}) == _feature_selector({"id": host_selector.get("id", ""), "kind": host_selector.get("kind", ""), "functional_role": host_selector.get("functional_role", ""), "method": host_selector.get("method", "")})
        if not same_plane and isinstance(host_selector, dict) and target_semantic and str(host_selector.get("kind", "")) == "boss" and target_semantic == "boss_top_face":
            same_plane = True
        if same_plane:
            matches.append(_feature_selector(feature))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in matches:
        key = (
            str(item.get("id", "")),
            str(item.get("kind", "")),
            str(item.get("functional_role", "")),
            str(item.get("method", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _replace_feature_boundary(
    *,
    previous_feature: dict[str, Any],
    current_feature: dict[str, Any],
    previous_features: list[dict[str, Any]],
    selector_strategy: str,
    match_confidence: float,
) -> dict[str, Any]:
    target_selector = _feature_selector(previous_feature)
    downstream = _downstream_subtractive_features(previous_features, target_selector)
    host_reference = _host_reference(current_feature)
    host_selector = _host_feature_selector(current_feature)
    same_plane = _same_plane_derived_features(
        previous_features,
        host_reference=host_reference,
        host_selector=host_selector,
    )
    return {
        "edit_scope": "single_feature_replacement",
        "dependency_scope": "target_feature_and_downstream_dependents",
        "requires_rebuild_revision": True,
        "native_feature_tree_edit_supported": False,
        "replacement_intent": {
            "new_kind": str(current_feature.get("kind", "")),
            "new_method": str(current_feature.get("method", "")),
            "functional_role": str(current_feature.get("functional_role", "")),
        },
        "executor_scope": "recompile_feature_plan_then_rebuild_revision",
        "blocked_if": [
            "target_feature_selector_is_not_unique",
            "replacement_feature_has_unresolved_required_parameters",
            "replacement_feature_crosses_to_uncompiled_family",
            "replacement_match_confidence_below_threshold",
        ],
        "dependency_summary": {
            "affects_host_features": True,
            "host_feature_selectors": [target_selector],
            "affects_same_plane_derived_features": bool(same_plane),
            "same_plane_derived_feature_selectors": same_plane,
            "affects_downstream_subtractive_features": bool(downstream),
            "downstream_feature_selectors": downstream,
            "affects_base_body": str(previous_feature.get("kind", "")) == "base_body",
            "rebuild_entry_nodes": [target_selector],
        },
        "match_policy": {
            "selector_strategy": selector_strategy,
            "match_confidence": match_confidence,
        },
    }


def _replace_feature_preflight(
    *,
    current_feature: dict[str, Any],
    match_confidence: float,
    compatibility: dict[str, Any],
) -> dict[str, Any]:
    transition_support = str(compatibility.get("transition_support", "unsupported_in_current_compiler"))
    return {
        "requires_unique_target_feature_selector": True,
        "requires_compile_ready_replacement_feature": not bool(current_feature.get("required_parameters")),
        "requires_supported_replacement_family": transition_support not in {"unsupported_in_current_compiler", "unsupported_transition_pair"},
        "supported_transition_for_execution": transition_support in {"direct_supported_rebuild", "supported_with_manual_confirmation"},
        "manual_confirmation_required": bool(compatibility.get("requires_manual_confirmation", False)),
        "requires_revision_output": True,
        "minimum_match_confidence": 0.75,
        "current_match_confidence": match_confidence,
    }


def _local_rebuild_boundary(
    targets: list[dict[str, Any]],
    *,
    host_targets: list[dict[str, Any]],
    same_plane_targets: list[dict[str, Any]],
    downstream_targets: list[dict[str, Any]],
    affects_base_body: bool,
) -> dict[str, Any]:
    return {
        "rebuild_scope": "affected_feature_dependency_chain",
        "dependency_scope": "selected_features_and_downstream_dependents",
        "entry_feature_count": len(targets),
        "executor_scope": "recompile_feature_plan_then_rebuild_revision",
        "native_feature_tree_edit_supported": False,
        "stops_before": [
            "native_solidworks_feature_tree_in_place_edit",
            "partial_dependency_graph_rebuild_inside_existing_sldprt",
        ],
        "blocked_if": [
            "affected_feature_selectors_are_empty",
            "affected_feature_selectors_are_not_unique",
            "requested_revision_output_is_missing",
        ],
        "dependency_summary": {
            "affects_host_features": bool(host_targets),
            "host_feature_selectors": host_targets,
            "affects_same_plane_derived_features": bool(same_plane_targets),
            "same_plane_derived_feature_selectors": same_plane_targets,
            "affects_downstream_subtractive_features": bool(downstream_targets),
            "downstream_feature_selectors": downstream_targets,
            "affects_base_body": affects_base_body,
            "rebuild_entry_nodes": targets,
        },
    }


def _local_rebuild_preflight(targets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "requires_affected_feature_selectors": True,
        "requires_revision_output": True,
        "requires_feature_plan_recompile": True,
        "affected_feature_count": len(targets),
    }


def build_edit_plan(
    *,
    request: str,
    feature_plan: dict[str, Any],
    existing_part_context: dict[str, Any] | None,
) -> dict[str, Any]:
    previous_feature_plan = (
        copy.deepcopy(existing_part_context.get("feature_plan"))
        if existing_part_context and isinstance(existing_part_context.get("feature_plan"), dict)
        else None
    )
    revision_index, previous_job_id = _next_revision(existing_part_context)
    suggested_job_id = _suggested_revision_job_id(existing_part_context)

    if not previous_feature_plan:
        return {
            "version": EDIT_PLAN_VERSION,
            "mode": "new_part",
            "request": request,
            "source_context": None,
            "actions": [],
            "output_revision": {
                "creates_new_revision": False,
                "revision_index": 1,
                "parent_job_id": None,
                "suggested_job_id": None,
            },
            "questions": list(feature_plan.get("questions", [])),
            "warnings": list(feature_plan.get("warnings", [])),
        }

    actions: list[dict[str, Any]] = []
    local_rebuild_targets: list[dict[str, Any]] = []
    local_rebuild_host_targets: list[dict[str, Any]] = []
    local_rebuild_same_plane_targets: list[dict[str, Any]] = []
    local_rebuild_downstream_targets: list[dict[str, Any]] = []
    local_rebuild_affects_base_body = False
    previous_features = list(previous_feature_plan.get("features", []))
    current_features = list(feature_plan.get("features", []))

    previous_parameters = dict(previous_feature_plan.get("parameters", {}))
    current_parameters = dict(feature_plan.get("parameters", {}))
    parameter_updates = _parameter_diff(previous_parameters, current_parameters)
    if parameter_updates:
        actions.append(
            {
                "action": "update_parameters",
                "target_scope": "part",
                "parameters": parameter_updates,
                "parameter_selectors": _parameter_selectors(parameter_updates),
                "selector_strategy": "part_parameters",
                "match_confidence": 1.0,
            }
        )
        local_rebuild_affects_base_body = _part_parameter_updates_affect_base_body(parameter_updates)

    for current_feature in current_features:
        if str(current_feature.get("kind", "")) == "base_body":
            previous_feature = next(
                (item for item in previous_features if str(item.get("kind", "")) == "base_body"),
                None,
            )
        else:
            previous_feature = _matching_previous_feature(previous_features, current_feature)
        if previous_feature is None:
            role_match = _matching_previous_feature_by_role(previous_features, current_feature)
            if role_match is not None and str(role_match.get("kind", "")) != str(current_feature.get("kind", "")):
                compatibility = _replace_compatibility(role_match, current_feature)
                actions.append(
                    {
                        "action": "replace_feature",
                        "target_scope": "feature",
                        "target_feature_selector": _feature_selector(role_match),
                        "replacement_feature": _feature_selector(current_feature),
                        "parameters": copy.deepcopy(current_feature.get("parameters", {})),
                        "parameter_selectors": _parameter_selectors(dict(current_feature.get("parameters", {}))),
                        "references": copy.deepcopy(current_feature.get("references", {})),
                        "host_reference": _host_reference(current_feature),
                        "selector_strategy": _selector_strategy(role_match, current_feature),
                        "match_confidence": _selector_confidence(role_match, current_feature),
                        "replacement_compatibility": compatibility,
                        "boundary": _replace_feature_boundary(
                            previous_feature=role_match,
                            current_feature=current_feature,
                            previous_features=previous_features,
                            selector_strategy=_selector_strategy(role_match, current_feature),
                            match_confidence=_selector_confidence(role_match, current_feature),
                        ),
                        "preflight": _replace_feature_preflight(
                            current_feature=current_feature,
                            match_confidence=_selector_confidence(role_match, current_feature),
                            compatibility=compatibility,
                        ),
                    }
                )
                target_selector = _feature_selector(role_match)
                local_rebuild_targets.append(target_selector)
                local_rebuild_host_targets.append(target_selector)
                local_rebuild_downstream_targets.extend(_downstream_subtractive_features(previous_features, target_selector))
                local_rebuild_same_plane_targets.extend(
                    _same_plane_derived_features(previous_features, host_selector=target_selector)
                )
                if str(role_match.get("kind", "")) == "base_body":
                    local_rebuild_affects_base_body = True
                continue
            if str(current_feature.get("kind", "")) != "base_body":
                actions.append(
                    {
                        "action": "append_feature",
                        "target_scope": "feature_append",
                        "feature_selector": _feature_selector(current_feature),
                        "parameters": copy.deepcopy(current_feature.get("parameters", {})),
                        "parameter_selectors": _parameter_selectors(dict(current_feature.get("parameters", {}))),
                        "references": copy.deepcopy(current_feature.get("references", {})),
                        "host_reference": _host_reference(current_feature),
                        "host_feature_selector": _host_feature_selector(current_feature),
                        "selector_strategy": "new_feature_append",
                        "match_confidence": 1.0,
                    }
                )
                if _host_reference(current_feature) or dict(current_feature.get("references", {})).get("target_semantic"):
                    current_selector = _feature_selector(current_feature)
                    local_rebuild_targets.append(current_selector)
                    if _host_feature_selector(current_feature):
                        host_selector = _host_feature_selector(current_feature)
                        local_rebuild_host_targets.append(host_selector)
                        local_rebuild_downstream_targets.extend(
                            _downstream_subtractive_features(previous_features, host_selector)
                        )
                        local_rebuild_same_plane_targets.extend(
                            _same_plane_derived_features(
                                previous_features,
                                host_reference=_host_reference(current_feature),
                                host_selector=host_selector,
                            )
                        )
            continue

        previous_params = dict(previous_feature.get("parameters", {}))
        current_params = dict(current_feature.get("parameters", {}))
        changed_parameters = _parameter_diff(previous_params, current_params)
        if changed_parameters:
            actions.append(
                {
                    "action": "update_parameters",
                    "target_scope": "feature",
                    "target_feature_selector": _feature_selector(previous_feature),
                    "parameters": changed_parameters,
                    "parameter_selectors": _parameter_selectors(changed_parameters),
                    "selector_strategy": _selector_strategy(previous_feature, current_feature),
                    "match_confidence": _selector_confidence(previous_feature, current_feature),
                }
            )
            previous_selector = _feature_selector(previous_feature)
            if str(previous_feature.get("kind", "")) != "base_body":
                local_rebuild_targets.append(previous_selector)
                local_rebuild_host_targets.append(previous_selector)
                local_rebuild_downstream_targets.extend(_downstream_subtractive_features(previous_features, previous_selector))
                local_rebuild_same_plane_targets.extend(
                    _same_plane_derived_features(
                        previous_features,
                        host_reference=_host_reference(previous_feature),
                        host_selector=previous_selector,
                    )
                )
            else:
                local_rebuild_affects_base_body = True

    if actions:
        if local_rebuild_targets:
            deduped_targets = []
            seen = set()
            for item in local_rebuild_targets:
                key = tuple(str(item.get(key, "")) for key in ["id", "kind", "functional_role", "method"])
                if key in seen:
                    continue
                seen.add(key)
                deduped_targets.append(item)
            deduped_host_targets = []
            seen = set()
            for item in local_rebuild_host_targets:
                key = tuple(str(item.get(key, "")) for key in ["id", "kind", "functional_role", "method"])
                if key in seen:
                    continue
                seen.add(key)
                deduped_host_targets.append(item)
            deduped_downstream_targets = []
            seen = set()
            for item in local_rebuild_downstream_targets:
                key = tuple(str(item.get(key, "")) for key in ["id", "kind", "functional_role", "method"])
                if key in seen:
                    continue
                seen.add(key)
                deduped_downstream_targets.append(item)
            deduped_same_plane_targets = []
            seen = set()
            for item in local_rebuild_same_plane_targets:
                key = tuple(str(item.get(key, "")) for key in ["id", "kind", "functional_role", "method"])
                if key in seen:
                    continue
                seen.add(key)
                deduped_same_plane_targets.append(item)
            actions.append(
                {
                    "action": "local_rebuild",
                    "target_scope": "dependency_chain",
                    "affected_feature_selectors": deduped_targets,
                    "boundary": _local_rebuild_boundary(
                        deduped_targets,
                        host_targets=deduped_host_targets,
                        same_plane_targets=deduped_same_plane_targets,
                        downstream_targets=deduped_downstream_targets,
                        affects_base_body=local_rebuild_affects_base_body,
                    ),
                    "preflight": _local_rebuild_preflight(deduped_targets),
                }
            )
        actions.append(
            {
                "action": "rebuild_revision",
                "revision_index": revision_index,
                "parent_job_id": previous_job_id,
            }
        )

    return {
        "version": EDIT_PLAN_VERSION,
        "mode": "rebuild_from_context",
        "request": request,
        "source_context": {
            "job_id": str(existing_part_context.get("job_id", "")),
            "part_name": str(existing_part_context.get("part_name", "")),
            "revision_index": int(existing_part_context.get("revision_index", 1)),
            "dominant_geometry": str(existing_part_context.get("dominant_geometry", "")),
        },
        "actions": actions,
        "output_revision": {
            "creates_new_revision": True,
            "revision_index": revision_index,
            "parent_job_id": previous_job_id,
            "suggested_job_id": suggested_job_id,
        },
        "questions": list(feature_plan.get("questions", [])),
        "warnings": list(feature_plan.get("warnings", [])),
    }


def build_edit_dsl(edit_plan: dict[str, Any]) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    for action in edit_plan.get("actions", []):
        operation = {"type": str(action.get("action", ""))}
        for key in [
            "target_scope",
            "feature_selector",
            "target_feature_selector",
            "replacement_feature",
            "parameters",
            "parameter_selectors",
            "references",
            "host_reference",
            "host_feature_selector",
            "selector_strategy",
            "match_confidence",
            "replacement_compatibility",
            "affected_feature_selectors",
            "boundary",
            "preflight",
            "revision_index",
            "parent_job_id",
        ]:
            if key in action:
                operation[key] = copy.deepcopy(action[key])
        operations.append(operation)
    return {
        "version": EDIT_DSL_VERSION,
        "mode": str(edit_plan.get("mode", "")),
        "request": str(edit_plan.get("request", "")),
        "source_context": copy.deepcopy(edit_plan.get("source_context")),
        "operations": operations,
        "output_revision": copy.deepcopy(edit_plan.get("output_revision", {})),
    }
