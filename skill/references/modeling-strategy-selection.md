# Modeling Strategy Selection

Use this reference when a natural-language CAD request can be modeled multiple ways, when the user asks how Agent planning works, or when choosing the simplest maintainable SolidWorks feature tree matters.

## Core Answer

VibeCading should not let the MCP server guess engineering intent. The split is:

```text
User natural language
-> Agent extracts function, use context, mating interfaces, feature roles, and missing parameters
-> Agent compares plausible modeling strategies
-> Agent emits an inspectable Feature Plan
-> Feature Plan compiler emits structured Primitive DSL
-> MCP / SolidWorks executor builds and validates the model
```

The Agent chooses the modeling method from engineering semantics. The MCP executes the chosen structured operations and reports whether they worked.

## What "Simplest" Means

The simplest modeling method is not always the shortest JSON or the fewest sketch entities. Prefer the method that is easiest for an engineer to understand, edit, and verify later.

Rank strategies by these criteria:

1. Design intent is clear: dimensions and references match how the part functions, where it works, and how it mates with other parts.
2. Feature tree is readable: major manufacturing or functional steps are separate when that improves editability.
3. Sketches are fully constrained with dimensions and geometric relations.
4. Feature count is low, but not at the cost of unreadable sketches.
5. References are stable: original datums, named faces, and intentional offset planes are preferred over fragile incidental edges.
6. SolidWorks behavior is proven or low risk.
7. Future edits are localized: changing a hole spacing, wall thickness, or flange diameter should not require rebuilding the whole part.
8. Manufacturing meaning is preserved: do not hide a bore, groove, flange, or slot inside unrelated geometry just because it can be drawn that way.

## Functional Intent First

Do not build a growing library of named part generators. Treat part names as clues, not dispatch keys. The reusable planning unit is a functional feature with context:

- `part_role`: what the part does, such as support, locate, connect, seal, transmit torque, guide motion, protect, mount, or transition flow.
- `working_context`: how and where it is used, including load direction, motion, space constraints, manufacturing process, or environment.
- `mating_interfaces`: faces, holes, shafts, grooves, planes, datums, or patterns that mate with other parts.
- `feature_intent`: why each feature exists, such as fastener interface, locating pin, bearing seat, seal groove, clearance slot, lightening cut, rib, boss, stop face, or adjustment slot.
- `modeling_method`: the command selected for that feature.
- `sketch_strategy`: the sketch construction that fits the selected command.

Current `feature_plan.v1` drafts use `engineering_context` for part-level semantics:

```json
{
  "engineering_context": {
    "part_roles": ["mounting_support"],
    "working_context": ["fixed_mounting"],
    "mating_interfaces": ["mounting_face", "four_corner_fastener_pattern"],
    "manufacturing_intent": ["milled_or_plate_like"],
    "semantic_assumptions": ["units_mm"]
  }
}
```

Each feature should then carry local semantics: `functional_role`, `feature_intent`, `mating_interfaces`, `modeling_method`, and `sketch_strategy`. These fields are planning data; the SolidWorks executor still consumes compiled primitive operations.

Compile-ready feature semantics should be handled directly:

- Long obround adjustment holes: `kind=obround_slot`, `functional_role=adjustment_slot`, `method=cut_extrude`, `sketch_strategy.type=straight_slot_profile`, compiled to dimensioned `add_straight_slot` primitives plus `cut_extrude`.
- Rotational annular / seal / relief grooves: `kind=groove`, `method=cut_revolve`, with groove width, bottom diameter, and axial position required.
- Generic centered pockets and centered clearance slots: `kind=slot_or_pocket`, `method=cut_extrude`, compiled to a dimensioned top-face rectangle plus `cut_extrude` when length, width, depth, and a stable position strategy are known.
- Countersinks / counterbores: `kind=countersink` or `counterbore`, `method=cut_extrude`, with nominal size, head diameter, seat depth, and base hole reference required. Countersinks use a drafted cut for the conical seat; counterbores use a cylindrical seat cut.
- Threaded holes: `kind=threaded_hole`, `method=cut_extrude`, with thread size, thread depth, tap-drill diameter, and hole layout required. Current support creates tap-drill geometry plus `thread_metadata`, not a full Hole Wizard thread.
- Bosses and simple ribs: `kind=boss` or `rib`, with target/supporting face plus driving dimensions, compiled to additive face-based extrudes.

