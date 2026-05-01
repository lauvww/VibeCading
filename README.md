# VibeCading

VibeCading is a local AI automation workbench for mechanical CAD.

The first milestone is a conservative CAD Agent MCP flow:

1. AI turns a CAD request into a structured JSON job.
2. The local tool layer validates the job.
3. A CAD adapter executes the deterministic operation.
4. The runner returns generated files, validation status, and an execution log.

MVP-0 started with `mounting_plate`. The product path now uses a two-layer CAD DSL:

1. `mounting_plate` and `feature_part` stay as upper-level templates that are easier for an AI agent to fill from natural language.
2. Templates compile into `primitive_part` operations.
3. SolidWorks executes only the primitive operations, so new part templates do not require one new SolidWorks function per feature.

## Current Status

- Structured JSON job format for a mounting plate.
- Structured `feature_part` JSON format for controlled upper-level feature templates.
- Generic `primitive_part` JSON format for low-level sketch, constraint, dimension, and extrusion operations.
- Validation for units, dimensions, holes, and export formats.
- Local preview backend with SVG and PDF output.
- FreeCAD adapter scaffold that can export STEP when FreeCAD Python modules are available.
- SolidWorks COM adapter with a Primitive Executor for constrained sketches and extrusions.
- CLI entrypoint that can later be exposed through MCP.

The preview backend does not pretend to generate CAD geometry. If STEP is requested without a real CAD backend, the job summary marks it as unsupported.

## Run MVP-0

```powershell
python .\mcp-server\server.py run .\examples\basic\mounting_plate.json
```

Outputs are written under:

```text
outputs/jobs/<job-id>/
```

Run validation only:

```powershell
python .\mcp-server\server.py validate .\examples\basic\mounting_plate.json
python .\mcp-server\server.py validate .\examples\basic\l_bracket.json
python .\mcp-server\server.py validate .\examples\basic\primitive_l_bracket.json
```

Run tests:

```powershell
python -m unittest discover .\mcp-server\tests
```

## Example Layout

Runnable JSON examples are grouped by modeling scope:

```text
examples/basic/       entry examples and upper templates
examples/primitives/  direct primitive_part feature examples
examples/advanced/    sweep, cut sweep, twist, guide curve, loft, cut loft
examples/sketch/      sketch-level and face-derived cleanup workflows
```

Generated CAD files should stay under `outputs/jobs/`, not under `examples/`.

## SolidWorks Test

This project can use a project-local conda environment for SolidWorks automation. Recreate it from `environment.yml` when `.conda/` is not present:

```powershell
conda env create -p D:\VibeCading\.conda\VibeCading -f environment.yml
```

Then activate it:

```powershell
conda activate D:\VibeCading\.conda\VibeCading
```

Check the SolidWorks COM connection and local templates:

```powershell
python .\mcp-server\server.py sw-check
```

Run the mounting plate job with SolidWorks:

```powershell
python .\mcp-server\server.py run .\examples\basic\mounting_plate.json --backend solidworks
```

The SolidWorks backend creates a constrained source sketch before extrusion. The mounting plate sketch includes horizontal and vertical edge relations, a fixed origin reference point, overall length and width dimensions, center positioning dimensions, and per-hole diameter plus X/Y position dimensions. The run fails instead of silently exporting if SolidWorks reports the sketch is not fully constrained.

For production sketches, prefer driving dimensions and geometric relations over `fixed`. A fixed origin or reference anchor is acceptable, but generated holes, pattern copies, and other editable geometry should be fully defined by dimensions and relations.

Run the upper-level L-bracket template with SolidWorks:

```powershell
python .\mcp-server\server.py run .\examples\basic\l_bracket.json --backend solidworks
```

The L-bracket template compiles into primitive operations before SolidWorks runs it. The current primitive set is:

```text
start_sketch
start_sketch_on_face
finish_sketch
tag_face
create_offset_plane
add_polyline
add_arc
add_center_rectangle
add_chamfered_rectangle
add_straight_slot
add_polygon
add_spline
add_circle
add_mirrored_circle
add_circle_linear_pattern
add_point
add_centerline
add_axis_constraints
add_relation
add_dimensions
sketch_fillet
sketch_chamfer
fully_define_sketch
convert_entities
offset_entities
trim_entities
delete_entities
validate_fully_constrained
extrude
cut_extrude
revolve
cut_revolve
sweep
cut_sweep
loft
cut_loft
```

`feature_part` currently keeps `l_profile_extrude` as an upper-level template example. It is not executed directly by SolidWorks; it is compiled into primitive operations first.

`start_sketch_on_face` can now select generated planar faces with additional selectors:

```json
{
  "type": "body_face",
  "feature": "extrude_base",
  "normal": [0, 0, 1],
  "position": "max",
  "area": "largest",
  "area_rank": 0
}
```

- `feature` / `feature_id` limits the search to faces generated by an earlier primitive feature.
- `area` accepts `largest` or `smallest` after the min/max position filter.
- `area_rank` selects the nth face inside the filtered group.
- `tag_face` stores a selected face under a user-facing name, and later `start_sketch_on_face` can use `{"type": "named_face", "name": "..."}`.
- `create_offset_plane` creates a named reference plane from a selected face or an original datum plane, and later `start_sketch` can use that plane name.

Chinese job names, part names, operation ids, named faces, reference planes, and output filenames are supported. JSON and summary files are written as UTF-8 with readable Chinese text.

