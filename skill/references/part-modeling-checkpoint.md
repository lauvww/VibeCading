# Part Modeling Checkpoint

Use this reference when the user asks for a阶段性总结, handoff, or when continuing VibeCading part-modeling development after the Primitive DSL stage.

## Current Stage Result

VibeCading has moved from product-specific SolidWorks functions to a reusable `primitive_part` workflow:

```text
natural language request
-> feature strategy
-> constrained sketches and references
-> primitive operations
-> SolidWorks Primitive Executor
-> SLDPRT / STEP / SVG / PDF / summary.json
```

The central decision remains: do not let AI directly generate uncontrolled SolidWorks macros. The agent should choose a modeling strategy, emit structured CAD JSON, and let the local MCP/SolidWorks executor perform bounded operations.

## Built Capabilities

- Upper templates such as `mounting_plate` and `feature_part/l_profile_extrude` compile into primitives.
- `primitive_part` can now express multi-feature parts instead of requiring a new SolidWorks function for each product.
- Sketches are expected to be fully constrained before feature creation.
- Generated planar faces can be selected by feature id, normal, min/max position, area order, or a user-facing named face.
- Named offset reference planes can be created from selected faces.
- Additive sweep can now use one constrained profile sketch and one constrained path sketch.
- Sweep cut, circular arc paths, and constant twist sweep are supported and SolidWorks-tested.
- Guide-curve / variable-section sweep is represented in the DSL and now has a SolidWorks-tested example.
- Additive loft with ordered profiles is supported and SolidWorks-tested.
- Cut loft with ordered profiles is supported and SolidWorks-tested.
- Sketch-level optimization is supported and SolidWorks-tested for sketch fillets, sketch chamfers, mirrored circular holes, and linear circular sketch patterns.
- Sketch editing is supported and SolidWorks-tested for projected face-loop conversion, inward offset entities, shallow groove cutting, trim/delete cleanup, and open edge-slot cutting.
- Offset reference planes can be created from selected faces or original datum planes.
- Chinese job ids, part names, operation ids, named faces, reference planes, and output filenames are supported with UTF-8 files.
- SolidWorks has been tested for extrusion, cut extrusion, generated-face sketching, offset reference planes, revolve, cut revolve, sweep, cut sweep, arc sweep paths, constant twist sweep, guide-curve sweep, loft, cut loft, sketch-level fillet/chamfer/mirror/pattern workflows, spline full-definition fallback, projected face-loop conversion, sketch offset entities, sketch trim/delete cleanup, and open edge-slot cutting.

## Current Primitive Set

- Sketch and reference setup:
  - `start_sketch`
  - `start_sketch_on_face`
  - `finish_sketch`
  - `tag_face`
  - `create_offset_plane`
- Sketch geometry:
  - `add_polyline`
  - `add_arc`
  - `add_center_rectangle`
  - `add_chamfered_rectangle`
  - `add_straight_slot`
  - `add_polygon`
  - `add_spline`
  - `add_circle`
  - `add_mirrored_circle`
  - `add_circle_linear_pattern`
  - `add_point`
  - `add_centerline`
- Constraints and dimensions:
  - `add_axis_constraints`
  - `add_relation`
  - `add_dimensions`
  - `sketch_fillet`
  - `sketch_chamfer`
  - `fully_define_sketch`
  - `convert_entities`
  - `offset_entities`
  - `trim_entities`
  - `delete_entities`
  - `validate_fully_constrained`
- Features:
  - `extrude`
  - `cut_extrude`
  - `revolve`
  - `cut_revolve`
  - `sweep`
  - `cut_sweep`
  - `loft`
  - `cut_loft`

## Verified Examples

