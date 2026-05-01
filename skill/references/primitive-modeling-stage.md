# Primitive Modeling Stage Summary

Use this reference when continuing the SolidWorks-first part-modeling stage or explaining how the current VibeCading primitive workflow works.

## Stage Outcome

The project moved from dedicated feature functions to a general Primitive DSL plus SolidWorks Primitive Executor.

The stable direction is:

```text
natural language intent
-> upper CAD template when useful
-> primitive_part operations
-> SolidWorks Primitive Executor
-> SLDPRT / STEP / SVG / PDF / summary.json
```

Upper templates such as `mounting_plate` and `l_bracket` are examples. They should compile into primitive operations instead of calling product-specific SolidWorks builders.

## What Was Built

- `PrimitiveOperation` and `PrimitivePart` were added to the CAD DSL.
- `template_compiler.py` compiles `mounting_plate` and `feature_part/l_profile_extrude` into `primitive_part`.
- `SolidWorksPrimitiveExecutor` executes the primitive operations through COM.
- The preview backend can summarize and render primitive jobs without pretending to create real CAD geometry.
- The runner, server tools, validators, examples, and tests support direct `primitive_part` jobs.

## Current Primitive Set

- `start_sketch`: start a sketch on the default base plane.
- `start_sketch_on_face`: start a sketch on a generated model face selected by normal, min/max position, optional feature id, optional area rank, or a previously named face.
- `finish_sketch`: close a fully constrained sketch so a later feature can select it together with another sketch.
- `tag_face`: select a generated planar face and store it under a user-facing name for later sketch operations.
- `create_offset_plane`: create a named reference plane offset from a selected planar face or an original datum plane.
- `add_polyline`: create an open or closed line profile.
- `add_arc`: create a circular arc for sweep paths or curved sketch geometry.
- `add_center_rectangle`: create a rectangular profile by center and size.
- `add_chamfered_rectangle`: create a closed chamfered rectangle profile directly in the sketch; use it as a fallback for direct closed profiles.
- `add_straight_slot`: create a SolidWorks straight slot from center, length, width, and angle.
- `add_polygon`: create a regular polygon from center, radius, side count, and angle.
- `add_spline`: create an open or closed spline through fit points.
- `add_circle`: create a circle by center and diameter.
- `add_mirrored_circle`: create a source circle and mirrored sketch copy around a centerline.
- `add_circle_linear_pattern`: create repeated circular sketch geometry from one source circle.
- `add_point`: create a reference sketch point.
- `add_centerline`: create a sketch centerline for future axis/path workflows.
- `add_axis_constraints`: add horizontal/vertical relations to profile segments.
- `add_relation`: currently supports `fixed`, `horizontal`, `vertical`, `coincident`, `tangent`, `curvature`, `equal_curvature`, and `pierce`.
- `add_dimensions`: add entity, horizontal-between, and vertical-between dimensions.
- `sketch_fillet`: apply a sketch fillet before the feature operation is created.
- `sketch_chamfer`: apply a SolidWorks sketch chamfer after the base sketch is constrained and dimensioned.
- `fully_define_sketch`: ask SolidWorks to complete residual sketch definition after explicit driving dimensions and relations are already present. Pass a fixed `datum` point when available. Default `relation_mask=1023` enables all local SolidWorks full-define relation flags. Treat it as a final pass for spline handle/shape degrees of freedom, not as a shortcut around planned dimensions.
- `convert_entities`: convert or project model face edges into the active sketch. Use it when the next sketch should derive from an existing generated face or edge loop.
- `offset_entities`: offset a referenced sketch entity group by a driving distance. Use it after `convert_entities` for grooves, lips, gasket paths, inner rims, and contour offsets.
- `validate_fully_constrained`: fail the job unless SolidWorks reports the active sketch is fully constrained.
- `extrude`: create additive extrusion from the active sketch.
- `cut_extrude`: create subtractive extrusion from the active sketch.
- `revolve`: create additive rotational geometry from a fully constrained section and axis.
- `cut_revolve`: create subtractive rotational geometry from a fully constrained section and axis.
- `sweep`: create additive path-driven geometry from one fully constrained profile sketch and one fully constrained path sketch.
- `cut_sweep`: create subtractive path-driven geometry from one fully constrained profile sketch and one fully constrained path sketch.
- `loft`: create additive blended geometry from ordered fully constrained profile sketches.
- `cut_loft`: create subtractive blended geometry from ordered fully constrained cut profile sketches.

## Verified Examples

Use these examples as regression references:

