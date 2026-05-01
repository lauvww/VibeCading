# Face-Derived Sketch Cleanup Stage

Use this reference when continuing the VibeCading sketch-editing workflow for open slots, edge notches, U-shaped cuts, face-derived grooves, or any feature where the sketch is built from existing model edges and then cleaned before the final cut.

## Stage Outcome

This stage turned sketch editing from isolated primitives into a reusable production workflow:

```text
natural-language edge/face intent
-> generated face selection
-> convert/offset reference geometry
-> trim/delete temporary sketch geometry
-> final dimensioned feature profile
-> fully constrained sketch check
-> cut/extrude feature
-> SLDPRT / STEP / SVG / PDF / summary.json
```

The key optimization is to use model-derived geometry as construction context, not as messy leftover feature-driving geometry. The final feature should be driven by a clean, dimensioned sketch.

## What Was Optimized

- Added a SolidWorks-tested open-slot workflow using existing primitives instead of a dedicated product function.
- Proved `convert_entities` and `offset_entities` can locate a new feature from a generated face boundary.
- Proved `trim_entities` can represent a real engineer's trim click with `trim_point`.
- Proved `delete_entities` can remove converted loops, offset loops, and temporary centerlines before final feature creation.
- Kept the final cut profile fully constrained before `cut_extrude`.
- Preserved Chinese job names, part names, operation ids, and output filenames.

## Stable Workflow

Use this sequence for open slots, edge notches, and similar cuts entering from an existing model edge:

1. Build the base solid with a fully constrained sketch.
2. Start a new sketch on the target generated face with `start_sketch_on_face`.
3. Project the face boundary with `convert_entities`; use `prefer_native=false` for the current tested path.
4. Add `offset_entities` when an inset reference, margin, or edge clearance helps locate the feature.
5. Add temporary centerlines or construction segments only when they encode useful engineering intent.
6. Use `trim_entities` when a real trim operation is needed; provide `trim_point` or `pick_points`.
7. Use `delete_entities` to remove temporary projected, offset, or construction geometry that should not remain in the final contour.
8. Create the final feature-driving profile with dimensions and geometric relations.
9. Run `validate_fully_constrained`.
10. Run `cut_extrude` or the intended feature.

## Natural-Language Mapping

Map these phrases to this workflow:

- "开口槽"
- "边缘缺口"
- "U 形槽"
- "从边上切进去的槽"
- "沿上表面边界定位一个槽"
- "根据外轮廓内缩后做切口"
- "先引用边界再修剪草图"

Do not add a new SolidWorks function for each of these product words. Emit reusable primitive operations.

## Example Pattern

The SolidWorks-tested example is `examples/中文开口槽工作流测试.json`.

It performs:

- base rectangle sketch and `extrude`
- top face selection through `start_sketch_on_face`
- outer loop projection through `convert_entities`
- inward reference offset through `offset_entities`
- temporary centerline and `trim_entities`
- cleanup with `delete_entities`
- final dimensioned cut rectangle
- `validate_fully_constrained`
- `cut_extrude`

The SolidWorks run generated:

- `中文开口槽工作流测试件.SLDPRT`
- `中文开口槽工作流测试件.STEP`
- `中文开口槽工作流测试件_primitive.svg`
- `中文开口槽工作流测试件_report.pdf`
- `summary.json`

## Rules

- Keep `convert_entities` with `prefer_native=false` for production examples until native COM conversion exposes generated segments reliably.
- Treat projected and offset loops as references unless they are intentionally part of the final closed contour.
- Do not leave temporary converted loops, offset loops, or centerlines in the feature-driving sketch by accident.
- Use `trim_entities` for trim semantics and `delete_entities` for explicit cleanup semantics; do not substitute one blindly for the other.
- Treat trim as a pick-location action. Entity ids are not enough; include `trim_point` or one `pick_points` entry per trim target.
- Validate the final sketch after cleanup, not only the earlier reference sketch.
- Avoid `fixed` for production geometry. Use dimensions and relations; use fixed points only as minimal datum/reference anchors.

## Validation

Before reporting this workflow as complete:

1. Run JSON validation.
2. Run preview for cheap structural checks.
3. Run unit tests after DSL, validator, preview, or executor changes.
4. Run SolidWorks backend for any new trim/delete/convert/offset behavior.
5. Confirm `summary.json` has `ok: true`.
6. Confirm `cad_outputs_complete: true`.
7. Confirm every feature-driving sketch reports `fully_constrained`.
8. Confirm all requested CAD artifacts exist and are non-empty.

Recommended commands:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py validate .\examples\中文开口槽工作流测试.json
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文开口槽工作流测试.json --backend preview
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\中文开口槽工作流测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe -m unittest discover .\mcp-server\tests
```

## Next Work

The next useful extension is not another product-specific slot function. Extend the same workflow toward:

- construction geometry flags instead of delete-after-use for references that should remain but not drive features;
- more robust relation-based positioning from converted edges;
- partially open contours and multi-boundary trims;
- feature-level fillet, chamfer, mirror, and pattern primitives after sketch-level workflows are stable.
