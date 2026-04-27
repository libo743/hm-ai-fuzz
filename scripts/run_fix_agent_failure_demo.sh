#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

WORKSPACE=${1:-"$REPO_ROOT"}
KERNEL_SRC=${2:-"$REPO_ROOT/../linux"}
OUT_DIR=${3:-"$REPO_ROOT/out/scenarios/fix-agent-simulated-failure"}
OUT_JSON=${4:-"$OUT_DIR/workflow-result.json"}

TMP_SYZ=$(mktemp -d /tmp/hm-ai-fuzz-fix-demo.XXXXXX)
cleanup() {
  rm -rf "$TMP_SYZ"
}
trap cleanup EXIT

mkdir -p "$TMP_SYZ/sys/linux" "$OUT_DIR"
cat > "$TMP_SYZ/Makefile" <<'EOF'
descriptions:
	@echo 'sys/linux/proc_auto.txt:12: parse error: forced failure for fix-agent demo' 1>&2
	@exit 2
EOF

cd "$REPO_ROOT"

HM_AI_FUZZ_LLM_FIX_SUGGEST=1 \
python3 -m workflows.proc_workflow \
  --workspace "$WORKSPACE" \
  --kernel-src "$KERNEL_SRC" \
  --syzkaller-dir "$TMP_SYZ" \
  --out-dir "$OUT_DIR" \
  --out-json "$OUT_JSON" \
  --make-target descriptions \
  --timeout-sec 60

python3 - "$OUT_DIR" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
validate_v2 = json.loads((out_dir / "validate-v2.json").read_text(encoding="utf-8"))
fix = json.loads((out_dir / "llm" / "fix-suggestions.json").read_text(encoding="utf-8"))

print(f"validate-v2 status: {validate_v2.get('status')}")
print(f"diagnostics: {len(validate_v2.get('diagnostics', []))}")
for item in validate_v2.get("diagnostics", [])[:5]:
    print(f"- {item.get('file')}:{item.get('line')} {item.get('message')}")

print(f"fix-agent enabled: {fix.get('enabled')}")
print(f"fix-agent status: {fix.get('status')}")
print(f"fix-agent reason: {fix.get('reason')}")

for item in fix.get("suggestions", [])[:3]:
    print(f"- suggestion item_key: {item.get('item_key')}")
    print(f"  warnings: {item.get('warnings')}")
PY
