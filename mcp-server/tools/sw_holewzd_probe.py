from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.solidworks_com import SolidWorksComAdapter, _maybe_call  # noqa: E402


def _load_swgen():
    adapter = SolidWorksComAdapter()
    return adapter._load_swgen_module()


def _cylinder_faces(feature_obj) -> list[dict[str, object]]:
    faces = _maybe_call(feature_obj.GetFaces)
    if faces is None:
        return []
    if not isinstance(faces, (list, tuple)):
        faces = [faces]
    output: list[dict[str, object]] = []
    for index, face in enumerate(faces):
        try:
            surface = _maybe_call(face.GetSurface)
            identity = _maybe_call(surface.Identity)
            record: dict[str, object] = {"face_index": index, "identity": identity}
            if identity == 4002:
                try:
                    params = _maybe_call(surface.CylinderParams)
                    record["cylinder_params"] = list(params) if isinstance(params, (list, tuple)) else params
                except Exception as exc:
                    record["cylinder_params_error"] = repr(exc)
            output.append(record)
        except Exception as exc:
            output.append({"face_index": index, "error": repr(exc)})
    return output


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: sw_holewzd_probe.py <sldprt-path> <feature-name> [new-size]", file=sys.stderr)
        return 2
    file_path = Path(sys.argv[1]).resolve()
    feature_name = sys.argv[2]
    new_size = sys.argv[3] if len(sys.argv) > 3 else None

    adapter = SolidWorksComAdapter()
    swgen = _load_swgen()
    with adapter._solidworks_session():
        sw = adapter._connect(visible=True)
        errors = adapter._byref_int()
        warnings = adapter._byref_int()
        model = sw.OpenDoc6(str(file_path), 1, 1, "", errors, warnings)
        if model is None:
            print(json.dumps({"ok": False, "error": "OpenDoc6 returned None"}, ensure_ascii=False, indent=2))
            return 1
        opened_title = str(model.GetTitle())
        try:
            rows = adapter._collect_feature_tree(model, include_objects=True)
            selected = next((row for row in rows if row.get("name") == feature_name and not row.get("is_subfeature")), None)
            if selected is None:
                print(json.dumps({"ok": False, "error": f"feature not found: {feature_name}"}, ensure_ascii=False, indent=2))
                return 1

            feature_obj = selected["_feature_object"]
            feature = swgen.IFeature(feature_obj._oleobj_)
            definition = swgen.WizardHoleFeatureData2(feature.GetDefinition()._oleobj_)

            before = {
                "geometry": adapter._model_geometry_snapshot(model),
                "faces": _cylinder_faces(feature_obj),
                "standard2": getattr(definition, "Standard2", None),
                "fastener_type2": getattr(definition, "FastenerType2", None),
                "fastener_size": getattr(definition, "FastenerSize", None),
            }

            result = {
                "ok": True,
                "feature_name": feature_name,
                "before": before,
            }

            if new_size:
                access = bool(definition.AccessSelections(model, None))
                result["access"] = access
                if access:
                    result["change_standard"] = bool(definition.ChangeStandard(definition.Standard2, definition.FastenerType2, new_size))
                    result["modify_definition"] = bool(feature.ModifyDefinition(definition, model, None))
                    try:
                        definition.ReleaseSelectionAccess()
                    except Exception:
                        pass
                    _maybe_call(model.EditRebuild3)
                    definition_after = swgen.WizardHoleFeatureData2(feature.GetDefinition()._oleobj_)
                    result["after"] = {
                        "geometry": adapter._model_geometry_snapshot(model),
                        "faces": _cylinder_faces(feature_obj),
                        "standard2": getattr(definition_after, "Standard2", None),
                        "fastener_type2": getattr(definition_after, "FastenerType2", None),
                        "fastener_size": getattr(definition_after, "FastenerSize", None),
                    }

            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        finally:
            try:
                sw.CloseDoc(opened_title)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