- `examples/basic/primitive_l_bracket.json`: direct primitive L bracket.
- `examples/primitives/multi_feature_test_part.json`: multiple additive features from separate sketches.
- `examples/primitives/multi_feature_cut_test_part.json`: additive features plus independent `cut_extrude` holes.
- `examples/primitives/complex_fixture_plate.json`: complex fixture plate with 56 primitive operations, 4 extrudes, 2 cuts, 6 holes, and 2 rectangular slots.
- `examples/primitives/face_reference_test_part.json`: generated-face workflow; build base, select base top face by feature id and area, build boss, tag the boss top face, then cut a hole from that named face.
- `examples/primitives/中文命名偏置基准面测试.json`: Chinese naming and offset-plane workflow; build a base, tag its top face, create a named offset reference plane, sketch on that plane, then cut a hole.
- `examples/primitives/中文旋转轴测试.json`: revolve workflow; build a fully constrained half-section profile, use one profile segment as the rotational axis, then create a 360 degree revolved body.
- `examples/primitives/中文旋转切除测试.json`: cut-revolve workflow; create a revolved cylindrical body on the original front datum, then create a fully constrained revolve-cut section on the same datum and cut a center bore.
- `examples/advanced/中文扫描把手测试.json`: sweep workflow; create and finish a constrained path sketch, create a constrained circular profile sketch, then sweep the profile along the path.
- `examples/advanced/中文圆弧扫描切除测试.json`: arc path plus `cut_sweep`; create an outer swept tube, then sweep-cut the inner bore along a matching arc path.
- `examples/advanced/中文扭转扫描测试.json`: constant-twist sweep; create a constrained rectangular profile and sweep it with a 90 degree twist.
- `examples/advanced/中文导向线变截面扫描测试.json`: guide-curve / variable-section sweep. The profile sketch explicitly pierces the path and guide curve, and the SolidWorks run generates SLDPRT, STEP, SVG, PDF, and a complete summary.
- `examples/advanced/中文放样过渡管测试.json`: additive loft; creates offset datum planes from the original front plane, builds three fully constrained circular profile sketches, then lofts them into a transition body.
- `examples/advanced/中文放样切除测试.json`: cut loft; creates a base block, builds three fully constrained circular cut profiles through the body, then creates a tapered internal passage with `cut_loft`.
- `examples/sketch/中文草图优化测试.json`: sketch-level optimization; creates sketch fillets, a chamfered cut profile, mirrored holes, and linearly patterned circular sketch geometry before creating the 3D features.
- `examples/sketch/中文转换实体等距切槽测试.json`: convert/project a generated top-face outer loop, offset it inward, fully define the derived groove sketch, and cut a shallow perimeter groove.

All of these should validate. The SolidWorks-tested examples generated SLDPRT, STEP, SVG, PDF, and a complete summary when SolidWorks was available.

## Modeling Method

For a new part:

1. Split the part into ordered features.
2. For each sketch, choose a plane:
   - use `start_sketch` for the initial base plane;
   - use `start_sketch_on_face` for a face generated by earlier features.
   - use `create_offset_plane` followed by `start_sketch` when the sketch should be built on a reference plane offset from a generated face or original datum plane.
3. Add geometry primitives.
4. Add axis relations, geometric constraints, and driving dimensions. Use `fixed` only for minimal origin/reference anchors.
5. Add driving dimensions.
6. For spline-heavy sketches, add `fully_define_sketch` only after the intended fit-point dimensions and endpoint/tangent/curvature relations are already present.
7. Add `validate_fully_constrained`.
8. Add `extrude`, `cut_extrude`, `revolve`, or another feature primitive.
9. Repeat for the next feature.

## Natural-Language Feature Strategy

Natural language can drive multiple modeling methods when the agent first converts the request into an explicit feature strategy:

- Use `extrude` when the user describes plates, blocks, bosses, pads, ribs, pockets, slots, and prism-like geometry.
- Use `cut_extrude` when the user describes through holes, blind holes, windows, pockets, and slots cut normal to a sketch plane.
- Use `revolve` when the user describes shafts, bushings, pulleys, spacers, washers, knobs, cones, cylinders, grooves, or lathe-like geometry.
- Use `cut_revolve` when the user describes center bores, annular grooves, relief cuts, countersunk rotational cuts, or lathe-style subtractive geometry.
- Use `sweep` when one section follows one path, such as pipes, handles, rails, wires, simple curved ribs, and path-driven round or rectangular sections.
- Use `cut_sweep` when a cutter section follows a path, such as curved grooves, swept bores, wiring channels, oil passages, or tube hollowing.
- Use `loft` when geometry blends between multiple ordered sections, such as ducts, transitions, aerodynamic covers, tapered shells, or organic housings.
- Use `cut_loft` when a subtractive passage blends between multiple ordered sections, such as tapered bores, reducer channels, multi-section ports, or inlet/outlet transitions.
- Use sketch-level primitives when a fillet, chamfer, mirror, or pattern is naturally part of one sketch and would otherwise add avoidable feature-tree clutter.

