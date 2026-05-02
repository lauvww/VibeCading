---
name: vibecading-cad-agent
description: SolidWorks-first CAD Agent MCP workflow for VibeCading. Use when Codex needs to turn natural-language mechanical CAD intent into Feature Plan / structured CAD JSON / Primitive DSL, infer modeling strategy from part function, use context, mating interfaces, manufacturing intent, and feature roles, choose the simplest maintainable SolidWorks feature tree, build or extend parametric parts, add production constrained sketches or sketch edit primitives including fillet, chamfer, mirror, pattern, slot, polygon, spline, convert entities, offset entities, trim/delete cleanup, open slots, edge notches, sweep/cut_sweep/guide-curve sweep/loft/cut_loft, validate exports, summarize modeling stages, or continue development of the local CAD Agent MCP under D:\VibeCading.
---

# VibeCading CAD Agent

Use this skill for VibeCading CAD automation work. Keep the core boundary strict:

```text
Natural language -> Agent planning -> Feature Plan -> Primitive DSL -> MCP tools -> CAD adapter -> SolidWorks -> files + summary
```

Do not generate arbitrary SolidWorks macro text as the main implementation path. Generate structured operations and let the local executor run them.

## Current Product Direction

- Build a local AI automation workbench for mechanical CAD.
- Use SolidWorks first for development and testing.
- Keep future CAD software support behind adapters; do not leak SolidWorks-specific behavior into the core DSL.
- Start with reliable part modeling, then expand to assemblies, drawings, and drawing-to-model workflows.
- Prefer deterministic templates and primitive operations over broad "one sentence to any CAD" promises.
- Do not grow into a part-template library. Grow reusable Feature Plan feature kinds, engineering-intent fields, and compiler rules.

## Modeling Workflow

1. Identify whether the request is a part template, direct primitive part, assembly, drawing, export, or reverse-modeling task.
2. Extract engineering intent before geometry: part role, use context, mating interfaces, load or motion context, manufacturing intent, primary shape, functional features, symmetry, reference datums, repeated geometry, manufacturing-critical dimensions, and required exports.
3. Split the part into functional features such as mounting, locating, fastening, bearing, sealing, guiding, load-bearing, clearance, lightening, reinforcement, transition, or cosmetic/manufacturing treatment.
4. Choose the modeling command for each feature from its function and context. Do not require the user to name `extrude`, `revolve`, `sweep`, or `loft`; infer the command unless the engineering intent is ambiguous.
5. Choose the sketch strategy from the selected command: closed profile for extrude/cut, half-section plus axis for revolve/cut_revolve, path plus profile for sweep/cut_sweep, ordered sections on datum/offset planes for loft/cut_loft, or converted/offset face references for face-derived features.
6. Choose a modeling strategy before writing JSON. Prefer the simplest maintainable strategy, not merely the fewest operations.
   Use the local `plan-strategy` command or `plan_modeling_strategy_tool` when the request is natural language, ambiguous, or may be modeled several ways.
7. For current supported rotational and prismatic requests, use `plan-features` to draft an inspectable Feature Plan before compiling it.
8. Use `draft-job` or `run-nl` only after the Feature Plan has no unresolved questions or missing capabilities.
9. For other part modeling, prefer `primitive_part` or an upper template that compiles into `primitive_part`.
10. Keep all dimensions in `mm`.
11. Add constraints and driving dimensions before any feature operation.
12. Prefer driving dimensions and geometric relations over `fixed`; reserve `fixed` for minimal origin/reference anchors, not production geometry or generated pattern copies.
13. Require `validate_fully_constrained` before any sketch-driven feature when a sketch drives parametric geometry.
14. Execute with the local runner.
15. Inspect `summary.json`; only report generated CAD files that exist and are non-empty.

## Question Workflow

Use questions to protect engineering intent, not to shift routine work back to the user.

- Decide directly when a missing value has a harmless, conventional default and does not change mating, manufacturability, or the feature tree.
- Ask before execution when the missing or ambiguous point changes function, fit, manufacturing method, reference datum, or downstream editability.
- Ask at most three focused questions in one turn. Put the recommended default first, then ask for confirmation only when the default affects engineering intent.
- Record every question in `Feature Plan.questions`; record safe assumptions in `engineering_context.semantic_assumptions` or feature-level parameters.
- Do not compile Primitive DSL while `questions` or `missing_capabilities` remain, unless the request is explicitly for a draft or preview-only plan.
- For ambiguous holes, slots, grooves, faces, fillets, and chamfers, ask about function first, then dimensions and references. Function usually decides the modeling method.

High-priority question triggers:

- Hole function is unclear: fastener clearance, threaded hole, locating pin, bearing seat, routing, or weight reduction.
- Slot/groove function is unclear: adjustment, clearance, sealing, guide, relief, or decorative cut.
- Target face, datum, direction, or offset plane is unclear.
- Fit, mating part, load direction, motion path, or manufacturing process changes the feature shape.
- A requested feature is understood but not yet compile-ready; return a planned feature plus `missing_capabilities`, then ask only for the parameters needed to make it executable.

