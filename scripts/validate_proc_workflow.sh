#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

WORKSPACE=${1:-"$REPO_ROOT"}
KERNEL_SRC=${2:-"$REPO_ROOT/../linux"}
SYZKALLER_DIR=${3:-"$REPO_ROOT/../syzkaller"}
OUT_DIR=${4:-"$REPO_ROOT/out"}
OUT_JSON=${5:-"$OUT_DIR/workflow-result.json"}

mkdir -p "$OUT_DIR"

cd "$REPO_ROOT"

python3 -m workflows.proc_workflow \
  --workspace "$WORKSPACE" \
  --kernel-src "$KERNEL_SRC" \
  --syzkaller-dir "$SYZKALLER_DIR" \
  --out-dir "$OUT_DIR" \
  --out-json "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))

discover = data.get("discover", [])
diff = data.get("diff", {})
generate = data.get("generate", {})
validate = data.get("validate", {})

generated_files = [Path(item["path"]) for item in generate.get("generated_files", []) if isinstance(item, dict) and item.get("path")]
missing_files = [str(item) for item in generated_files if not item.is_file()]
if missing_files:
    raise SystemExit(f"missing generated files: {missing_files}")

status = validate.get("status")
if status != "passed":
    raise SystemExit(f"workflow validate step failed: {status}")

print(f"workflow json: {path}")
print(f"discover count: {len(discover)}")
print(f"diff new_items: {len(diff.get('new_items', []))}")
print(f"generated files: {[str(item) for item in generated_files]}")
print(f"validate status: {status}")

for item in discover[:5]:
    target = item.get("target")
    caps = ",".join(item.get("capabilities", []))
    print(f"- {target} [{caps}]")

if len(discover) > 5:
    print(f"... {len(discover) - 5} more discovered targets")
PY
