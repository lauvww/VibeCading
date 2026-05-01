# Sketch Tools Stage Summary

Use this reference when the user asks to continue SolidWorks sketch-level automation, add sketch editing primitives, or explain how VibeCading should translate natural language into editable engineering sketches.

## Stage Outcome

This stage moved VibeCading beyond simple sketch creation into production-oriented sketch editing:

```text
natural language sketch intent
-> sketch strategy
-> constrained geometry / sketch edit primitives
-> full-definition check
-> feature operation
-> SLDPRT / STEP / SVG / PDF / summary.json
```

The important product decision is unchanged: do not let the agent emit arbitrary SolidWorks macros. Add reusable Primitive DSL operations, validate them, and run them through the SolidWorks Primitive Executor.

## Built Sketch Capabilities

- Sketch-level fillet and chamfer:
  - `sketch_fillet`
  - `sketch_chamfer`
- Sketch-level repeated geometry:
  - `add_mirrored_circle`
  - `add_circle_linear_pattern`
- Fully defined slot, polygon, and spline workflows:
  - `add_straight_slot`
  - `add_polygon`
  - `add_spline`
  - `fully_define_sketch`
- Existing-model edge driven sketches:
  - `convert_entities`
  - `offset_entities`
  - `trim_entities`
  - `delete_entities`

The latest SolidWorks-tested workflows cover both inset grooves and edge-notches: build a base plate, start a sketch on a generated top face, convert/project the face loop, offset or use it as a construction reference, clean temporary geometry with trim/delete operations, validate the final feature-driving sketch as fully constrained, then cut the requested geometry. This keeps reference geometry explicit instead of hiding sketch cleanup inside extra modeling features.

## Natural-Language Mapping

Use these mappings when interpreting user CAD requests:

- "圆角草图", "轮廓圆角", "草图内倒圆": create and dimension the base sketch first, then use `sketch_fillet`.
- "倒角窗口", "草图倒角", "矩形孔倒角": create and dimension the base sketch first, then use `sketch_chamfer`.
- "对称孔", "镜像孔": use a centerline plus `add_mirrored_circle`.
- "一排孔", "等距孔", "孔阵列": use `add_circle_linear_pattern` when the holes belong to one sketch.
- "直槽口", "腰形孔": use `add_straight_slot`; for production constraints prefer `definition_mode=dimensioned_geometry` and `fully_define=true`.
- "多边形孔", "六角孔": use `add_polygon`; for production constraints use `fully_define=true`.
- "样条曲线", "自由曲线", "控制曲线": use `add_spline` with `create_fit_point_refs=true`, then add dimensions and relations to fit points.
- "沿已有边线", "引用边线", "从面边界内缩", "密封槽", "边缘浅槽", "轮廓等距": use `convert_entities` followed by `offset_entities`.
- "剪裁", "修剪", "去掉多余线段", "清理交点", "强力剪裁": use `trim_entities`. Always include a pick point near the portion to trim because SolidWorks trim is not determined by entity id alone.
- "删除临时线", "去掉辅助线", "删除多余引用线": use `delete_entities` for explicit sketch cleanup before continuing with trim or feature creation.
- "开口槽", "边缘缺口", "U 形槽", "从边上切进去的槽": use face-loop conversion and optional offset references to locate the notch, delete temporary reference geometry, then create a dimensioned cut profile and run `cut_extrude`.

## Constraint Discipline

Do not use `fixed` to hide missing design intent. Use this order:

1. Create a minimal datum point or centerline only when needed.
2. Add geometry.
3. Add geometric relations such as horizontal, vertical, coincident, tangent, curvature, pierce, mirror, or pattern relations.
4. Add driving dimensions.
5. Use `fully_define_sketch` only as a residual pass after the intended dimensions and relations exist.
6. Run `validate_fully_constrained` before the feature operation.