## Supported Job Types

- `mounting_plate`: upper template for rectangular installation plates.
- `feature_part`: upper template layer; currently keeps `l_profile_extrude` as an example.
- `feature_plan.v1`: natural-language planning handoff layer with dominant geometry, engineering context, reusable feature list, feature intent, modeling-method reasons, sketch strategies, parameters, references, questions, and missing capabilities.
- `primitive_part`: low-level execution DSL used by SolidWorks Primitive Executor.

Compile-ready natural-language Feature Plan semantics now include:

- Adjustment obround slots / long slots when slot count, length, and width are available. These compile to dimensioned `add_straight_slot` operations followed by `cut_extrude`.
- Rotational annular / seal / relief grooves when groove width, bottom diameter, and axial position are known. These compile to a fully constrained groove half-section followed by `cut_revolve`.
- Countersinks and counterbores when nominal size, head diameter, seat depth, and hole layout are known. Countersinks use `cut_extrude` with `draft_angle` for the conical seat; counterbores use a cylindrical seat cut.
- Threaded holes when thread size, thread depth, and hole layout are known. The current executor creates tap-drill geometry and carries `thread_metadata`; it is not yet a full SolidWorks Hole Wizard / cosmetic thread feature.
- Centered generic pockets / clearance slots, bosses, and simple rib extrusions when their driving dimensions are known.

Recognized but not yet compile-ready Feature Plan semantics include ambiguous planar slots, fillets, chamfers, and any feature missing target/reference data. Keep them in `features` with questions or `missing_capabilities` until a compiler rule and tests exist.

Current primitive operations:

- `start_sketch`
- `start_sketch_on_face`
- `finish_sketch`
- `tag_face`
- `create_offset_plane`
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
- `extrude`
- `cut_extrude`
- `revolve`
- `cut_revolve`
- `sweep`
- `cut_sweep`
- `loft`
- `cut_loft`

Read `references/part-modeling-checkpoint.md` when asked for a stage summary, handoff, current capability recap, or next development direction.

Read `references/modeling-strategy-selection.md` when the user asks how natural language becomes CAD operations, when a part can be modeled multiple ways, when choosing the simplest/cleanest feature tree matters, or before implementing a complex natural-language-to-primitive workflow.

Read `references/primitive-modeling-stage.md` when continuing primitive modeling, adding a new primitive, or explaining detailed primitive behavior.

Read `references/sketch-tools-stage.md` when working on sketch-level automation, sketch fillet/chamfer/mirror/pattern, straight slots, polygons, splines, convert entities, offset entities, fully defined sketch workflows, or sketch-edit failure diagnosis.

Read `references/face-derived-sketch-cleanup-stage.md` when working on open slots, edge notches, U-shaped cuts, face-derived grooves, converted/offset reference geometry, or workflows that need `trim_entities` / `delete_entities` cleanup before the final feature.

Read `references/sweep-guide-stage.md` when working on sweep, cut sweep, arc paths, twist control, guide curves, variable-section sweep, or SolidWorks sweep failure diagnosis.

## Development Rules

