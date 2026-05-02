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
from core.nl_job_planner import draft_feature_plan_from_natural_language, draft_primitive_job_from_natural_language
from core.strategy_planner import plan_modeling_strategy_dict
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


def plan_modeling_strategy(request: str) -> dict[str, Any]:
    """Plan a CAD modeling strategy from natural language without running CAD."""
    return plan_modeling_strategy_dict(request)


def draft_primitive_job(request: str, export_formats: list[str] | None = None) -> dict[str, Any]:
    """Draft a primitive CAD job from natural language without running CAD."""
    return draft_primitive_job_from_natural_language(request, export_formats=export_formats)


def draft_feature_plan(request: str) -> dict[str, Any]:
    """Draft a feature plan from natural language without compiling Primitive DSL."""
    return draft_feature_plan_from_natural_language(request)


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


def _cmd_plan_strategy(args: argparse.Namespace) -> int:
    request = " ".join(args.request).strip()
    if args.input_file:
        file_request = Path(args.input_file).read_text(encoding="utf-8").strip()
        request = "\n".join(item for item in [request, file_request] if item).strip()
    result = plan_modeling_strategy(request)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _request_from_args(args: argparse.Namespace) -> str:
    request = " ".join(args.request).strip()
    if args.input_file:
        file_request = Path(args.input_file).read_text(encoding="utf-8").strip()
        request = "\n".join(item for item in [request, file_request] if item).strip()
    return request


def _cmd_plan_features(args: argparse.Namespace) -> int:
    request = _request_from_args(args)
    result = draft_feature_plan_from_natural_language(request)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ready_for_compilation"] else 2


def _cmd_draft_job(args: argparse.Namespace) -> int:
    request = _request_from_args(args)
    result = draft_primitive_job_from_natural_language(
        request,
        job_id=args.job_id,
        part_name=args.part_name,
        material=args.material,
        export_formats=args.export_formats,
    )
    if args.output and result.get("job"):
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result["job"], indent=2, ensure_ascii=False), encoding="utf-8")
        result["job_path"] = str(output_path)
    if args.job_only:
        if not result.get("job"):
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 2
        print(json.dumps(result["job"], indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ready_for_execution"] else 2


def _cmd_run_nl(args: argparse.Namespace) -> int:
    request = _request_from_args(args)
    draft = draft_primitive_job_from_natural_language(
        request,
        job_id=args.job_id,
        part_name=args.part_name,
        material=args.material,
        export_formats=args.export_formats,
    )
    if not draft["ready_for_execution"] or not draft.get("job"):
        print(json.dumps(draft, indent=2, ensure_ascii=False))
        return 2
    job = CadJob.from_dict(draft["job"])
    validate_job(job)
    result = run_job(job, output_root=Path(args.output_root), backend=args.backend)
    result["natural_language"] = {
        "request": request,
        "strategy": draft["strategy"],
        "feature_plan": draft["feature_plan"],
        "parsed_parameters": draft["parsed_parameters"],
        "warnings": draft["warnings"],
    }
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

    @app.tool()
    def plan_modeling_strategy_tool(request: str) -> dict[str, Any]:
        return plan_modeling_strategy(request=request)

    @app.tool()
    def draft_feature_plan_tool(request: str) -> dict[str, Any]:
        return draft_feature_plan(request=request)

    @app.tool()
    def draft_primitive_job_tool(request: str, export_formats: list[str] | None = None) -> dict[str, Any]:
        return draft_primitive_job(request=request, export_formats=export_formats)

    @app.tool()
    def run_natural_language_part_tool(
        request: str,
        backend: str = "auto",
        export_formats: list[str] | None = None,
    ) -> dict[str, Any]:
        draft = draft_primitive_job_from_natural_language(request, export_formats=export_formats)
        if not draft["ready_for_execution"] or not draft.get("job"):
            return draft
        job = CadJob.from_dict(draft["job"])
        validate_job(job)
        result = run_job(job, output_root=PROJECT_ROOT / "outputs" / "jobs", backend=backend)
        result["natural_language"] = {
            "request": request,
            "strategy": draft["strategy"],
            "feature_plan": draft["feature_plan"],
            "parsed_parameters": draft["parsed_parameters"],
            "warnings": draft["warnings"],
        }
        return result

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

    plan_strategy_parser = subparsers.add_parser(
        "plan-strategy",
        help="Plan a modeling strategy from a natural-language CAD request",
    )
    plan_strategy_parser.add_argument("request", nargs="*", help="Natural-language CAD request")
    plan_strategy_parser.add_argument("--input-file", help="Read additional request text from a UTF-8 file")
    plan_strategy_parser.set_defaults(func=_cmd_plan_strategy)

    plan_features_parser = subparsers.add_parser(
        "plan-features",
        help="Draft a Feature Plan from a natural-language CAD request",
    )
    plan_features_parser.add_argument("request", nargs="*", help="Natural-language CAD request")
    plan_features_parser.add_argument("--input-file", help="Read additional request text from a UTF-8 file")
    plan_features_parser.set_defaults(func=_cmd_plan_features)

    draft_job_parser = subparsers.add_parser(
        "draft-job",
        help="Draft a primitive_part CAD job from a natural-language CAD request",
    )
    draft_job_parser.add_argument("request", nargs="*", help="Natural-language CAD request")
    draft_job_parser.add_argument("--input-file", help="Read additional request text from a UTF-8 file")
    draft_job_parser.add_argument("--job-id")
    draft_job_parser.add_argument("--part-name")
    draft_job_parser.add_argument("--material")
    draft_job_parser.add_argument("--export-formats", nargs="+", default=["pdf", "svg", "step"])
    draft_job_parser.add_argument("--output", help="Write the generated primitive_part JSON to this path")
    draft_job_parser.add_argument("--job-only", action="store_true", help="Print only the generated CAD job JSON")
    draft_job_parser.set_defaults(func=_cmd_draft_job)

    run_nl_parser = subparsers.add_parser(
        "run-nl",
        help="Draft and run a CAD job from a natural-language CAD request",
    )
    run_nl_parser.add_argument("request", nargs="*", help="Natural-language CAD request")
    run_nl_parser.add_argument("--input-file", help="Read additional request text from a UTF-8 file")
    run_nl_parser.add_argument("--backend", default="auto", choices=["auto", "preview", "freecad", "solidworks"])
    run_nl_parser.add_argument("--output-root", default=str(PROJECT_ROOT / "outputs" / "jobs"))
    run_nl_parser.add_argument("--job-id")
    run_nl_parser.add_argument("--part-name")
    run_nl_parser.add_argument("--material")
    run_nl_parser.add_argument("--export-formats", nargs="+", default=["pdf", "svg", "step"])
    run_nl_parser.set_defaults(func=_cmd_run_nl)

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
