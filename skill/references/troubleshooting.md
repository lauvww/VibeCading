# Troubleshooting

## No STEP Output

Cause: The preview backend is active, or no real CAD backend is available.

Action:

1. Check `summary.json`.
2. Confirm the selected backend.
3. Install/configure FreeCAD or SolidWorks automation.
4. Re-run the same JSON job.

## Validation Fails

Common causes:

- Hole center is too close to an edge.
- A dimension is zero or negative.
- Unsupported units were used.
- An unsupported export format was requested.

## SolidWorks COM Fails

Common causes:

- `pywin32` is not installed.
- SolidWorks is not installed or not registered for COM.
- Template path is missing or language-specific.
- The process is running without permission to write output files.

