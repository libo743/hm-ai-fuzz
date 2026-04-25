#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

DIFF_JSON=${1:-"$REPO_ROOT/out/diff.json"}
SYZKALLER_DIR=${2:-/home/libo/work/syzkaller}
OUT_JSON=${3:-"$REPO_ROOT/out/generate.json"}
TXT_NAME=${4:-proc_auto.txt}

mkdir -p "$(dirname "$OUT_JSON")"

cd "$REPO_ROOT"

python3 - "$DIFF_JSON" "$SYZKALLER_DIR" "$OUT_JSON" "$TXT_NAME" <<'PY'
import json
import sys
from pathlib import Path

from core.pipeline import write_json
from core.protocols import WorkflowContext
from core.schemas import DiffResult, InterfaceSpec, SourceRef, to_jsonable
from generators.syzkaller.minimal import MinimalSyzkallerGeneratePlugin

diff_json = Path(sys.argv[1]).resolve()
syzkaller_dir = Path(sys.argv[2]).resolve()
out_json = Path(sys.argv[3]).resolve()
txt_name = sys.argv[4]

payload = json.loads(diff_json.read_text(encoding="utf-8"))
current = []
for item in payload.get("current", []):
    source = item.get("source")
    current.append(
        InterfaceSpec(
            subsystem=item["subsystem"],
            target=item["target"],
            kind=item["kind"],
            capabilities=list(item.get("capabilities", [])),
            source=SourceRef(**source) if isinstance(source, dict) else None,
            metadata=dict(item.get("metadata", {})),
        )
    )

new = []
for item in payload.get("new", []):
    source = item.get("source")
    new.append(
        InterfaceSpec(
            subsystem=item["subsystem"],
            target=item["target"],
            kind=item["kind"],
            capabilities=list(item.get("capabilities", [])),
            source=SourceRef(**source) if isinstance(source, dict) else None,
            metadata=dict(item.get("metadata", {})),
        )
    )

diff = DiffResult(
    current=current,
    existing_keys=list(payload.get("existing_keys", [])),
    new=new,
    new_items=list(payload.get("new_items", [])),
)
ctx = WorkflowContext(
    workspace=Path.cwd(),
    output_dir=out_json.parent,
    syzkaller_dir=syzkaller_dir,
    config={"txt_name": txt_name},
)
generation = MinimalSyzkallerGeneratePlugin().generate(diff, ctx)
write_json(out_json, to_jsonable(generation))

print(f"generate json: {out_json}")
print(f"generated interface groups: {generation.metadata.get('generated_interface_count')}")
for item in generation.generated_files:
    print(f"- generated {item.kind}: {item.path}")
PY