When a feature is understood but not compile-ready, still add a planned feature and pair it with `missing_capabilities`. Do this instead of silently dropping the feature:

- Ambiguous slots, pockets, clearance cuts, and seal grooves on planar faces: `kind=slot_or_pocket`, `method=cut_extrude`, with target face, position, profile shape, and function still required.
- Fillets and chamfers: `kind=fillet` or `chamfer`, with target edges or sketch entities and radius/distance required.

The user should not have to say "use revolve" or "use loft". Infer the command from the feature role. Ask only when missing function or work context changes the right modeling method.

## Strategy Selection Loop

Before writing Primitive DSL, do this:

1. Parse the request into engineering semantics:
   - part role
   - use context
   - mating interfaces and fit types
   - manufacturing intent
   - critical functional surfaces
2. Parse the request into engineering features:
   - base body
   - holes, slots, pockets, grooves
   - ribs, bosses, flanges, shafts
   - symmetry, repetitions, patterns
   - paths, transitions, lofted sections
   - required exports and drawings
3. Identify the dominant geometry class:
   - prismatic
   - rotational
   - path-driven
   - multi-section transition
   - face-derived or edge-derived
4. Choose a modeling method per feature from its function and geometry.
5. Choose a sketch strategy per feature from the selected modeling method.
6. Generate two or three candidate strategies when the geometry is ambiguous.
7. Score each candidate using the criteria above.
8. Choose the default strategy.
9. Ask the user only when strategy choice changes manufacturing intent, function, mating, or missing critical dimensions.
10. Emit a Feature Plan with reusable feature kinds, references, parameters, questions, and missing capabilities.
11. Compile Primitive DSL only after the Feature Plan is complete enough to execute.

## Sketch Strategy Follows Command Choice

The sketch should be designed for the feature that will consume it:

- `extrude` / `cut_extrude`: closed profile, usually a dimensioned rectangle, circle, slot, polygon, offset loop, or clean trimmed face-derived contour.
- `revolve` / `cut_revolve`: half-section profile plus explicit axis; shoulders, bores, grooves, chamfers, and reliefs should be dimensioned like lathe geometry.
- `sweep` / `cut_sweep`: path sketch plus profile sketch; add pierce or coincident relations so profile and path are not floating.
- guide-curve sweep: path sketch, guide sketch, profile sketch, and explicit profile-to-path and profile-to-guide pierce relations.
- `loft` / `cut_loft`: ordered profile sketches on datum or offset planes; section order and connection direction must preserve design intent.
- face-derived features: convert or project existing face/edge references, offset if needed, trim/delete temporary geometry, then keep a clean final feature profile.
- sketch mirror/pattern: use when symmetry or repeated holes belong to the same feature intent; otherwise use feature-level operations later.

For every sketch strategy, choose dimensions by design intent rather than by entity count. A rectangle should be driven by length/width and a datum, a hole by center/diameter, a slot by center/length/width/spacing, a revolve section by axial positions and radii, and a spline by critical fit points plus tangent/curvature relations. Do not make a sketch pass full-definition by adding endpoint-to-origin dimensions everywhere; those dimensions often become driven/reference dimensions and make the model harder to edit.

## Default Strategy Rules

Use these rules as the first pass:

- Plates, blocks, pads, bosses, rectangular pockets, windows: use `extrude` / `cut_extrude`.
- Shafts, sleeves, pulleys, washers, knobs, cones, lathe-like parts: use `revolve`.
- Center bores, annular grooves, and lathe-style relief cuts: use `cut_revolve`.
- Plate countersinks / counterbores / tap-drill threaded holes: use face-based `cut_extrude`; use a draft angle for conical countersinks and preserve thread metadata for threaded holes until Hole Wizard support is added.
- Pipes, handles, rails, wires, curved ribs: use `sweep`.
- Curved grooves, swept bores, oil passages, tube hollowing: use `cut_sweep`.
- Ducts, reducers, smooth transitions, changing sections: use `loft`.
- Tapered passages and multi-section internal channels: use `cut_loft`.
- Same-plane repeated holes: prefer one sketch with `add_circle_linear_pattern` when the pattern belongs to one feature.
- Symmetric sketch geometry: prefer sketch mirror when symmetry is part of the sketch design intent.
- Edge-derived grooves, lips, inset paths: use `convert_entities` + `offset_entities`.
- Open slots, edge notches, U-shaped cuts: derive face references, clean temporary geometry with `trim_entities` / `delete_entities`, then create a clean `cut_extrude` profile.
- Sketch fillets/chamfers: first draw and dimension the base sketch, then apply `sketch_fillet` or `sketch_chamfer`.

## When Fewer Features Is Not Better

Do not pack everything into one huge sketch when it reduces clarity. Split features when:

- a later feature has a distinct function, such as a mounting hole, locating boss, relief slot, or seal groove;
- dimensions should be edited independently;
- the feature should be suppressed, patterned, mirrored, or reused later;
- the sketch would need many unrelated constraints;
- a generated face or offset plane is the natural engineering reference.

Good feature trees are short enough to scan, but not so compressed that design intent disappears.

## Candidate Comparison Examples

### Shaft

Bad default:

```text
extrude multiple cylinders from several circular sketches
```

Better default:

```text
one fully constrained half-section -> revolve
then cut_revolve grooves or bores
```

Reason: rotational dimensions, shoulders, grooves, and bores match lathe-style design intent.

### Mounting Plate With Hole Pattern

Good default:

```text
base rectangle sketch -> extrude
hole sketch on top face -> patterned circles -> cut_extrude
```

Reason: plate size and hole pattern stay editable. Same-plane holes should not require separate cut features unless they have different semantics.

### Edge Slot

Bad default:

```text
leave converted boundary loops and temporary centerlines in the final cut sketch
```

Better default:

```text
start top-face sketch
convert/offset references
trim/delete temporary references
dimension final slot profile
validate fully constrained
cut_extrude
```

Reason: the final feature is driven by a clean sketch, while face-derived geometry only helps locate it.

### Smooth Reducer

Bad default:

```text
stack several extrudes and fillets to fake a transition
```

Better default:

```text
ordered profile sketches on datum or offset planes -> loft
```

Reason: the shape is a multi-section transition, not a stack of prismatic steps.

## Ask Or Decide

Decide automatically when:

- the missing value is a harmless default, such as a preview export or a conventional plane choice;
- multiple strategies produce the same engineering intent but one is clearly simpler and already tested;
- the user describes a standard geometry class, such as shaft, plate, pipe, slot, flange, or transition.

Ask the user when:

- a missing dimension changes fit or manufacturability;
- a feature could be either additive or subtractive;
- a slot, hole, or datum reference is ambiguous;
- the function of a hole, slot, groove, face, fillet, or chamfer is unclear;
- a mating interface or fit type changes the feature shape, tolerance expectation, or modeling method;
- the user may expect a manufacturing process, such as turning vs milling;
- the drawing or model can be interpreted in multiple valid 3D ways.

Use this concrete workflow before execution:

1. Classify each uncertainty as harmless default, engineering assumption, or blocker.
2. Apply harmless defaults directly and record them in `semantic_assumptions` or feature parameters.
3. Convert engineering assumptions into a clear recommended default when the model can still be useful.
4. Stop and ask only for blockers: missing fit-critical dimensions, ambiguous feature function, unclear datum/target face, or unsupported compile path.
5. Keep questions short and grouped by effect: function first, then size, then reference.
6. After the user answers, update the Feature Plan and re-run `draft-job` / `run-nl`; do not patch the generated primitive list by hand unless the Feature Plan changed too.