- `examples/mounting_plate.json`: upper template mounting plate.
- `examples/l_bracket.json`: upper template L bracket compiled to primitive operations.
- `examples/multi_feature_test_part.json`: additive multi-feature primitive part.
- `examples/multi_feature_cut_test_part.json`: additive features plus `cut_extrude`.
- `examples/complex_fixture_plate.json`: larger fixture with multiple bosses, holes, and rectangular slots.
- `examples/face_reference_test_part.json`: feature-id face selection, area selection, named face, and face-based cut.
- `examples/中文命名偏置基准面测试.json`: Chinese naming, named face, offset reference plane, sketch on named plane, and cut.
- `examples/中文旋转轴测试.json`: fully constrained revolve section and 360 degree revolved body.
- `examples/中文旋转切除测试.json`: fully constrained cut-revolve section and 360 degree center bore cut from a revolved body.
- `examples/中文扫描把手测试.json`: fully constrained path sketch plus circular profile sketch, then additive sweep.
- `examples/中文圆弧扫描切除测试.json`: line-arc-line path, outer sweep, and inner `cut_sweep`.
- `examples/中文扭转扫描测试.json`: 90 degree constant-twist rectangular sweep.
- `examples/中文导向线变截面扫描测试.json`: guide-curve / variable-section sweep with explicit profile-path and profile-guide `pierce` relations; SolidWorks run generates SLDPRT, STEP, SVG, PDF, and complete summary.
- `examples/中文放样过渡管测试.json`: ordered-profile loft from three fully constrained circular sections on datum/offset planes; SolidWorks run generates SLDPRT, STEP, SVG, PDF, and complete summary.
- `examples/中文放样切除测试.json`: ordered-profile cut loft through a base block; SolidWorks run generates SLDPRT, STEP, SVG, PDF, and complete summary.
- `examples/中文草图优化测试.json`: sketch fillet, sketch chamfer, mirrored circular holes, and linear circular sketch pattern; SolidWorks run generates SLDPRT, STEP, SVG, PDF, and complete summary.
- `examples/中文槽口多边形样条测试.json`: straight slot, polygon, spline fit-point references and full-definition fallback; SolidWorks run generates SLDPRT, STEP, SVG, PDF, and complete summary.
- `examples/中文转换实体等距切槽测试.json`: projected top-face loop, inward offset, full-definition check, and shallow groove cut; SolidWorks run generates SLDPRT, STEP, SVG, PDF, and complete summary.
- `examples/中文开口槽工作流测试.json`: generated top-face sketch, converted and offset reference geometry, trim/delete cleanup, final fully constrained edge-slot cut, and complete SolidWorks SLDPRT/STEP/SVG/PDF output.

## Modeling Method

For each natural-language CAD request:

1. Determine the feature strategy before writing JSON.
2. Split the model into ordered features.
3. For each feature, decide the sketch plane:
   - base template plane for the first feature;
   - generated planar face for direct face-based work;
   - offset reference plane when a construction plane is more stable.
4. Create sketch geometry.
5. Add geometric relations and driving dimensions; use only minimal fixed origin/reference anchors when a stable datum is needed.
6. Add driving dimensions.
7. Run `validate_fully_constrained`.
8. Create the feature operation.
9. Check `summary.json`, artifact existence, and export completeness.

Do not accept a visually correct but under-constrained sketch as an engineering result.

## Natural-Language Mapping

The agent can support multiple modeling logics from natural language when the request is first mapped to a feature strategy:

- Use `extrude` for plates, blocks, pads, bosses, ribs, tabs, and prism-like features.
- Use `cut_extrude` for through holes, blind holes, slots, windows, pockets, and normal cuts.
- Use `revolve` for shafts, sleeves, bushings, washers, spacers, cones, pulleys, knobs, and lathe-like parts.
- Use `cut_revolve` for center bores, annular grooves, relief cuts, countersunk rotational cuts, and lathe-like subtractive features.
- Use `sweep` for pipes, handles, rails, wires, simple curved ribs, and one-profile-one-path features.
- Use `cut_sweep` for swept bores, curved grooves, oil passages, wiring channels, and tube hollowing.
- Use `loft` for ducts, transitions, blended housings, tapered shells, and ordered multi-section geometry.
- Use `cut_loft` for tapered bores, reducer channels, multi-section ports, and inlet/outlet passages with different section sizes.
- Use sketch-level primitives for rounded profiles, chamfered sketch windows, symmetric holes, and same-diameter hole rows when those actions are naturally part of the source sketch.
- Use convert/offset/trim/delete sketch-editing primitives for open slots, edge notches, U-shaped cuts, and face-derived grooves when the user describes geometry relative to an existing model edge or face boundary.

When the natural-language request lacks a manufacturing-critical dimension, ask the user. When a stable default is harmless, choose it and record it in the summary.

## SolidWorks Lessons

