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

python3 - "$OUT_DIR" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
publish = json.loads((out_dir / "publish.json").read_text(encoding="utf-8"))

print(f"target repo: {publish.get('target_repo')}")
print(f"target subdir: {publish.get('target_subdir')}")
print(f"published: {publish.get('published')}")
print(f"validate status: {publish.get('validate_status')}")
for item in publish.get("generated_files", []):
    print(f"- {item.get('path')} [{item.get('kind')}] exists={item.get('exists')}")
PY
