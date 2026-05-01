---
name: vibecading-cad-agent
description: SolidWorks-first CAD Agent MCP workflow for VibeCading. Use when Codex needs to turn natural-language mechanical CAD intent into structured CAD JSON/Primitive DSL, choose the simplest maintainable modeling strategy, build or extend parametric SolidWorks parts, add production constrained sketches or sketch edit primitives including fillet, chamfer, mirror, pattern, slot, polygon, spline, convert entities, offset entities, trim/delete cleanup, open slots, edge notches, sweep/cut_sweep/guide-curve sweep/loft/cut_loft, validate exports, summarize modeling stages, or continue development of the local CAD Agent MCP under D:\VibeCading.
---

# VibeCading CAD Agent

Use this skill for VibeCading CAD automation work. Keep the core boundary strict:

```text
Natural language -> Agent planning -> CAD JSON / Primitive DSL -> MCP tools -> CAD adapter -> SolidWorks -> files + summary
```

Do not generate arbitrary SolidWorks macro text as the main implementation path. Generate structured operations and let the local executor run them.

## Current Product Direction

- Build a local AI automation workbench for mechanical CAD.
- Use SolidWorks first for development and testing.
- Keep future CAD software support behind adapters; do not leak SolidWorks-specific behavior into the core DSL.
- Start with reliable part modeling, then expand to assemblies, drawings, and drawing-to-model workflows.
- Prefer deterministic templates and primitive operations over broad "one sentence to any CAD" promises.

## Modeling Workflow

1. Identify whether the request is a part template, direct primitive part, assembly, drawing, export, or reverse-modeling task.
2. Extract the engineering intent: primary shape, functional features, symmetry, reference datums, repeated geometry, manufacturing-critical dimensions, and required exports.
3. Choose a modeling strategy before writing JSON. Prefer the simplest maintainable strategy, not merely the fewest operations.
4. For current part modeling, prefer `primitive_part` or an upper template that compiles into `primitive_part`.
5. Keep all dimensions in `mm`.
6. Add constraints and driving dimensions before any feature operation.
7. Prefer driving dimensions and geometric relations over `fixed`; reserve `fixed` for minimal origin/reference anchors, not production geometry or generated pattern copies.
8. Require `validate_fully_constrained` before any sketch-driven feature when a sketch drives parametric geometry.
9. Execute with the local runner.
10. Inspect `summary.json`; only report generated CAD files that exist and are non-empty.

## Supported Job Types

- `mounting_plate`: upper template for rectangular installation plates.
- `feature_part`: upper template layer; currently keeps `l_profile_extrude` as an example.
- `primitive_part`: low-level execution DSL used by SolidWorks Primitive Executor.

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
- Do not emit Primitive DSL before choosing a feature strategy. Compare plausible strategies and choose the one with the clearest design intent, fewest robust features, simplest constraints, and best editability.
- Do not accept unconstrained source sketches for engineering part generation.
- Do not use `fixed` as the default way to make sketches pass validation. Use dimensions and geometric relations so the resulting model remains editable.
- Do not claim STEP, SLDPRT, SVG, or PDF output unless the artifact exists and summary marks it complete.
- Do not hide SolidWorks COM failures. Return the failed operation and error clearly.
- Use preview backend for cheap validation, but do not treat preview as real CAD geometry.
- When SolidWorks is required, use the project conda environment and local templates.
- Preserve Chinese job names, part names, operation ids, named faces, reference planes, and output filenames unless a character is unsafe for Windows or SolidWorks.
- Natural-language modeling requests should be converted into a feature strategy first. Use `extrude` / `cut_extrude` for prismatic geometry, `revolve` / `cut_revolve` for rotational geometry, `sweep` / `cut_sweep` for one-profile-one-path geometry, `loft` for ordered multi-section blended geometry, and `cut_loft` for tapered or multi-section subtractive passages. For sketch-level fillets and chamfers, first create and dimension the base sketch, then apply SolidWorks sketch commands through `sketch_fillet` or `sketch_chamfer`. When mirrored holes or repeated holes are naturally part of a sketch, prefer `add_mirrored_circle` and `add_circle_linear_pattern` instead of adding extra downstream features. Use `convert_entities` followed by `offset_entities` when the user describes a groove, lip, gasket path, inner rim, or contour derived from an existing model edge. For open slots, edge notches, U-shaped cuts, and cuts entering from a model edge, derive face references first, remove temporary reference geometry with `trim_entities` / `delete_entities`, then create a clean dimensioned cut profile and call `cut_extrude`. For spline-driven curves, explicitly dimension fit points and add endpoint/tangent/curvature relations where the engineering intent requires them; use `fully_define_sketch` only as a controlled final pass for residual SolidWorks spline degrees of freedom. For guide-curve sweeps, add explicit `pierce` relations between the profile sketch and both the path and guide curve before creating the feature. For loft and cut loft, create fully constrained profile sketches on ordered datum or offset planes before calling the feature.

## Commands

Use the project Python:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe
```

Validate a job:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py validate .\examples\face_reference_test_part.json
```

Run preview:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\face_reference_test_part.json --backend preview
```

Run SolidWorks:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\face_reference_test_part.json --backend solidworks
```

Run tests:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe -m unittest discover .\mcp-server\tests
```

## When To Ask

Ask the user only when a missing choice affects geometry, manufacturability, output format, safety, or irreversible local actions. Otherwise choose stable defaults, execute, validate, and report the result.
