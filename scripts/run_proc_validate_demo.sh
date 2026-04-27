#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

GENERATE_JSON=${1:-"$REPO_ROOT/out/generate.json"}
SYZKALLER_DIR=${2:-"$REPO_ROOT/../syzkaller"}
OUT_JSON=${3:-"$REPO_ROOT/out/validate.json"}
MAKE_TARGET=${4:-descriptions}
TIMEOUT_SEC=${5:-300}

mkdir -p "$(dirname "$OUT_JSON")"

cd "$REPO_ROOT"

python3 - "$GENERATE_JSON" "$SYZKALLER_DIR" "$OUT_JSON" "$MAKE_TARGET" "$TIMEOUT_SEC" <<'PY'
import json
import sys
from pathlib import Path

from core.pipeline import write_json
from core.protocols import WorkflowContext
from core.schemas import GeneratedFile, GenerationResult, to_jsonable
from validators.syzkaller_build import SyzkallerBuildValidatePlugin

generate_json = Path(sys.argv[1]).resolve()
syzkaller_dir = Path(sys.argv[2]).resolve()
out_json = Path(sys.argv[3]).resolve()
make_target = sys.argv[4]
timeout_sec = int(sys.argv[5])

payload = json.loads(generate_json.read_text(encoding="utf-8"))
generation = GenerationResult(
    generated_files=[
        GeneratedFile(
            path=item["path"],
            kind=item["kind"],
            details=dict(item.get("details", {})),
        )
        for item in payload.get("generated_files", [])
    ],
    units=list(payload.get("units", [])),
    metadata=dict(payload.get("metadata", {})),
)
ctx = WorkflowContext(
    workspace=Path.cwd(),
    output_dir=out_json.parent,
    syzkaller_dir=syzkaller_dir,
    config={"make_target": make_target, "timeout_sec": timeout_sec},
)
validation = SyzkallerBuildValidatePlugin().validate(generation, ctx)
write_json(out_json, to_jsonable(validation))

print(f"validate json: {out_json}")
print(f"build status: {validation.status}")
print(f"diagnostics: {len(validation.diagnostics)}")
for item in validation.diagnostics[:10]:
    print(f"- {item.get('file')}:{item.get('line')} {item.get('message')}")
if len(validation.diagnostics) > 10:
    print(f"... {len(validation.diagnostics) - 10} more")
PY
