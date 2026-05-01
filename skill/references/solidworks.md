# SolidWorks Adapter Notes

SolidWorks automation should run locally on Windows through COM.

Expected requirements:

- Installed SolidWorks desktop application.
- Python package `pywin32`.
- Access to a known part template path.
- Stable output directory with write permission.

The adapter should avoid relying on whichever document happens to be active. It should create or open the required document explicitly, execute a bounded operation, save/export, then verify the output files.

For MVP-0, SolidWorks support is intentionally gated behind availability checks. The preview backend is used when SolidWorks automation is not configured.

## Primitive Executor Notes

The SolidWorks backend now executes `primitive_part` through `SolidWorksPrimitiveExecutor`.

Important COM details:

- Some SolidWorks COM members are exposed by `pywin32` as properties rather than methods. Use a compatibility helper when reading members such as `Face.GetBox`, `Face.GetArea`, `Face.Normal`, or `Face.FaceInSurfaceSense`.
- For generated-face sketching, prefer planar face selection by feature id, body face normal, min/max position, and area rank before adding more fragile selectors.
- `tag_face` names a selected face inside the current executor run. Use it as a DSL convenience, not as a permanent SolidWorks topology guarantee after unrelated later edits.
- `create_offset_plane` creates a named reference plane from a selected planar face or an original datum plane. Later `start_sketch` operations can use that reference-plane name.
- `revolve` uses SolidWorks `FeatureRevolve2`. The tested stable path is a fully constrained half-section sketch with a profile segment selected as the rotational axis.
- `cut_revolve` also uses `FeatureRevolve2` in subtractive mode. The tested path creates a fully constrained cut section and uses a profile segment as the rotational axis.
- `sweep` uses SolidWorks `InsertProtrusionSwept4`. The tested stable path is one finished, fully constrained path sketch plus one fully constrained profile sketch selected by sketch id.
- `cut_sweep` uses SolidWorks `InsertCutSwept5`. The tested path creates a swept solid first, then cuts an inner bore using a second fully constrained path/profile pair.
- `add_arc` uses SolidWorks sketch arcs for curved sweep paths. The tested path constrains line-arc-line continuity with `coincident` and `tangent` relations.
- Sweep twist control is passed through to SolidWorks. The tested constant-twist example uses `twist_control=constant_twist` and a 90 degree `twist_angle`.
- Guide curves are selected by sketch curve entity with guide-curve selection mark `2`. For guide-curve sweeps, use `sgATPIERCE` relations in the profile sketch so the path and guide curve explicitly pierce profile points.
- `loft` uses SolidWorks `InsertProtrusionBlend2`. The tested path selects fully constrained closed profile sketches with profile selection mark `1`; optional guide curves use mark `2` and centerline curves use mark `4`.
- `cut_loft` uses SolidWorks `InsertCutBlend`. The tested path creates a base solid first, then selects ordered fully constrained cut profile sketches with profile selection mark `1`.
- `sketch_fillet` uses SolidWorks sketch fillet behavior before feature creation. The tested path applies four sketch fillets to a constrained rectangle, then extrudes the resulting rounded profile.
- `sketch_chamfer` uses SolidWorks sketch chamfer behavior before feature creation. The preferred engineering path is to constrain and dimension the base sketch first, then add the chamfer command with the required distance.
- `add_chamfered_rectangle` creates a closed chamfered sketch profile directly and adds endpoint coincident relations internally. Keep it as a fallback for direct closed profiles; do not make it the default way to model ordinary chamfers.
- `add_straight_slot` uses the SolidWorks sketch slot command for straight slots.
- `add_polygon` uses the SolidWorks sketch polygon command for regular polygons.
- `add_spline` uses the SolidWorks sketch spline command for fit-point spline curves. When `create_fit_point_refs=true`, the executor creates addressable fit-point references so follow-up dimensions and endpoint/tangent/curvature relations can target the curve explicitly.
- `fully_define_sketch` calls SolidWorks full sketch definition as a controlled final pass. Use it after explicit driving dimensions and relations, especially for residual spline handle or shape degrees of freedom. Passing a fixed `datum` point is preferred because the SolidWorks API accepts explicit horizontal and vertical datum entities. Default `relation_mask=1023` enables all relation types exposed by the local SolidWorks constants library.
- `convert_entities` first tries SolidWorks native convert-entities calls. The tested path sets `prefer_native=false`, reads the selected planar face loop, and projects the loop edges into the active sketch when native COM conversion does not expose created sketch segments.
- `offset_entities` uses SolidWorks sketch offset behavior on a referenced sketch entity group. The tested path offsets the projected top-face outer loop inward by a driving distance, then validates the sketch before cutting the shallow groove.
- `add_mirrored_circle` uses SolidWorks dynamic sketch mirror around a selected centerline.
- `add_circle_linear_pattern` creates repeated circular sketch geometry from one source circle. Generated copies are exposed as `<operation_id>_<index>` so follow-up dimensions and relations can fully define them without relying on `fixed`.
- `start_sketch` supports original datum plane aliases such as `front`, `top`, and `right`, plus named offset reference planes.
- Always rebuild or let SolidWorks update the model before selecting faces produced by earlier features, but do not call `EditRebuild3` while an active sketch is being edited; it can break sketch-edit state before operations like conversion or offset.
- `start_sketch_on_face` should fail if no unambiguous planar body face matches the target normal and position.
- Keep job JSON, summary files, SVG, and Skill docs as UTF-8. Chinese names should be preserved unless a character is unsafe for Windows paths or SolidWorks feature names.
