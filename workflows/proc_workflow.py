from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.pipeline import WorkflowPipeline, write_json
from core.protocols import WorkflowContext
from core.schema_adapter_v2 import (
    adapt_diff_proc_v2,
    adapt_discover_proc_v2,
    adapt_generate_proc_v2,
    adapt_validate_proc_v2,
    diff_v2_to_diff_result,
)
from extractors.proc.extractor import ProcDiscoverPlugin
from generators.syzkaller.minimal import MinimalSyzkallerGeneratePlugin
from modelers.simple_diff import SimpleDiffPlugin
from validators.syzkaller_build import SyzkallerBuildValidatePlugin


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hm-ai-fuzz",
        description="Plugin-based scaffold workflow for future syscall fuzz generation",
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="project workspace")
    parser.add_argument("--kernel-src", type=Path, default=Path("/home/libo/work/linux"), help="Linux source root")
    parser.add_argument("--syzkaller-dir", type=Path, default=Path("/home/libo/work/syzkaller"), help="syzkaller root")
    parser.add_argument("--target-module", default="fs/proc", help="subsystem module scope")
    parser.add_argument("--search-method", choices=("exact", "prefix", "substring"), default="prefix")
    parser.add_argument("--scan-mode", choices=("auto", "full"), default="auto")
    parser.add_argument("--out-dir", type=Path, default=Path("out"), help="output directory")
    parser.add_argument("--existing-json", type=Path, help="optional baseline json")
    parser.add_argument("--out-json", type=Path, default=Path("out/workflow-result.json"), help="workflow result json")
    parser.add_argument("--make-target", default="descriptions")
    parser.add_argument("--timeout-sec", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    existing = {}
    if args.existing_json and args.existing_json.is_file():
        existing = json.loads(args.existing_json.read_text(encoding="utf-8"))

    ctx = WorkflowContext(
        workspace=args.workspace.resolve(),
        output_dir=args.out_dir.resolve(),
        kernel_src=args.kernel_src.resolve(),
        syzkaller_dir=args.syzkaller_dir.resolve(),
        config={
            "target_module": args.target_module,
            "search_method": args.search_method,
            "scan_mode": args.scan_mode,
            "txt_name": "proc_auto.txt",
            "make_target": args.make_target,
            "timeout_sec": args.timeout_sec,
        },
    )
    pipeline = WorkflowPipeline(
        discover_plugin=ProcDiscoverPlugin(),
        diff_plugin=SimpleDiffPlugin(),
        generate_plugin=MinimalSyzkallerGeneratePlugin(),
        validate_plugin=SyzkallerBuildValidatePlugin(),
    )
    result = pipeline.run(ctx, existing)
    discover_v2 = adapt_discover_proc_v2(result["discover"], ctx)
    diff_v2 = adapt_diff_proc_v2(result["diff"], discover_v2)
    generate_plugin = MinimalSyzkallerGeneratePlugin()
    validate_plugin = SyzkallerBuildValidatePlugin()
    generation_v2_raw = generate_plugin.generate(diff_v2_to_diff_result(diff_v2), ctx)
    generate_v2 = adapt_generate_proc_v2(generation_v2_raw, diff_v2)
    validate_v2 = adapt_validate_proc_v2(validate_plugin.validate(generation_v2_raw, ctx))
    result["discover_v2"] = discover_v2
    result["diff_v2"] = diff_v2
    result["generate_v2"] = generate_v2
    result["validate_v2"] = validate_v2
    output_dir = args.out_dir.resolve()
    write_json(output_dir / "discover.json", result["discover"])
    write_json(output_dir / "discover-v2.json", discover_v2)
    write_json(output_dir / "diff.json", result["diff"])
    write_json(output_dir / "diff-v2.json", diff_v2)
    write_json(output_dir / "generate.json", result["generate"])
    write_json(output_dir / "generate-v2.json", generate_v2)
    write_json(output_dir / "validate.json", result["validate"])
    write_json(output_dir / "validate-v2.json", validate_v2)
    write_json(args.out_json.resolve(), result)
    print(f"workflow result: {args.out_json.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
