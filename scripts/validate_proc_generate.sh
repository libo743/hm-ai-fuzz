#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

DIFF_JSON=${1:-"$REPO_ROOT/out/diff.json"}
SYZKALLER_DIR=${2:-"$REPO_ROOT/../syzkaller"}
OUT_JSON=${3:-"$REPO_ROOT/out/generate-validation.json"}
TXT_NAME=${4:-proc_auto.txt}

bash "$REPO_ROOT/scripts/run_proc_generate_demo.sh" "$DIFF_JSON" "$SYZKALLER_DIR" "$OUT_JSON" "$TXT_NAME"

TXT_PATH="$SYZKALLER_DIR/sys/linux/$TXT_NAME"
CONST_PATH="$TXT_PATH.const"

python3 - "$OUT_JSON" "$TXT_PATH" "$CONST_PATH" <<'PY'
import json
import sys
from pathlib import Path

metadata_json = Path(sys.argv[1])
txt_path = Path(sys.argv[2])
const_path = Path(sys.argv[3])

metadata = json.loads(metadata_json.read_text(encoding="utf-8"))
txt = txt_path.read_text(encoding="utf-8")
const = const_path.read_text(encoding="utf-8")

generated_count = metadata.get("metadata", {}).get("generated_interface_count", 0)
if generated_count <= 0:
    raise SystemExit("generated_interface_count should be > 0")

required_txt = [
    "include <uapi/linux/fcntl.h>",
    "openat$proc_proc_cpuinfo(",
    'string["/proc/cpuinfo"]',
]
for snippet in required_txt:
    if snippet not in txt:
        raise SystemExit(f"generated txt missing expected snippet: {snippet}")

required_const = [
    "arches = 386, amd64, arm, arm64, mips64le, ppc64le, riscv64, s390x",
    "AT_FDCWD =",
    "__NR_openat =",
]
for snippet in required_const:
    if snippet not in const:
        raise SystemExit(f"generated txt.const missing expected snippet: {snippet}")

print(f"validation json: {metadata_json}")
print(f"generated txt: {txt_path}")
print(f"generated txt.const: {const_path}")
print(f"generated interface groups: {generated_count}")
print(f"skipped interface items: {metadata.get('metadata', {}).get('skipped_interface_count')}")
PY
