from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from adapters.solidworks_com import SolidWorksComAdapter
from core.part_context import build_native_edit_part_context, build_part_context
from server import build_parser


class SolidWorksNativeTreeTests(unittest.TestCase):
    def test_multiple_solidworks_processes_are_rejected(self) -> None:
        with mock.patch.object(
            SolidWorksComAdapter,
            "_solidworks_processes",
            return_value=[{"image_name": "SLDWORKS.EXE", "pid": "100"}, {"image_name": "SLDWORKS.EXE", "pid": "200"}],
        ):
            with self.assertRaisesRegex(Exception, "多个 SolidWorks 进程"):
                SolidWorksComAdapter._assert_single_solidworks_process()

    def test_doc_type_from_path_recognizes_supported_types(self) -> None:
        self.assertEqual(SolidWorksComAdapter._doc_type_from_path(Path("demo.SLDPRT")), (1, "part"))
        self.assertEqual(SolidWorksComAdapter._doc_type_from_path(Path("demo.SLDASM")), (2, "assembly"))
        self.assertEqual(SolidWorksComAdapter._doc_type_from_path(Path("demo.SLDDRW")), (3, "drawing"))

    def test_feature_tree_selector_contains_stable_fields(self) -> None:
        selector = SolidWorksComAdapter._feature_tree_selector(
            feature_name="拉伸_底板",
            feature_type="BossExtrude",
            tree_index=4,
            depth=0,
            parent_feature_name=None,
            is_subfeature=False,
        )
        self.assertEqual(selector["feature_name"], "拉伸_底板")
        self.assertEqual(selector["feature_type"], "BossExtrude")
        self.assertEqual(selector["tree_index"], 4)
        self.assertEqual(selector["depth"], 0)
        self.assertFalse(selector["is_subfeature"])

    def test_selector_index_groups_types_and_native_candidates(self) -> None:
        features = [
            {
                "type": "BossExtrude",
                "native_edit_candidate": True,
                "selector": {"feature_name": "拉伸_底板", "feature_type": "BossExtrude", "tree_index": 1},
            },
            {
                "type": "ProfileFeature",
                "native_edit_candidate": True,
                "selector": {"feature_name": "草图1", "feature_type": "ProfileFeature", "tree_index": 2},
            },
            {
                "type": "OriginProfileFeature",
                "native_edit_candidate": False,
                "selector": {"feature_name": "原点", "feature_type": "OriginProfileFeature", "tree_index": 3},
            },
        ]
        index = SolidWorksComAdapter._selector_index(features)
        self.assertEqual(len(index["native_edit_candidates"]), 2)
        self.assertEqual(index["by_type"]["BossExtrude"][0]["feature_name"], "拉伸_底板")
        self.assertEqual(index["by_type"]["ProfileFeature"][0]["tree_index"], 2)

    def test_native_selector_match_uses_stable_fields(self) -> None:
        feature = {
            "selector": {
                "feature_name": "拉伸_底板",
                "feature_type": "Extrusion",
                "tree_index": 21,
                "depth": 0,
                "is_subfeature": False,
            }
        }
        selector = {"feature_name": "拉伸_底板", "tree_index": 21}
        self.assertTrue(SolidWorksComAdapter._native_selector_matches(feature, selector))
        self.assertFalse(SolidWorksComAdapter._native_selector_matches(feature, {"feature_name": "拉伸切除_安装孔"}))

    def test_match_native_feature_returns_unique_matches(self) -> None:
        features = [
            {"selector": {"feature_name": "拉伸_底板", "feature_type": "Extrusion", "tree_index": 21, "depth": 0, "is_subfeature": False}},
            {"selector": {"feature_name": "拉伸切除_安装孔", "feature_type": "ICE", "tree_index": 23, "depth": 0, "is_subfeature": False}},
        ]
        matches = SolidWorksComAdapter._match_native_feature(features, {"feature_name": "拉伸切除_安装孔"})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["selector"]["tree_index"], 23)

    def test_editable_top_level_candidates_filters_to_supported_top_level_features(self) -> None:
        class StubAdapter(SolidWorksComAdapter):
            @classmethod
            def _feature_dimension_candidates(cls, _model, feature):  # type: ignore[override]
                if feature["selector"]["feature_name"] == "拉伸_底板":
                    return [{"dimension_name": "D1@底板草图", "value_mm": 120.0}]
                return []

        features = [
            {
                "type": "Extrusion",
                "is_subfeature": False,
                "selector": {"feature_name": "拉伸_底板", "feature_type": "Extrusion", "tree_index": 21},
            },
            {
                "type": "ICE",
                "is_subfeature": False,
                "selector": {"feature_name": "拉伸切除_安装孔", "feature_type": "ICE", "tree_index": 23},
            },
            {
                "type": "ProfileFeature",
                "is_subfeature": True,
                "selector": {"feature_name": "孔切除草图", "feature_type": "ProfileFeature", "tree_index": 24},
            },
            {
                "type": "RefPlane",
                "is_subfeature": False,
                "selector": {"feature_name": "前视基准面", "feature_type": "RefPlane", "tree_index": 17},
            },
        ]
        candidates = StubAdapter._editable_top_level_candidates(object(), features)
        self.assertEqual([item["feature_name"] for item in candidates], ["拉伸_底板", "拉伸切除_安装孔"])
        self.assertEqual(candidates[0]["supported_operations"], ["suppress_feature", "unsuppress_feature", "update_dimension"])
        self.assertEqual(candidates[0]["dimension_candidates"][0]["dimension_name"], "D1@底板草图")
        self.assertIn("length", candidates[0]["supported_parameter_roles"])

    def test_supported_parameter_roles_include_hole_wizard_roles(self) -> None:
        roles = SolidWorksComAdapter._supported_parameter_roles_for_feature_type("HoleWzd")
        self.assertIn("nominal_size", roles)
        self.assertIn("thread_size", roles)
        self.assertIn("counterbore_diameter", roles)

    def test_part_context_preserves_native_feature_tree_metadata(self) -> None:
        context = build_part_context(
            job={
                "job_id": "demo-native-tree",
                "kind": "primitive_part",
                "units": "mm",
                "part": {"name": "demo-part", "material": "6061铝", "source_kind": "feature_plan_prismatic"},
            },
            feature_plan={
                "dominant_geometry": "prismatic",
                "parameters": {"length": 120.0},
                "engineering_context": {},
                "features": [],
            },
            summary={
                "summary_path": "demo-summary.json",
                "output_dir": "demo-output",
                "metadata": {
                    "native_feature_tree": {
                        "version": "solidworks_feature_tree.v1",
                        "feature_count": 2,
                        "features": [{"name": "拉伸_底板"}],
                    }
                },
            },
        )
        self.assertIn("native_feature_tree", context)
        self.assertEqual(context["native_feature_tree"]["feature_count"], 2)
        self.assertEqual(context["native_feature_tree"]["features"][0]["name"], "拉伸_底板")

    def test_part_context_builds_native_feature_bindings(self) -> None:
        context = build_part_context(
            job={
                "job_id": "demo-bindings",
                "kind": "primitive_part",
                "units": "mm",
                "part": {"name": "demo-part", "material": "6061铝", "source_kind": "feature_plan_prismatic"},
            },
            feature_plan={
                "dominant_geometry": "prismatic",
                "parameters": {"length": 120.0, "width": 80.0, "thickness": 8.0},
                "engineering_context": {},
                "features": [
                    {
                        "id": "棱柱主形体",
                        "kind": "base_body",
                        "method": "extrude",
                        "functional_role": "mounting_plate_body",
                        "parameters": {"length": 120.0, "width": 80.0, "thickness": 8.0},
                    },
                    {
                        "id": "孔组切除",
                        "kind": "hole_pattern",
                        "method": "cut_extrude",
                        "functional_role": "fastener_hole_pattern",
                        "parameters": {"depth": 10.0},
                    },
                ],
            },
        )
        bindings = context["native_feature_bindings"]
        self.assertEqual(bindings[0]["native_feature_name"], "拉伸_底板")
        self.assertTrue(any(item["parameter_role"] == "length" for item in bindings[0]["parameter_roles"]))
        self.assertEqual(bindings[1]["native_feature_name"], "拉伸切除_安装孔")
        self.assertTrue(any(item["parameter_role"] == "depth" for item in bindings[1]["parameter_roles"]))

    def test_part_context_builds_hole_diameter_binding_paths(self) -> None:
        context = build_part_context(
            job={
                "job_id": "demo-hole-bindings",
                "kind": "primitive_part",
                "units": "mm",
                "part": {"name": "demo-part", "material": "6061铝", "source_kind": "feature_plan_prismatic"},
            },
            feature_plan={
                "dominant_geometry": "prismatic",
                "parameters": {},
                "engineering_context": {},
                "features": [
                    {
                        "id": "孔组切除",
                        "kind": "hole_pattern",
                        "method": "cut_extrude",
                        "functional_role": "fastener_hole_pattern",
                        "parameters": {
                            "holes": [
                                {"diameter": 8.0, "center": [-45.0, -25.0]},
                                {"diameter": 8.0, "center": [45.0, -25.0]},
                            ]
                        },
                    }
                ],
            },
        )
        bindings = context["native_feature_bindings"]
        diameter_role = next(item for item in bindings[0]["parameter_roles"] if item["parameter_role"] == "diameter")
        self.assertIn(["hole_diameter"], diameter_role["context_parameter_paths"])
        self.assertIn(["holes", "0", "diameter"], diameter_role["context_parameter_paths"])
        self.assertIn(["holes", "1", "diameter"], diameter_role["context_parameter_paths"])

    def test_model_geometry_snapshot_counts_faces_and_edges(self) -> None:
        class FakeBody:
            def GetFaces(self):
                return ("f1", "f2", "f3")

            def GetEdges(self):
                return ("e1", "e2")

        class FakeModel:
            def GetBodies2(self, *_args):
                return (FakeBody(), FakeBody())

        snapshot = SolidWorksComAdapter._model_geometry_snapshot(FakeModel())
        self.assertEqual(snapshot["body_count"], 2)
        self.assertEqual(snapshot["face_count"], 6)
        self.assertEqual(snapshot["edge_count"], 4)

    def test_feature_dimension_candidates_use_direct_profile_children_only(self) -> None:
        class StubAdapter(SolidWorksComAdapter):
            @classmethod
            def _collect_feature_tree(cls, _model, *, include_objects: bool = False):  # type: ignore[override]
                return [
                    {
                        "name": "拉伸_底板",
                        "type": "Extrusion",
                        "parent_feature_name": None,
                    },
                    {
                        "name": "底板草图",
                        "type": "ProfileFeature",
                        "parent_feature_name": "拉伸_底板",
                    },
                    {
                        "name": "孔切除草图",
                        "type": "ProfileFeature",
                        "parent_feature_name": "拉伸切除_安装孔",
                    },
                ]

        class FakeParam:
            def __init__(self, full_name: str, value: float):
                self.FullName = full_name
                self.SystemValue = value

        class FakeModel:
            def Parameter(self, name: str):
                if name == "D1@拉伸_底板":
                    return FakeParam("D1@拉伸_底板@demo.Part", 0.12)
                if name == "D1@底板草图":
                    return FakeParam("D1@底板草图@demo.Part", 0.12)
                return None

        dims = StubAdapter._feature_dimension_candidates(
            FakeModel(),
            {"name": "拉伸_底板", "type": "Extrusion"},
        )
        self.assertEqual(len(dims), 2)
        self.assertEqual(dims[0]["owner_kind"], "feature")
        self.assertEqual(dims[0]["dimension_name"], "D1@拉伸_底板")
        self.assertEqual(dims[1]["owner_kind"], "sketch")
        self.assertEqual(dims[1]["dimension_name"], "D1@底板草图")

    def test_feature_dimension_candidates_include_feature_owned_dimensions(self) -> None:
        class StubAdapter(SolidWorksComAdapter):
            @classmethod
            def _collect_feature_tree(cls, _model, *, include_objects: bool = False):  # type: ignore[override]
                return []

        class FakeParam:
            def __init__(self, full_name: str, value: float):
                self.FullName = full_name
                self.SystemValue = value

        class FakeModel:
            def Parameter(self, name: str):
                if name == "D1@拉伸切除_安装孔":
                    return FakeParam("D1@拉伸切除_安装孔@demo.Part", 0.01)
                return None

        dims = StubAdapter._feature_dimension_candidates(
            FakeModel(),
            {"name": "拉伸切除_安装孔", "type": "ICE"},
        )
        self.assertEqual(len(dims), 1)
        self.assertEqual(dims[0]["owner_kind"], "feature")
        self.assertEqual(dims[0]["owner_name"], "拉伸切除_安装孔")
        self.assertEqual(dims[0]["dimension_name"], "D1@拉伸切除_安装孔")

    def test_sw_native_edit_parser_accepts_update_dimension_arguments(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "sw-native-edit",
                "--file",
                "demo.SLDPRT",
                "--context-file",
                "demo_context.json",
                "--operation",
                "update_dimension",
                "--feature-name",
                "拉伸_底板",
                "--feature-type",
                "Extrusion",
                "--tree-index",
                "21",
                "--dimension-name",
                "D1@底板草图",
                "--value-mm",
                "140",
            ]
        )
        self.assertEqual(args.operation, "update_dimension")
        self.assertEqual(args.dimension_name, "D1@底板草图")
        self.assertEqual(args.value_mm, 140.0)

    def test_sw_native_edit_parser_accepts_parameter_role_arguments(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "sw-native-edit",
                "--file",
                "demo.SLDPRT",
                "--context-file",
                "demo_context.json",
                "--operation",
                "update_dimension",
                "--feature-name",
                "拉伸_底板",
                "--feature-type",
                "Extrusion",
                "--tree-index",
                "21",
                "--parameter-role",
                "length",
                "--value-mm",
                "150",
            ]
        )
        self.assertEqual(args.parameter_role, "length")
        self.assertEqual(args.value_mm, 150.0)

    def test_resolve_dimension_candidate_by_role_uses_binding_values(self) -> None:
        selected_feature = {"name": "拉伸_底板", "type": "Extrusion"}
        candidates = [
            {"dimension_name": "D1@底板草图", "full_name": "D1@底板草图@demo.Part", "value_mm": 120.0},
            {"dimension_name": "D2@底板草图", "full_name": "D2@底板草图@demo.Part", "value_mm": 80.0},
        ]
        bindings = [
            {
                "feature_id": "棱柱主形体",
                "native_feature_name": "拉伸_底板",
                "native_feature_type": "Extrusion",
                "parameter_roles": [
                    {"parameter_role": "length", "context_parameter_paths": [["length"]], "feature_parameter_paths": [["length"]], "value_mm": 120.0},
                    {"parameter_role": "width", "context_parameter_paths": [["width"]], "feature_parameter_paths": [["width"]], "value_mm": 80.0},
                ],
            }
        ]
        candidates_out, sync_info = SolidWorksComAdapter._resolve_dimension_candidate_by_role(
            selected_feature=selected_feature,
            dimension_candidates=candidates,
            parameter_role="length",
            native_feature_bindings=bindings,
        )
        self.assertEqual(candidates_out[0]["dimension_name"], "D1@底板草图")
        self.assertEqual(sync_info["feature_id"], "棱柱主形体")
        self.assertEqual(sync_info["context_parameter_paths"], [["length"]])

    def test_resolve_dimension_candidate_by_role_supports_width(self) -> None:
        selected_feature = {"name": "拉伸_底板", "type": "Extrusion"}
        candidates = [
            {"dimension_name": "D1@底板草图", "full_name": "D1@底板草图@demo.Part", "owner_kind": "sketch", "value_mm": 120.0},
            {"dimension_name": "D2@底板草图", "full_name": "D2@底板草图@demo.Part", "owner_kind": "sketch", "value_mm": 80.0},
        ]
        bindings = [
            {
                "feature_id": "棱柱主形体",
                "native_feature_name": "拉伸_底板",
                "native_feature_type": "Extrusion",
                "parameter_roles": [
                    {"parameter_role": "length", "context_parameter_paths": [["length"]], "feature_parameter_paths": [["length"]], "value_mm": 120.0},
                    {"parameter_role": "width", "context_parameter_paths": [["width"]], "feature_parameter_paths": [["width"]], "value_mm": 80.0},
                ],
            }
        ]
        candidates_out, sync_info = SolidWorksComAdapter._resolve_dimension_candidate_by_role(
            selected_feature=selected_feature,
            dimension_candidates=candidates,
            parameter_role="width",
            native_feature_bindings=bindings,
        )
        self.assertEqual(candidates_out[0]["dimension_name"], "D2@底板草图")
        self.assertEqual(sync_info["context_parameter_paths"], [["width"]])

    def test_resolve_dimension_candidate_by_role_can_fallback_to_single_feature_owned_depth(self) -> None:
        selected_feature = {"name": "拉伸切除_安装孔", "type": "ICE"}
        candidates = [
            {
                "dimension_name": "D1@拉伸切除_安装孔",
                "full_name": "D1@拉伸切除_安装孔@demo.Part",
                "owner_name": "拉伸切除_安装孔",
                "owner_kind": "feature",
                "value_mm": 10.0,
            }
        ]
        bindings = [
            {
                "feature_id": "孔组切除",
                "kind": "hole_pattern",
                "method": "cut_extrude",
                "native_feature_name": "拉伸切除_安装孔",
                "native_feature_type": "ICE",
                "parameter_roles": [],
            }
        ]
        candidates_out, sync_info = SolidWorksComAdapter._resolve_dimension_candidate_by_role(
            selected_feature=selected_feature,
            dimension_candidates=candidates,
            parameter_role="depth",
            native_feature_bindings=bindings,
        )
        self.assertEqual(candidates_out[0]["dimension_name"], "D1@拉伸切除_安装孔")
        self.assertEqual(sync_info["status"], "native_parameter_role_synced")
        self.assertEqual(sync_info["context_parameter_paths"], [["depth"]])
        self.assertEqual(sync_info["context_literal_updates"][0]["path"], ["through"])

    def test_resolve_dimension_candidate_by_role_can_sync_thickness_via_override(self) -> None:
        selected_feature = {"name": "拉伸_底板", "type": "Extrusion"}
        candidates = [
            {
                "dimension_name": "D1@拉伸_底板",
                "full_name": "D1@拉伸_底板@demo.Part",
                "owner_name": "拉伸_底板",
                "owner_kind": "feature",
                "value_mm": 8.0,
            }
        ]
        bindings = [
            {
                "feature_id": "棱柱主形体",
                "kind": "base_body",
                "method": "extrude",
                "native_feature_name": "拉伸_底板",
                "native_feature_type": "Extrusion",
                "parameter_roles": [],
            }
        ]
        candidates_out, sync_info = SolidWorksComAdapter._resolve_dimension_candidate_by_role(
            selected_feature=selected_feature,
            dimension_candidates=candidates,
            parameter_role="thickness",
            native_feature_bindings=bindings,
        )
        self.assertEqual(candidates_out[0]["dimension_name"], "D1@拉伸_底板")
        self.assertEqual(sync_info["status"], "native_parameter_role_synced")
        self.assertEqual(sync_info["context_parameter_paths"], [["thickness"]])

    def test_resolve_dimension_candidate_by_role_can_return_multiple_diameter_matches(self) -> None:
        selected_feature = {"name": "拉伸切除_安装孔", "type": "ICE"}
        candidates = [
            {"dimension_name": "D1@孔切除草图", "full_name": "D1@孔切除草图@demo.Part", "owner_kind": "sketch", "value_mm": 8.0},
            {"dimension_name": "D4@孔切除草图", "full_name": "D4@孔切除草图@demo.Part", "owner_kind": "sketch", "value_mm": 8.0},
            {"dimension_name": "D2@孔切除草图", "full_name": "D2@孔切除草图@demo.Part", "owner_kind": "sketch", "value_mm": 45.0},
        ]
        bindings = [
            {
                "feature_id": "孔组切除",
                "native_feature_name": "拉伸切除_安装孔",
                "native_feature_type": "ICE",
                "parameter_roles": [
                    {
                        "parameter_role": "diameter",
                        "context_parameter_paths": [["hole_diameter"], ["holes", "0", "diameter"], ["holes", "1", "diameter"]],
                        "feature_parameter_paths": [["holes", "0", "diameter"], ["holes", "1", "diameter"]],
                        "value_mm": 8.0,
                    }
                ],
            }
        ]
        candidates_out, sync_info = SolidWorksComAdapter._resolve_dimension_candidate_by_role(
            selected_feature=selected_feature,
            dimension_candidates=candidates,
            parameter_role="diameter",
            native_feature_bindings=bindings,
        )
        self.assertEqual(len(candidates_out), 2)
        self.assertEqual(sync_info["resolved_dimension_names"], ["D1@孔切除草图", "D4@孔切除草图"])

    def test_capability_registry_selects_definition_paths(self) -> None:
        self.assertEqual(
            SolidWorksComAdapter._resolve_native_capability(
                selected_feature={"type": "ICE"},
                canonical_role="depth",
                native_feature_bindings=None,
                candidates_to_update=[{"owner_kind": "feature"}],
            )["edit_path"],
            "feature_definition_modify",
        )
        self.assertEqual(
            SolidWorksComAdapter._resolve_native_capability(
                selected_feature={"name": "孔向导_孔组切除_1", "type": "HoleWzd"},
                canonical_role="nominal_size",
                native_feature_bindings=[{"native_feature_name": "孔向导_孔组切除", "native_feature_type": "HoleWzd"}],
                candidates_to_update=[],
            )["edit_path"],
            "feature_definition_modify",
        )
        self.assertEqual(
            SolidWorksComAdapter._resolve_native_capability(
                selected_feature={"type": "Extrusion"},
                canonical_role="length",
                native_feature_bindings=None,
                candidates_to_update=[{"owner_kind": "sketch"}],
            )["edit_path"],
            "dimension_parameter",
        )

    def test_build_native_edit_part_context_syncs_parameter_path_when_available(self) -> None:
        existing = {
            "job_id": "demo-r1",
            "revision_index": 1,
            "units": "mm",
            "backend": "solidworks",
            "part_name": "demo",
            "material": "6061铝",
            "dominant_geometry": "prismatic",
            "parameters": {"length": 120.0, "width": 80.0},
            "engineering_context": {},
            "feature_plan": {
                "features": [
                    {"id": "棱柱主形体", "parameters": {"length": 120.0, "width": 80.0}},
                ]
            },
            "reference_registry": {},
            "lineage": [],
        }
        summary = {
            "backend": "solidworks",
            "summary_path": "demo-summary.json",
            "output_dir": "demo-output",
            "metadata": {
                "feature_plan_sync_info": {
                    "status": "native_parameter_role_synced",
                    "feature_id": "棱柱主形体",
                    "context_parameter_paths": [["width"]],
                    "feature_parameter_paths": [["width"]],
                },
                "dimension_change": {
                    "after_mm": 90.0,
                },
            },
        }
        context = build_native_edit_part_context(
            existing_part_context=existing,
            summary=summary,
            job_id="demo-r2",
            operation="update_dimension",
        )
        self.assertEqual(context["parameters"]["width"], 90.0)
        self.assertEqual(context["feature_plan"]["features"][0]["parameters"]["width"], 90.0)
        self.assertEqual(context["feature_plan_sync"], "native_parameter_role_synced")

    def test_build_native_edit_part_context_syncs_multiple_context_paths(self) -> None:
        existing = {
            "job_id": "demo-r1",
            "revision_index": 1,
            "units": "mm",
            "backend": "solidworks",
            "part_name": "demo",
            "material": "6061铝",
            "dominant_geometry": "prismatic",
            "parameters": {
                "hole_diameter": 8.0,
                "holes": [
                    {"diameter": 8.0},
                    {"diameter": 8.0},
                ],
            },
            "engineering_context": {},
            "feature_plan": {
                "features": [
                    {"id": "孔组切除", "parameters": {"holes": [{"diameter": 8.0}, {"diameter": 8.0}]}},
                ]
            },
            "reference_registry": {},
            "lineage": [],
        }
        summary = {
            "backend": "solidworks",
            "summary_path": "demo-summary.json",
            "output_dir": "demo-output",
            "metadata": {
                "feature_plan_sync_info": {
                    "status": "native_parameter_role_synced",
                    "feature_id": "孔组切除",
                    "context_parameter_paths": [["hole_diameter"], ["holes", "0", "diameter"], ["holes", "1", "diameter"]],
                    "feature_parameter_paths": [["holes", "0", "diameter"], ["holes", "1", "diameter"]],
                },
                "dimension_change": {
                    "after_mm": 10.0,
                },
            },
        }
        context = build_native_edit_part_context(
            existing_part_context=existing,
            summary=summary,
            job_id="demo-r2",
            operation="update_dimension",
        )
        self.assertEqual(context["parameters"]["hole_diameter"], 10.0)
        self.assertEqual(context["parameters"]["holes"][0]["diameter"], 10.0)
        self.assertEqual(context["parameters"]["holes"][1]["diameter"], 10.0)
        self.assertEqual(context["feature_plan"]["features"][0]["parameters"]["holes"][0]["diameter"], 10.0)

    def test_hole_wizard_sync_info_updates_nominal_and_finished_diameters(self) -> None:
        binding = {
            "feature_id": "孔组切除",
            "functional_role": "fastener_hole_pattern",
            "native_feature_name": "孔向导_孔组切除",
            "parameters_snapshot": {
                "clearance_class": "normal",
                "holes": [
                    {"clearance_class": "normal"},
                    {"clearance_class": "normal"},
                ],
            },
        }
        sync_info = SolidWorksComAdapter._hole_wizard_sync_info(
            binding=binding,
            canonical_role="nominal_size",
            target_mm=10.0,
        )
        self.assertIn(["hole_diameter"], sync_info["context_parameter_paths"])
        self.assertEqual(sync_info["context_literal_updates"][1]["value"], 11.0)
        self.assertEqual(sync_info["feature_literal_updates"][0]["path"], ["size_label"])

    def test_hole_wizard_sync_info_updates_thread_size_fields(self) -> None:
        binding = {
            "feature_id": "螺纹孔",
            "functional_role": "threaded_fastener_interface",
            "native_feature_name": "孔向导_螺纹孔",
            "parameters_snapshot": {},
        }
        sync_info = SolidWorksComAdapter._hole_wizard_sync_info(
            binding=binding,
            canonical_role="thread_size",
            target_mm=8.0,
        )
        self.assertIn(["thread_size"], sync_info["context_parameter_paths"])
        self.assertEqual(sync_info["context_literal_updates"][1]["path"], ["callout"])

    def test_hole_wizard_sync_info_updates_counterbore_paths(self) -> None:
        binding = {
            "feature_id": "沉孔",
            "functional_role": "counterbored_fastener_interface",
            "native_feature_name": "孔向导_沉孔",
            "parameters_snapshot": {"holes": [{}]},
        }
        sync_info = SolidWorksComAdapter._hole_wizard_sync_info(
            binding=binding,
            canonical_role="counterbore_depth",
            target_mm=4.0,
        )
        self.assertIn(["seat_depth"], sync_info["context_parameter_paths"])
        self.assertIn(["holes", "0", "seat_depth"], sync_info["feature_parameter_paths"])

    def test_match_native_binding_supports_hole_wizard_suffix_instances(self) -> None:
        binding = {
            "feature_id": "孔组切除",
            "native_feature_name": "孔向导_孔组切除",
            "native_feature_type": "HoleWzd",
        }
        matched = SolidWorksComAdapter._match_native_binding(
            [binding],
            {"name": "孔向导_孔组切除_1", "type": "HoleWzd"},
        )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["feature_id"], "孔组切除")

    def test_build_native_edit_part_context_applies_literal_updates(self) -> None:
        existing = {
            "job_id": "demo-r1",
            "revision_index": 1,
            "units": "mm",
            "backend": "solidworks",
            "part_name": "demo",
            "material": "6061铝",
            "dominant_geometry": "prismatic",
            "parameters": {},
            "engineering_context": {},
            "feature_plan": {
                "features": [
                    {"id": "孔组切除", "parameters": {"through": True}},
                ]
            },
            "reference_registry": {},
            "lineage": [],
        }
        summary = {
            "backend": "solidworks",
            "summary_path": "demo-summary.json",
            "output_dir": "demo-output",
            "metadata": {
                "feature_plan_sync_info": {
                    "status": "native_parameter_role_synced",
                    "feature_id": "孔组切除",
                    "context_parameter_paths": [["depth"]],
                    "feature_parameter_paths": [["depth"]],
                    "context_literal_updates": [{"path": ["through"], "value": False}],
                    "feature_literal_updates": [{"path": ["through"], "value": False}],
                },
                "dimension_change": {
                    "after_mm": 2.0,
                },
            },
        }
        context = build_native_edit_part_context(
            existing_part_context=existing,
            summary=summary,
            job_id="demo-r2",
            operation="update_dimension",
        )
        self.assertEqual(context["parameters"]["depth"], 2.0)
        self.assertFalse(context["parameters"]["through"])
        self.assertEqual(context["feature_plan"]["features"][0]["parameters"]["depth"], 2.0)
        self.assertFalse(context["feature_plan"]["features"][0]["parameters"]["through"])


if __name__ == "__main__":
    unittest.main()