`revolve` creates rotational features from a fully constrained half-section sketch and a selected axis. The current SolidWorks-tested path uses a profile segment as the axis:

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

`cut_revolve` uses the same section-and-axis pattern for subtractive rotational features such as center bores, grooves, relief cuts, and lathe-style cuts. The sketch plane can be:

- an original datum plane such as `front`, `top`, or `right`;
- a generated planar face selected by `start_sketch_on_face`;
- a named offset reference plane created by `create_offset_plane`.

The SolidWorks-tested cut-revolve example is:

```powershell
python .\mcp-server\server.py run .\examples\primitives\中文旋转切除测试.json --backend solidworks
```

`sweep` creates path-driven additive geometry from two sketches: one fully constrained path sketch and one fully constrained profile sketch. Use `finish_sketch` after validating the path so the executor can later select both sketches for the sweep feature:

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

The sweep example is:

```powershell
python .\mcp-server\server.py run .\examples\advanced\中文扫描把手测试.json --backend solidworks
```

`add_arc` adds a constrained circular-arc path segment, and `cut_sweep` creates subtractive swept geometry from a profile and path. The SolidWorks-tested arc plus swept-cut example is:

```powershell
python .\mcp-server\server.py run .\examples\advanced\中文圆弧扫描切除测试.json --backend solidworks
```

`sweep` and `cut_sweep` also accept advanced parameters such as `guide_curves`, `twist_control`, `twist_angle`, `path_align`, and `section_control`. Constant-twist sweep is SolidWorks-tested:

```powershell
python .\mcp-server\server.py run .\examples\advanced\中文扭转扫描测试.json --backend solidworks
```

Guide-curve / variable-section sweep is represented in the DSL and preview backend with:

```powershell
python .\mcp-server\server.py run .\examples\advanced\中文导向线变截面扫描测试.json --backend solidworks
```

That guide-curve example is SolidWorks-tested. The stable pattern is: create and finish the path sketch, create and finish the guide-curve sketch, then start the profile sketch and add explicit `pierce` relations from the profile center to the path and from a profile point to the guide curve.

`loft` creates additive multi-section geometry from ordered profile sketches. The current SolidWorks-tested path creates offset reference planes from the original `front` plane, fully constrains one closed profile sketch on each plane, closes all profile sketches, then calls `loft` with the ordered `profiles` list:

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

The tested loft example is:

```powershell
python .\mcp-server\server.py run .\examples\advanced\中文放样过渡管测试.json --backend solidworks
```

`cut_loft` creates subtractive multi-section geometry from ordered profile sketches. The current SolidWorks-tested path builds a base solid first, creates offset reference planes through the body, fully constrains one closed cut profile on each plane, closes all cut profile sketches, then calls `cut_loft`:

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

The tested cut-loft example is:

```powershell
python .\mcp-server\server.py run .\examples\advanced\中文放样切除测试.json --backend solidworks
```

Sketch-level optimization is now supported for common engineering workflows where the sketch should already contain finished repeated or treated geometry:

- `sketch_fillet`: apply SolidWorks sketch fillets before the feature is created.
- `sketch_chamfer`: apply SolidWorks sketch chamfers after the base sketch has been constrained and dimensioned.
- `add_chamfered_rectangle`: create a closed chamfered rectangle profile directly in the sketch; keep it as a fallback for direct closed profiles, not the default engineering workflow.
- `add_straight_slot`: create a SolidWorks straight slot from center, length, width, and angle.
- `add_polygon`: create a regular polygon from center, radius, side count, and angle.
- `add_spline`: create an open or closed spline through fit points.
- `fully_define_sketch`: ask SolidWorks to add residual relations/dimensions after explicit driving dimensions are already present; pass a fixed `datum` point when available. Default `relation_mask=1023` enables all local SolidWorks full-define relation flags. Use it mainly for spline handle or curve-shape degrees of freedom, not as a replacement for planned dimensions.
- `convert_entities`: convert or project selected model face edges into the active sketch. The tested SolidWorks path uses `prefer_native=false` to project the selected face loop into sketch segments when native conversion does not expose created segments through COM.
- `offset_entities`: offset an existing sketch entity group by a driving distance, typically after `convert_entities` for grooves, gasket paths, lips, and rims.
- `add_mirrored_circle`: create a mirrored circular sketch entity from a centerline.
- `add_circle_linear_pattern`: create repeated circular sketch entities from one source circle; generated copies can be referenced as `<operation_id>_<index>` for follow-up dimensions and relations.

The tested sketch optimization example is:

```powershell
python .\mcp-server\server.py run .\examples\sketch\中文草图优化测试.json --backend solidworks
```

The tested convert-and-offset example is:

```powershell
python .\mcp-server\server.py run .\examples\sketch\中文转换实体等距切槽测试.json --backend solidworks
```

Run a primitive job directly:

```powershell
python .\mcp-server\server.py run .\examples\basic\primitive_l_bracket.json --backend solidworks
```

## Backend Selection

`backend: "auto"` tries CAD backends first, then falls back to preview:

1. SolidWorks COM, if pywin32 and SolidWorks are available.
2. FreeCAD, only for the older direct mounting-plate path when available.
3. Preview backend.

You can force the preview backend:

```powershell
python .\mcp-server\server.py run .\examples\basic\mounting_plate.json --backend preview
python .\mcp-server\server.py run .\examples\basic\l_bracket.json --backend preview
```