- Do not add one SolidWorks function per product template. Add reusable primitives and compile templates into those primitives.
- Do not expand natural-language coverage by adding a new hard-coded generator for every named part. Expand reusable Feature Plan feature kinds and compiler rules instead.
- Do not let users carry the burden of naming modeling commands. The Agent should infer commands from function, use context, mating interfaces, and feature roles, then ask only when those engineering semantics are unclear.
- Do not emit Primitive DSL before choosing a feature strategy. Compare plausible strategies and choose the one with the clearest design intent, fewest robust features, simplest constraints, and best editability.
- Use `plan-strategy` as the first local planning pass for natural-language part requests. Treat its output as strategy metadata and missing-parameter guidance, not as final CAD JSON.
- Use `plan-features` as the second local planning pass. Treat its output as the structured handoff from Agent reasoning to CAD compilation. The Feature Plan should carry `engineering_context` plus per-feature `functional_role`, `feature_intent`, `mating_interfaces`, `modeling_method`, and `sketch_strategy`.
- Use `draft-job` / `run-nl` only for compile-ready Feature Plans in the supported drafting scope: stepped shafts, simple cylinders, washers, through center bores, annular/seal/relief grooves, basic mounting plates/blocks with center holes or four-corner hole patterns, adjustment obround slots, countersinks/counterbores, tap-drill threaded holes, centered pockets/clearance slots, bosses, and simple rib extrusions. If unsupported requested features such as ambiguous planar slots, fillets, chamfers, or missing target references are present, return questions or expand the Feature Plan family/compiler rule first; do not silently omit them.
- For supported adjustment slots, map "长圆孔用于调节张紧" to `kind=obround_slot`, `functional_role=adjustment_slot`, `method=cut_extrude`, and `sketch_strategy.type=straight_slot_profile`, then compile to dimensioned `add_straight_slot` primitives and a through `cut_extrude`.
- For supported rotational seal grooves, map "密封槽" on a shaft/rotational part to `kind=groove`, `functional_role=seal_groove`, `method=cut_revolve`, and require groove width, bottom diameter, and axial position.
- For threaded holes, do not claim a modeled thread unless Hole Wizard / cosmetic thread support has been explicitly added. The current supported behavior is tap-drill geometry plus thread metadata.
- Do not accept unconstrained source sketches for engineering part generation.
- Do not use `fixed` as the default way to make sketches pass validation. Use dimensions and geometric relations so the resulting model remains editable.
- Avoid fully defining sketches by dimensioning every endpoint from the origin. Prefer compact driving dimensions: one datum/center reference, feature size dimensions, spacing/pattern dimensions, and geometric relations. This applies to rectangles, holes, slots, polygons, splines, offset contours, ribs, bosses, and derived-face sketches. Extra dimensions that SolidWorks turns gray are usually driven/reference dimensions and should be reduced in production sketches.
- Do not claim STEP, SLDPRT, SVG, or PDF output unless the artifact exists and summary marks it complete.
- Do not hide SolidWorks COM failures. Return the failed operation and error clearly.
- Use preview backend for cheap validation, but do not treat preview as real CAD geometry.
- When SolidWorks is required, use the project conda environment and local templates.
- Preserve Chinese job names, part names, operation ids, named faces, reference planes, and output filenames unless a character is unsafe for Windows or SolidWorks.
- Natural-language modeling requests should be converted into a feature strategy first. Use `extrude` / `cut_extrude` for prismatic geometry, `revolve` / `cut_revolve` for rotational geometry, `sweep` / `cut_sweep` for one-profile-one-path geometry, `loft` for ordered multi-section blended geometry, and `cut_loft` for tapered or multi-section subtractive passages. For sketch-level fillets and chamfers, first create and dimension the base sketch, then apply SolidWorks sketch commands through `sketch_fillet` or `sketch_chamfer`. When mirrored holes or repeated holes are naturally part of a sketch, prefer `add_mirrored_circle` and `add_circle_linear_pattern` instead of adding extra downstream features. Use `convert_entities` followed by `offset_entities` when the user describes a groove, lip, gasket path, inner rim, or contour derived from an existing model edge. For open slots, edge notches, U-shaped cuts, and cuts entering from a model edge, derive face references first, remove temporary reference geometry with `trim_entities` / `delete_entities`, then create a clean dimensioned cut profile and call `cut_extrude`. For spline-driven curves, explicitly dimension fit points and add endpoint/tangent/curvature relations where the engineering intent requires them; use `fully_define_sketch` only as a controlled final pass for residual SolidWorks spline degrees of freedom. For guide-curve sweeps, add explicit `pierce` relations between the profile sketch and both the path and guide curve before creating the feature. For loft and cut loft, create fully constrained profile sketches on ordered datum or offset planes before calling the feature.
- Ask the user to align on function and work context when command choice would change design intent, such as whether a slot is for adjustment, clearance, sealing, or guidance; whether a hole is for bolts, pins, bearings, routing, or weight reduction; whether a face is a mating datum, machining datum, sealing face, bearing face, or cosmetic surface.

## Commands

Use the project Python:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe
```

Validate a job:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py validate .\examples\primitives\face_reference_test_part.json
```

Run preview:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\primitives\face_reference_test_part.json --backend preview
```

Plan a natural-language modeling strategy:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py plan-strategy "做一个带中心孔和环形槽的阶梯轴，直径40，长度120"
```

Draft a natural-language Feature Plan:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py plan-features "做一个安装板，长120宽80厚8，四角孔孔径8，孔边距15，材料6061铝"
```

Draft a supported natural-language job:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py draft-job "做一个阶梯轴，总长120，最大直径40，左段直径30长度40，右段直径20长度30，中心孔直径10贯穿，材料45钢"
```

Draft a supported mounting plate:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py draft-job "做一个安装板，长120宽80厚8，四角孔孔径8，孔边距15，材料6061铝"
```

Run a supported natural-language job:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run-nl "做一个阶梯轴，总长120，最大直径40，左段直径30长度40，右段直径20长度30，中心孔直径10贯穿，材料45钢" --backend solidworks
```

Run SolidWorks:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\primitives\face_reference_test_part.json --backend solidworks
```

Run tests:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe -m unittest discover .\mcp-server\tests
```

## When To Ask

Ask the user only when a missing choice affects geometry, manufacturability, output format, safety, or irreversible local actions. Otherwise choose stable defaults, execute, validate, and report the result.
