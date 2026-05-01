from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_ROOT.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.dsl import CadJob, load_job
from core.job_runner import run_job
from core.validators import validate_job
from adapters.solidworks_com import SolidWorksComAdapter


def _configure_stdio() -> None:
    for stream in [sys.stdout, sys.stderr]:
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_configure_stdio()


def create_mounting_plate(spec: dict[str, Any], output_root: str | None = None, backend: str = "auto") -> dict[str, Any]:
    """Run a mounting plate CAD job from an already parsed JSON object."""
    job = CadJob.from_dict(spec)
    validate_job(job)
    root = Path(output_root) if output_root else PROJECT_ROOT / "outputs" / "jobs"
    return run_job(job, output_root=root, backend=backend)


def create_feature_part(spec: dict[str, Any], output_root: str | None = None, backend: str = "auto") -> dict[str, Any]:
    """Run a generic feature-part CAD job from an already parsed JSON object."""
    job = CadJob.from_dict(spec)
    validate_job(job)
    if job.kind != "feature_part":
        raise ValueError("create_feature_part expects kind=feature_part.")
    root = Path(output_root) if output_root else PROJECT_ROOT / "outputs" / "jobs"
    return run_job(job, output_root=root, backend=backend)


def create_primitive_part(spec: dict[str, Any], output_root: str | None = None, backend: str = "auto") -> dict[str, Any]:
    """Run a primitive CAD job from an already parsed JSON object."""
    job = CadJob.from_dict(spec)
    validate_job(job)
    if job.kind != "primitive_part":
        raise ValueError("create_primitive_part expects kind=primitive_part.")
    root = Path(output_root) if output_root else PROJECT_ROOT / "outputs" / "jobs"
    return run_job(job, output_root=root, backend=backend)


def _cmd_validate(args: argparse.Namespace) -> int:
    job = load_job(Path(args.job_file))
    validate_job(job)
    print(json.dumps({"ok": True, "job_id": job.job_id, "kind": job.kind}, indent=2, ensure_ascii=False))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    job = load_job(Path(args.job_file))
    validate_job(job)
    result = run_job(
        job,
        output_root=Path(args.output_root),
        backend=args.backend,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 2


def _cmd_serve(_: argparse.Namespace) -> int:
    try:
        from fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - depends on optional runtime
        print(
            "FastMCP is not installed. The CAD job runner is available through the CLI; "
            f"MCP serving needs the fastmcp package. Detail: {exc}",
            file=sys.stderr,
        )
        return 2

    app = FastMCP("cad-agent-mcp")

    @app.tool()
    def create_mounting_plate_tool(spec: dict[str, Any], backend: str = "auto") -> dict[str, Any]:
        return create_mounting_plate(spec=spec, backend=backend)

    @app.tool()
    def create_feature_part_tool(spec: dict[str, Any], backend: str = "auto") -> dict[str, Any]:
        return create_feature_part(spec=spec, backend=backend)

    @app.tool()
    def create_primitive_part_tool(spec: dict[str, Any], backend: str = "auto") -> dict[str, Any]:
        return create_primitive_part(spec=spec, backend=backend)

    app.run()
    return 0


def _cmd_sw_check(args: argparse.Namespace) -> int:
    adapter = SolidWorksComAdapter()
    result = adapter.check_connection(visible=not args.hidden)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CAD Agent MCP runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a CAD job JSON file")
    validate_parser.add_argument("job_file")
    validate_parser.set_defaults(func=_cmd_validate)

    run_parser = subparsers.add_parser("run", help="Run a CAD job JSON file")
    run_parser.add_argument("job_file")
    run_parser.add_argument("--backend", default="auto", choices=["auto", "preview", "freecad", "solidworks"])
    run_parser.add_argument("--output-root", default=str(PROJECT_ROOT / "outputs" / "jobs"))
    run_parser.set_defaults(func=_cmd_run)

    serve_parser = subparsers.add_parser("serve", help="Start the optional MCP server")
    serve_parser.set_defaults(func=_cmd_serve)

    sw_check_parser = subparsers.add_parser("sw-check", help="Check SolidWorks COM and template availability")
    sw_check_parser.add_argument("--hidden", action="store_true", help="Do not force SolidWorks visible")
    sw_check_parser.set_defaults(func=_cmd_sw_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
