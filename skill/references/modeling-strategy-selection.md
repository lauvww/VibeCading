# Modeling Strategy Selection

Use this reference when a natural-language CAD request can be modeled multiple ways, when the user asks how Agent planning works, or when choosing the simplest maintainable SolidWorks feature tree matters.

## Core Answer

VibeCading should not let the MCP server guess engineering intent. The split is:

```text
User natural language
-> Agent extracts engineering intent and missing parameters
-> Agent compares plausible modeling strategies
-> Agent emits structured Primitive DSL
-> MCP / SolidWorks executor builds and validates the model
```

The Agent chooses the modeling method. The MCP executes the chosen structured operations and reports whether they worked.

## What "Simplest" Means

The simplest modeling method is not always the shortest JSON or the fewest sketch entities. Prefer the method that is easiest for an engineer to understand, edit, and verify later.

Rank strategies by these criteria:

1. Design intent is clear: dimensions and references match how the part functions.
2. Feature tree is readable: major manufacturing or functional steps are separate when that improves editability.
3. Sketches are fully constrained with dimensions and geometric relations.
4. Feature count is low, but not at the cost of unreadable sketches.
5. References are stable: original datums, named faces, and intentional offset planes are preferred over fragile incidental edges.
6. SolidWorks behavior is proven or low risk.
7. Future edits are localized: changing a hole spacing, wall thickness, or flange diameter should not require rebuilding the whole part.
8. Manufacturing meaning is preserved: do not hide a bore, groove, flange, or slot inside unrelated geometry just because it can be drawn that way.

## Strategy Selection Loop

Before writing Primitive DSL, do this:

1. Parse the request into engineering features:
   - base body
   - holes, slots, pockets, grooves
   - ribs, bosses, flanges, shafts
   - symmetry, repetitions, patterns
   - paths, transitions, lofted sections
   - required exports and drawings
2. Identify the dominant geometry class:
   - prismatic
   - rotational
   - path-driven
   - multi-section transition
   - face-derived or edge-derived
3. Generate two or three candidate strategies when the geometry is ambiguous.
4. Score each candidate using the criteria above.
5. Choose the default strategy.
6. Ask the user only when strategy choice changes manufacturing intent, function, or missing critical dimensions.
7. Emit Primitive DSL only after the strategy is chosen.

## Default Strategy Rules

Use these rules as the first pass:

- Plates, blocks, pads, bosses, rectangular pockets, windows: use `extrude` / `cut_extrude`.
- Shafts, sleeves, pulleys, washers, knobs, cones, lathe-like parts: use `revolve`.
- Center bores, annular grooves, relief cuts, countersinks: use `cut_revolve`.
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
- the user may expect a manufacturing process, such as turning vs milling;
- the drawing or model can be interpreted in multiple valid 3D ways.

## Summary Metadata Recommendation

When productizing the Agent layer, include strategy metadata in the generated job or execution summary:

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

This makes Agent decisions inspectable and creates a path toward an explicit strategy planner later.

## Future Product Optimization

The current implementation relies on the Skill/Agent to choose strategy. The next product step is to add a lightweight planning layer before validation:

```text
natural language
-> strategy candidates
-> strategy score
-> Primitive DSL
-> existing validators and SolidWorks executor
```

This can start as metadata-only planning. It does not need a new CAD executor yet.