Do not let the agent jump from natural language directly to SolidWorks macros. The agent should pick the modeling method, create constrained sketches and references, then emit Primitive DSL.

## Revolve

The SolidWorks-tested revolve path uses a fully constrained section and one profile segment as the axis:

```json
{
  "type": "revolve",
  "parameters": {
    "sketch": "旋转草图",
    "axis": {
      "type": "profile_segment",
      "profile": "旋转截面",
      "index": 3
    },
    "angle": 360
  }
}
```

For stable engineering output, locate the section with a minimal reference anchor plus driving dimensions before `validate_fully_constrained`. Avoid fixing production sketch geometry just to force a fully constrained status.

## Revolve Cut

Use `cut_revolve` for subtractive rotational features. The sketch plane may come from several sources:

- original datum plane: `front`, `top`, `right`, or their Chinese SolidWorks names;
- generated planar face: use `start_sketch_on_face`;
- offset reference plane: use `create_offset_plane` first, then `start_sketch` with the plane name.

SolidWorks-tested pattern:

```json
{
  "type": "cut_revolve",
  "parameters": {
    "sketch": "中心孔旋转切除草图",
    "axis": {
      "type": "profile_segment",
      "profile": "中心孔切除截面",
      "index": 3
    },
    "angle": 360
  }
}
```

Keep the cut section fully constrained before calling `cut_revolve`. For a center bore, the cut section can touch the rotation axis and revolve into the removed cylindrical volume.

Do not draw a large unconstrained profile just because it looks right. Every engineering-critical location should come from a dimension or relation.

## Sweep

Use `sweep` for additive geometry where the user describes a section moving along a path. Current stable scope is one profile sketch plus one path sketch. The path should be created first, fully constrained, validated, and closed with `finish_sketch`. Then create and validate the profile sketch before calling `sweep`.

```json
{
  "type": "sweep",
  "parameters": {
    "profile": "圆管截面草图",
    "path": "把手扫描路径草图",
    "merge": true
  }
}
```

For stable SolidWorks behavior, put the profile plane at the path start and keep the profile normal to the first path direction when possible. A common stable pattern is a front-plane path that starts at the origin and a right-plane circular profile centered at the origin.

## Sweep Cut, Arc Paths, And Twist

`cut_sweep` follows the same sketch discipline as `sweep`, but creates subtractive geometry:

```json
{
  "type": "cut_sweep",
  "parameters": {
    "profile": "内孔截面草图",
    "path": "内孔圆弧路径草图",
    "twist_control": "follow_path"
  }
}
```

Use `add_arc` with `coincident` and `tangent` relations when a path contains a bend. The SolidWorks-tested arc workflow uses a line-arc-line path, validates it as fully constrained, then uses it for both an outer sweep and an inner swept cut.

Twist control is available through `twist_control` and `twist_angle`. The tested constant-twist pattern uses:

```json
{
  "type": "sweep",
  "parameters": {
    "profile": "扭转矩形截面草图",
    "path": "扭转扫描路径草图",
    "twist_control": "constant_twist",
    "twist_angle": 90
  }
}
```

`guide_curves` and `section_control` are now part of the DSL and executor selection path. For SolidWorks stability, do not rely on geometry that merely looks intersecting. Add explicit `pierce` relations inside the profile sketch:

- profile center point pierces the path curve;
- a profile point on the section pierces the guide curve;
- the profile point should also be constrained to the section geometry, for example coincident with a circle or profile edge.

The SolidWorks executor maps `pierce` to `sgATPIERCE` and selects guide curves by sketch curve entity with guide-curve mark `2`. This is the current stable pattern for guide-curve sweeps.

## Loft

Use `loft` for additive geometry where the user describes a transition between multiple sections. The current stable scope is ordered profile sketches, usually on original datum planes or named offset reference planes.

```json
{
  "type": "loft",
  "parameters": {
    "profiles": [
      "入口圆截面草图",
      "中间圆截面草图",
      "出口圆截面草图"
    ],
    "merge": true
  }
}
```

Stable workflow:

1. Create any needed offset reference planes from an original datum plane or known planar face.
2. Create one closed section sketch per profile.
3. Fully constrain and `finish_sketch` every profile sketch.
4. Call `loft` with profiles in the intended physical order.