- Use `pywin32` compatibility helpers because some COM members behave like properties and some like methods.
- Do not depend on whichever document is active. Create the SolidWorks document from the project template.
- Name created features by operation id so later operations can refer to them.
- For generated faces, feature-id selection is safer than global body-face selection.
- For ambiguous planar faces, filter by normal and min/max position, then sort by area.
- Named faces are run-local references, not permanent topological guarantees after unrelated later edits.
- `create_offset_plane` is more stable than trying to sketch on difficult derived geometry.
- For `revolve` and `cut_revolve`, the tested stable pattern is a fully constrained section with a profile segment used as the axis.
- The sketch plane for rotational cuts may be an original datum plane, a generated planar face, or a named offset reference plane.
- For `sweep`, the stable pattern is to validate and `finish_sketch` the path first, then validate the profile sketch and let the feature select both sketches by id.
- For arc sweep paths, constrain line and arc endpoints with `coincident`, add `tangent` where smoothness matters, and dimension the arc center/radius.
- For guide-curve sweeps, do not claim success from preview alone. SolidWorks requires explicit guide/profile/path `pierce` relationships; geometry that merely looks intersecting is not enough.
- For loft, do not treat profile order as cosmetic. The ordered `profiles` list defines the physical transition order; create every section as a fully constrained closed sketch and close it with `finish_sketch` before calling `loft`.
- For cut loft, create the base solid first. The cut profiles should pass through the body volume and follow the intended inlet-to-outlet order.
- `create_offset_plane` can now use an original datum plane such as `front` as its base, which makes multi-section loft setup possible before any solid body exists.
- For sketch-level chamfers, prefer a constrained and dimensioned base sketch followed by `sketch_chamfer`, matching normal SolidWorks modeling practice. Keep `add_chamfered_rectangle` as a fallback for direct closed profiles.
- For sketch-level slots and polygons, prefer dimensioned geometry modes and validate the sketch before creating a cut.
- For splines, create fit-point references, dimension fit points, add endpoint/tangent/curvature relations when needed, then use `fully_define_sketch` only as a residual SolidWorks spline freedom pass.
- For grooves or lips derived from existing faces, use `convert_entities` plus `offset_entities`. The tested SolidWorks path uses projected face-loop segments (`prefer_native=false`) because native convert-entities COM calls can report success without exposing created sketch segments.
- For trimmed sketch workflows, use `trim_entities` with explicit `trim_point` or `pick_points`. SolidWorks trim is a pick-location operation; entity id alone is not enough to know which side should be removed. For boundary workflows, prefer `boundary_entities` plus `trim_targets`; for `power`, accept `method=entity_point_fallback` when native batch trim fails but the SolidWorks output succeeds.
- Use `delete_entities` for explicit cleanup of temporary sketch lines or unwanted projected/offset segments before creating a feature. Do not rely on downstream features to ignore leftover sketch geometry.
- For open slots and edge notches, a stable production workflow is: derive target-face references with `convert_entities` / `offset_entities`, remove temporary references with `trim_entities` / `delete_entities`, then create a clean dimensioned cut profile and run `cut_extrude`.
- Do not call `EditRebuild3` while an active sketch is being edited; it can break sketch-edit state before conversion, offset, or manual projection.
- Keep all project JSON and summaries UTF-8; configure CLI stdout/stderr as UTF-8 to avoid terminal mojibake.

## Validation Checklist

Before reporting success:

1. Run JSON validation for the example.
2. Run preview backend for cheap structural validation.
3. Run unit tests after executor or validator changes.
4. Run real SolidWorks when a primitive controls CAD geometry.
5. Confirm `summary.json` has `ok: true` for SolidWorks runs.
6. Confirm generated artifacts exist and are non-empty.
7. Confirm `cad_outputs_complete` is true when the user requested real CAD exports.
8. For Chinese names, inspect files with UTF-8-aware commands if terminal output looks wrong.

Recommended commands:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py validate .\examples\中文旋转轴测试.json
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文旋转轴测试.json --backend preview
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文旋转轴测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文旋转切除测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文扫描把手测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文圆弧扫描切除测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文扭转扫描测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文放样过渡管测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文放样切除测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文草图优化测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文开口槽工作流测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe -m unittest discover .\mcp-server\tests
```

## Next Development Direction

The recommended next work is to strengthen `loft`, because complex sections, connector points, guide curves, and profile matching can be ambiguous.

Keep the delivery order conservative:

1. Connector-point controls for loft profile matching.
2. Loft with guide curves.
3. More guide-curve sweep variants with multiple guide curves.
4. Fillet, chamfer, shell, mirror, and pattern primitives.
