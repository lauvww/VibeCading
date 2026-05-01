# Sweep And Guide-Curve Stage

Use this reference when continuing VibeCading sweep development or diagnosing SolidWorks sweep failures.

## Background

This stage extended the Primitive DSL from basic `sweep` into a more complete path-driven modeling workflow:

```text
natural language path-driven intent
-> constrained path sketch
-> constrained profile sketch
-> optional guide curve / twist / cut behavior
-> SolidWorks sweep feature
-> SLDPRT / STEP / SVG / PDF / summary.json
```

The main lesson is that SolidWorks sweep success depends on explicit sketch relationships, not visual intersection. Guide-curve sweeps especially require `pierce` relations between the profile sketch and both the path and guide curves.

## Goal

Let the agent model path-driven features from natural language:

- pipes, handles, rails, wires, curved ribs: `sweep`
- curved bores, oil passages, wiring channels, tube hollowing: `cut_sweep`
- bent sweep paths: `add_arc` plus line/arc constraints
- twisted bars or shaped rails: `twist_control` and `twist_angle`
- guide-controlled or variable-section sweeps: `guide_curves` plus profile `pierce` relations

## Scope

Implemented and SolidWorks-tested:

- `add_arc`
- `cut_sweep`
- `sweep` with a circular profile and polyline path
- line-arc-line sweep path
- swept cut along a matching arc path
- constant twist sweep
- single guide-curve / variable-section sweep using explicit `pierce` relations

Still future work:

- multiple guide curves
- more complex 3D guide paths
- connector-point control
- guide-curve loft
- feature-level editing after creation

## Stable Primitive Pattern

For a normal sweep:

1. `start_sketch` for the path.
2. Add path geometry with `add_polyline` and optionally `add_arc`.
3. Add constraints, dimensions, and `validate_fully_constrained`.
4. `finish_sketch` for the path.
5. `start_sketch` for the profile.
6. Add profile geometry.
7. Add constraints, dimensions, and `validate_fully_constrained`.
8. Call `sweep`.

For `cut_sweep`, use the same pattern but call `cut_sweep`.

## Arc Path Rules

Use `add_arc` for bends:

```json
{
  "type": "add_arc",
  "parameters": {
    "sketch": "外管圆弧路径草图",
    "center": [50, 20],
    "start": [50, 0],
    "end": [70, 20],
    "direction": "counterclockwise"
  }
}
```

For a stable line-arc-line path:

- line endpoint `coincident` with arc start;
- arc end `coincident` with next line start;
- add `tangent` between line and arc when smoothness matters;
- dimension line lengths, arc center, and radius;
- validate the path sketch before closing it.

## Guide-Curve Rules

A guide-curve sweep must explicitly connect guide/path/profile. Do not rely on geometry that merely looks intersecting.

Stable profile-sketch pattern:

1. Create the path sketch and `finish_sketch`.
2. Create the guide-curve sketch and `finish_sketch`.
3. Start the profile sketch.
4. Add the section geometry.
5. Add a profile point on the section where the guide curve should control the profile.
6. Add `pierce` between the profile center and the path curve.
7. Add `coincident` between the profile control point and the section geometry.
8. Add `pierce` between the profile control point and the guide curve.
9. Dimension the section.
10. Validate the profile sketch.
11. Call `sweep` with `guide_curves`.

Example feature:

```json
{
  "type": "sweep",
  "parameters": {
    "profile": "导向变截面圆形截面草图",
    "path": "导向扫描路径草图",
    "guide_curves": ["扫描导向线草图"],
    "twist_control": "follow_path",
    "section_control": {
      "mode": "guide_curves"
    },
    "merge": true
  }
}
```

## SolidWorks Details

Important implementation details:

- `pierce` must map to SolidWorks `sgATPIERCE`, not `sgPIERCE`.
- Sweep selection marks are:
  - profile: `1`
  - guide curve: `2`
  - sweep path: `4`
- For guide curves, select sketch curve entities when available before falling back to selecting the whole sketch.
- `InsertProtrusionSwept4` is used for `sweep`.
- `InsertCutSwept5` is used for `cut_sweep`.

## Verified Examples

Use these examples as regression references:

- `examples/advanced/中文扫描把手测试.json`: basic additive sweep.
- `examples/advanced/中文圆弧扫描切除测试.json`: line-arc-line path, outer sweep, inner `cut_sweep`.
- `examples/advanced/中文扭转扫描测试.json`: 90 degree constant twist sweep.
- `examples/advanced/中文导向线变截面扫描测试.json`: guide-curve / variable-section sweep with explicit `pierce` relations.

The guide-curve example generated:

- `中文导向线变截面扫描测试件.SLDPRT`
- `中文导向线变截面扫描测试件.STEP`
- `中文导向线变截面扫描测试件_primitive.svg`
- `中文导向线变截面扫描测试件_report.pdf`
- `summary.json`

## Validation

Before reporting success:

1. Run JSON validation.
2. Run preview backend.
3. Run unit tests.
4. Run SolidWorks backend for any primitive that controls real CAD geometry.
5. Check `summary.json`:
   - `ok: true`
   - `cad_outputs_complete: true`
   - no errors
6. Confirm generated files exist and are non-empty.

Recommended commands:

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py validate .\examples\advanced\中文导向线变截面扫描测试.json
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\advanced\中文导向线变截面扫描测试.json --backend preview
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\advanced\中文导向线变截面扫描测试.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe -m unittest discover .\mcp-server\tests
```

## Failure Diagnosis

If a guide-curve sweep fails:

- Check whether the profile sketch has explicit `pierce` relations to both path and guide curve.
- Check whether `pierce` maps to `sgATPIERCE`.
- Check whether the guide curve is selected with mark `2`.
- Check whether the guide curve is selected as curve geometry, not only as a sketch name.
- Check whether the profile point lies on the profile section geometry.
- Check whether the profile sketch is fully constrained before calling `sweep`.
