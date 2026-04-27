#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

KERNEL_SRC=${1:-"$REPO_ROOT/../linux"}
TARGET_MODULE=${2:-fs/proc}
SEARCH_METHOD=${3:-prefix}
SCAN_MODE=${4:-auto}
OUT_JSON=${5:-"$REPO_ROOT/out/discover.json"}

mkdir -p "$(dirname "$OUT_JSON")"

cd "$REPO_ROOT"

python3 - "$KERNEL_SRC" "$TARGET_MODULE" "$SEARCH_METHOD" "$SCAN_MODE" "$OUT_JSON" <<'PY'
import sys
from pathlib import Path

from core.pipeline import write_json
from core.protocols import WorkflowContext
from core.schemas import to_jsonable
from extractors.proc.extractor import ProcDiscoverPlugin

kernel_src = Path(sys.argv[1]).resolve()
target_module = sys.argv[2]
search_method = sys.argv[3]
scan_mode = sys.argv[4]
out_json = Path(sys.argv[5]).resolve()

ctx = WorkflowContext(
    workspace=Path.cwd(),
    output_dir=out_json.parent,
    kernel_src=kernel_src,
    config={
        "target_module": target_module,
        "search_method": search_method,
        "scan_mode": scan_mode,
    },
)
discover = ProcDiscoverPlugin().discover(ctx)
write_json(out_json, to_jsonable(discover))

print(f"discover json: {out_json}")
print(f"target module: {target_module}")
print(f"matches: {len(discover)}")
for item in discover[:10]:
    ops = ",".join(item.capabilities)
    module_file = item.metadata.get("module_file")
    print(f"- {item.target} [{ops}] @ {module_file}")
if len(discover) > 10:
    print(f"... {len(discover) - 10} more")
PY