For splines, fit-point dimensions and endpoint constraints are the design intent. `fully_define_sketch` is only for residual SolidWorks spline degrees of freedom such as handles or curve shape. Pass a fixed `datum` point and keep `relation_mask=1023`.

## Convert And Offset Pattern

Use this pattern for grooves, lips, gasket paths, and inset rims derived from an existing model face:

```json
{
  "type": "convert_entities",
  "parameters": {
    "sketch": "上表面等距槽草图",
    "target": {
      "type": "body_face_edges",
      "feature": "拉伸_基板",
      "normal": [0, 0, 1],
      "position": "max",
      "area": "largest",
      "loop": "outer"
    },
    "prefer_native": false
  }
}
```

Then offset the resulting group:

```json
{
  "type": "offset_entities",
  "parameters": {
    "sketch": "上表面等距槽草图",
    "source": {
      "type": "profile",
      "id": "转换_上表面外轮廓"
    },
    "offset": 8,
    "direction": "inside",
    "chain": true,
    "add_dimensions": true
  }
}
```

Current tested SolidWorks path: set `prefer_native=false`. Native `SketchUseEdge` / `ConvertEntities` can report success without exposing created sketch segments through COM. The executor's tested path reads the planar face loop, projects its edge endpoints into editable sketch segments, then offsets those segments.

## Trim Pattern

Use `trim_entities` after temporary construction, projected edges, or offset contours create extra sketch segments. The most stable first mode for agent-generated jobs is `entity_point`, where the agent gives both the entity reference and a `trim_point` near the side to remove:

```json
{
  "type": "trim_entities",
  "parameters": {
    "sketch": "上表面剪裁草图",
    "mode": "entity_point",
    "entities": [
      {
        "type": "profile_segment",
        "profile": "待剪裁水平中心线",
        "index": 0
      }
    ],
    "trim_point": [55, 0]
  }
}
```

Supported mode aliases:

- `closest` / `trim_to_closest`
- `corner`
- `two_entities` / `to_entity`
- `entity_point` / `point`
- `power` / `power_trim` / `entities`
- `inside` / `trim_away_inside`
- `outside` / `trim_away_outside`

Use `pick_points` for `power`, and provide one point for each entity. For `corner` and `two_entities`, pick points are optional but recommended when two possible intersections or trim sides exist.

For boundary-based trim, prefer the structured form instead of a flat entity list:

```json
{
  "type": "trim_entities",
  "parameters": {
    "sketch": "边界内侧剪裁草图",
    "mode": "inside",
    "boundary_entities": [
      {"type": "profile_segment", "profile": "左侧剪裁边界", "index": 0},
      {"type": "profile_segment", "profile": "右侧剪裁边界", "index": 0}
    ],
    "trim_targets": [
      {"type": "profile_segment", "profile": "被内侧剪裁水平线", "index": 0}
    ],
    "boundary_pick_points": [[-22, 0], [22, 0]],
    "trim_pick_points": [[0, 0]]
  }
}
```

SolidWorks native `power` trim can be unstable through COM. The executor tries native power trim first, then falls back to repeated `entity_point` trim using `trim_pick_points`. Keep one pick point per target.

Use `delete_entities` when the sketch includes temporary construction or reference segments that should not remain in the feature-driving sketch:

```json
{
  "type": "delete_entities",
  "parameters": {
    "sketch": "强力剪裁草图",
    "entities": [
      {
        "type": "profile",
        "id": "待删除临时草图线"
      }
    ]
  }
}
```

## Open Slot / Edge Notch Pattern

Use this pattern when a user asks for an open slot, edge notch, U-shaped cut, or a slot cut in from a model edge:

1. Create the base feature and start a sketch on the target generated face.
2. Use `convert_entities` and, when useful, `offset_entities` to create reference geometry from the existing face boundary.
3. Use `trim_entities` only when the engineering action is actually a trim; use `delete_entities` to remove temporary projected, offset, or centerline references that should not drive the final feature.
4. Create the final closed cut profile with dimensions and geometric relations.
5. Run `validate_fully_constrained`.
6. Run `cut_extrude`.