Question examples:

- Slot: "这个槽是调节长孔、避让槽、导向槽还是密封槽？如果是调节长孔，我默认用贯穿切除并按中心对称布置。"
- Hole: "这个孔是螺栓过孔、螺纹孔、定位销孔还是轴承孔？不同用途会改变孔径、配合和建模方法。"
- Face/datum: "这个特征做在哪个面上？如果没有特殊要求，我默认放在最大上表面，并从零件中心定位。"
- Fillet/chamfer: "这个圆角/倒角是去锐边、装配导向还是应力过渡？如果只是去锐边，我默认作为后处理特征。"

Do not ask broad questions such as "还有什么要求？" when the blocker is specific. Ask for the exact missing engineering decision.

## Summary Metadata Recommendation

The project now includes a lightweight local strategy planner. Use it before generating Primitive DSL when the request starts as natural language:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py plan-strategy "做一个带中心孔和环形槽的阶梯轴，直径40，长度120"
```

The planner is metadata only. It chooses a modeling family, lists recommended primitive operation types, records assumptions, and reports missing parameters. It does not replace the Agent, validators, or SolidWorks executor.

The next layer is `plan-features`, which converts a supported request into an inspectable `feature_plan.v1`:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py plan-features "做一个安装板，长120宽80厚8，四角孔孔径8，孔边距15，材料6061铝"
```

The Feature Plan is the stable handoff layer. It is where the Agent records dominant geometry, engineering context, feature roles, modeling-method reasons, sketch strategies, parameters, references, questions, warnings, and missing capabilities. It should be expanded by adding reusable semantic fields, feature kinds, and compiler rules, not by adding a new one-off generator for every named part.

`draft-job` / `run-nl` then compile a supported Feature Plan into an executable `primitive_part` job:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run-nl "做一个阶梯轴，总长120，最大直径40，左段直径30长度40，右段直径20长度30，中心孔直径10贯穿，材料45钢" --backend solidworks
```

The supported Feature Plan compiler scope is still controlled, but now covers two common geometry families:

- rotational: stepped shafts, simple cylinders, washers, and through center bores;
- prismatic: basic plates/blocks, mounting plates, center holes, and four-corner hole patterns.

This is enough to prove the product loop across more than one modeling strategy:

```text
Chinese request
-> strategy planner chooses rotational or prismatic modeling from function, context, and geometry
-> Feature Plan records engineering context, feature roles, parameters, references, and missing capabilities
-> compiler emits primitive_part JSON
-> validators check the generated job
-> SolidWorks executes revolve/cut_revolve or extrude/cut_extrude
-> summary records fully constrained sketches and exports
```

If the request includes unsupported features such as annular grooves, generic slots/pockets, fillets, chamfers, countersinks, or threads, do not silently omit them. Return a question/warning, or extend the Feature Plan family and compiler rule before execution.

Include strategy metadata in the generated job or execution summary:

```json
{
  "modeling_strategy": {
    "dominant_geometry": "rotational",
    "chosen_strategy": "revolve_then_cut_revolve",
    "alternatives_considered": ["stacked_extrudes"],
    "selection_reason": "Rotational part with editable shaft shoulders and center bore.",
    "assumptions": ["units_mm", "front_plane_section"]
  }
}
```

This makes Agent decisions inspectable and keeps later generated CAD JSON traceable to the strategy choice.

## Product Optimization

The current implementation has a first-pass planning layer before validation:

```text
natural language
-> strategy candidates
-> strategy score
-> Feature Plan
-> Primitive DSL
-> existing validators and SolidWorks executor
```

Keep this layer small and inspectable. It should guide strategy selection and missing-parameter checks, while the Feature Plan compiler writes the actual `primitive_part` JSON and the existing validators/SolidWorks executor remain responsible for execution quality.