The first tested SolidWorks loft example creates a 30 mm -> 22 mm -> 14 mm circular transition over 80 mm. It generated SLDPRT, STEP, SVG, PDF, and a complete summary.

The next loft work should add connector-point controls and guide-curve loft examples, because complex profile matching can twist or connect the wrong vertices if the order is ambiguous.

## Cut Loft

Use `cut_loft` for subtractive multi-section geometry. It follows the same profile discipline as `loft`, but it must operate on an existing solid body.

```json
{
  "type": "cut_loft",
  "parameters": {
    "profiles": [
      "入口切除截面草图",
      "中间切除截面草图",
      "出口切除截面草图"
    ]
  }
}
```

Stable workflow:

1. Create the base solid first.
2. Create datum or offset planes through the intended cut volume.
3. Create one closed cut section sketch per profile.
4. Fully constrain and `finish_sketch` every cut profile.
5. Call `cut_loft` with profiles in the physical inlet-to-outlet order.

The first tested SolidWorks cut-loft example cuts a 30 mm -> 20 mm -> 12 mm tapered passage through a 100 x 60 x 90 mm block. It generated SLDPRT, STEP, SVG, PDF, and a complete summary.

## Sketch-Level Optimization

Use sketch-level primitives when the engineering intent belongs inside the sketch:

- rounded profile corners: `sketch_fillet`
- chamfered rectangular windows or pockets: create a constrained base rectangle, then apply `sketch_chamfer`
- symmetric holes around a centerline: `add_mirrored_circle`
- repeated same-diameter sketch holes: `add_circle_linear_pattern`

The tested SolidWorks example builds a rounded rectangular plate, cuts a chamfered window, and cuts mirrored/patterned circular holes. The recommended pattern is to dimension the base sketch first, then use SolidWorks sketch commands for fillets and chamfers. All sketches in that example are fully constrained before feature creation.

Current caveat: `add_chamfered_rectangle` remains available as a direct closed-profile fallback, but it is no longer the recommended default for ordinary chamfers. Prefer a fully constrained base sketch followed by `sketch_chamfer`, matching normal SolidWorks modeling practice.

## Face Selection Principle

`start_sketch_on_face` supports two stable planar face-selection modes.

Mode 1: select a body face by feature id, normal, position, and area:

```json
{
  "type": "start_sketch_on_face",
  "parameters": {
    "sketch": "boss_sketch",
    "target": {
      "type": "body_face",
      "feature": "extrude_base",
      "normal": [0, 0, 1],
      "position": "max",
      "area": "largest",
      "area_rank": 0
    }
  }
}
```

The executor uses the earlier primitive feature id when provided, enumerates that feature's generated faces, filters planar faces by normal direction, groups by min/max position along the normal, then sorts the positional group by area.

Mode 2: name a face first, then reuse the name:

```json
{
  "type": "tag_face",
  "parameters": {
    "name": "boss_top_face",
    "target": {
      "type": "body_face",
      "feature": "extrude_boss",
      "normal": [0, 0, 1],
      "position": "max",
      "area": "largest"
    }
  }
}
```

```json
{
  "type": "start_sketch_on_face",
  "parameters": {
    "sketch": "hole_sketch",
    "target": {
      "type": "named_face",
      "name": "boss_top_face"
    }
  }
}
```

Use this for top, bottom, and side planar faces. Curved or cylindrical face sketching is still a separate future primitive.

## Offset Reference Plane

Use `create_offset_plane` when a later feature should be sketched from a construction plane instead of directly on the model face or original datum plane:

```json
{
  "type": "create_offset_plane",
  "parameters": {
    "name": "孔加工偏置基准面",
    "base": {
      "type": "named_face",
      "name": "底板顶面"
    },
    "offset": 5
  }
}
```

Then start the sketch by plane name:

```json
{
  "type": "start_sketch",
  "parameters": {
    "sketch": "偏置孔草图",
    "plane": "孔加工偏置基准面"
  }
}
```

Chinese names are valid for jobs, parts, operations, named faces, reference planes, and output files. Keep all project files UTF-8.

## Extension Rules

When adding a new capability:

1. Add a primitive only if it is reusable across many part templates.
2. Add validator coverage for required parameters and safe ranges.
3. Implement preview fallback metadata if possible.
4. Implement SolidWorks executor behavior.
5. Add at least one example JSON.
6. Add tests for validation and preview.
7. Run a real SolidWorks job when the new primitive controls CAD geometry.

Prefer future primitives such as:

- `fillet`
- `chamfer`
- `linear_pattern`
- `mirror`
- `hole_wizard`
- `loft_connector`
- `shell`

Avoid adding one-off operations that only model a single named product.