The SolidWorks-tested example is `examples/sketch/中文开口槽工作流测试.json`. It proves that a face-derived reference workflow can be used during sketch construction, then cleaned before the final feature-driving rectangle is cut from the plate edge.

## SolidWorks Lessons

- Use `_maybe_call`-style compatibility helpers because pywin32 may expose COM members as properties or methods.
- Do not call `EditRebuild3` while an active sketch is being edited. It can break sketch-edit state before conversion, offset, or manual projection.
- When selecting generated faces, filter by feature id, normal, min/max position, area, and area rank.
- For edge-loop projection, read edge start and end vertices instead of relying only on curve parameter arrays.
- Register generated sketch segments under the operation id so later operations can reference them as a group.
- Treat `convert_entities` with `prefer_native=false` as a controlled projection, not a persistent topological external reference.
- Treat `trim_entities` as a pick-point operation. The DSL must preserve where the engineer clicked, not only which sketch segment was selected.
- For `inside` / `outside`, keep boundary entities separate from trim targets. This makes natural-language plans clearer and avoids relying on ambiguous entity ordering.
- For `power`, expect `method=entity_point_fallback` in `summary.json` when native batch trim fails. This is acceptable if the requested sketch cleanup and exports succeed.
- Use `delete_entities` for explicit cleanup rather than hoping unused sketch segments are ignored by later features.
- For open slots and edge notches, do not leave converted or offset loops in the same sketch unless they are intentionally part of the final closed contour. Use them as references, clean them, then build the final dimensioned cut profile.
- Run real SolidWorks tests for every sketch-edit primitive. Preview can validate structure but cannot prove CAD edit behavior.

## Verified Examples

- `examples/sketch/中文草图优化测试.json`: sketch fillet, sketch chamfer, mirrored holes, and linear circular sketch pattern.
- `examples/sketch/中文槽口多边形样条测试.json`: straight slot, polygon, spline fit-point references, fit-point dimensions, and `fully_define_sketch`.
- `examples/sketch/中文转换实体等距切槽测试.json`: projected face loop, inward offset, full-definition check, and shallow groove cut.
- `examples/sketch/中文草图剪裁测试.json`: projected face loop, overhanging line, and `trim_entities` entity-point trim using an explicit trim point.
- `examples/sketch/中文草图复杂剪裁测试.json`: boundary-based inside trim, outside trim, explicit `delete_entities`, and power trim with entity-point fallback, all verified through SolidWorks export.
- `examples/sketch/中文开口槽工作流测试.json`: generated top-face sketch, converted outer loop, inward offset reference, trim/delete cleanup, final dimensioned open-slot cut, and fully constrained sketches verified through SolidWorks export.

## Current Limits

- `trim_entities` currently exposes SolidWorks trim modes and explicit pick points. Inside, outside, power trim, and one open-slot cleanup workflow now have SolidWorks-tested samples, but complex closed-contour trimming after offset workflows still needs more production examples.
- Native associative Convert Entities behavior is not guaranteed in the current COM path. The tested default for production examples is projection into editable segments.
- Sketching directly on cylindrical or non-planar faces is still a future capability.
- Complex spline control handles, curvature combs, and manufacturing-grade curvature continuity still need deeper primitives beyond fit-point dimensions and relation aliases.

## Validation Checklist

Before reporting a sketch feature as complete:

1. Run JSON validation.
2. Run preview for cheap structural checks.
3. Run unit tests after validator or executor changes.
4. Run SolidWorks backend when the primitive edits CAD geometry.
5. Confirm every feature-driving sketch reports `fully_constrained`.
6. Confirm `summary.json` has `ok: true`.
7. Confirm requested SLDPRT / STEP / SVG / PDF artifacts exist and `cad_outputs_complete` is true.
