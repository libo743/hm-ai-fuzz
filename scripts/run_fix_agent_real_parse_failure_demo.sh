#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

WORKSPACE=${1:-"$REPO_ROOT"}
KERNEL_SRC=${2:-"$REPO_ROOT/../linux"}
SYZKALLER_DIR=${3:-"$REPO_ROOT/../syzkaller"}
OUT_DIR=${4:-"$REPO_ROOT/out/scenarios/fix-agent-real-parse-failure"}
OUT_JSON=${5:-"$OUT_DIR/workflow-result.json"}

mkdir -p "$OUT_DIR"

cd "$REPO_ROOT"

python3 -m workflows.proc_workflow \
  --workspace "$WORKSPACE" \
  --kernel-src "$KERNEL_SRC" \
  --syzkaller-dir "$SYZKALLER_DIR" \
  --out-dir "$OUT_DIR" \
  --out-json "$OUT_JSON" \
  --make-target descriptions \
  --timeout-sec 180

python3 - "$OUT_DIR" <<'PY'
import json
import re
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
generate_v2 = json.loads((out_dir / "generate-v2.json").read_text(encoding="utf-8"))
txt_files = [item["path"] for item in generate_v2.get("generated_files", []) if item.get("kind") == "txt"]
if not txt_files:
    raise SystemExit("no generated txt file found")

txt_path = Path(txt_files[0])
text = txt_path.read_text(encoding="utf-8")
pattern = re.compile(r"^(read\$proc_[^(]+\([^)]*\))$", re.MULTILINE)
match = pattern.search(text)
if not match:
    raise SystemExit("no read$proc_* line found to corrupt")

broken_line = match.group(1)[:-1]
text = text[:match.start(1)] + broken_line + text[match.end(1):]
txt_path.write_text(text, encoding="utf-8")

marker = {
    "file": str(txt_path),
    "corruption": "removed closing parenthesis from first read$proc_* declaration",
    "broken_line": broken_line,
}
(out_dir / "corruption.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(marker, ensure_ascii=False))
PY

HM_AI_FUZZ_LLM_FIX_SUGGEST=1 \
python3 - "$WORKSPACE" "$OUT_DIR" "$SYZKALLER_DIR" <<'PY'
import json
import os
import sys
from pathlib import Path

from core.protocols import WorkflowContext
from core.schema_adapter_v2 import adapt_validate_proc_v2, generate_v2_to_generation_result
from llm.agents.fix_agent import FixAgent
from llm.client import LLMClient
from llm.config import load_config_from_env
from validators.syzkaller_build import SyzkallerBuildValidatePlugin
from workflows.proc_workflow import _select_failed_unit, _source_fragment_for_failed_unit

workspace = Path(sys.argv[1]).resolve()
out_dir = Path(sys.argv[2]).resolve()
syzkaller_dir = Path(sys.argv[3]).resolve()

generate_v2 = json.loads((out_dir / "generate-v2.json").read_text(encoding="utf-8"))
generation = generate_v2_to_generation_result(generate_v2)
ctx = WorkflowContext(
    workspace=workspace,
    output_dir=out_dir,
    syzkaller_dir=syzkaller_dir,
    config={"make_target": "descriptions", "timeout_sec": 180},
)

validation = SyzkallerBuildValidatePlugin().validate(generation, ctx)
validate_v2 = adapt_validate_proc_v2(validation)

llm_config = load_config_from_env()
fix_agent = FixAgent(LLMClient(llm_config), workspace / "llm" / "prompts")
failed_unit = _select_failed_unit(generate_v2, validate_v2)
source_fragment = _source_fragment_for_failed_unit(generate_v2, ctx)

try:
    suggestion = fix_agent.suggest(
        validate_v2=validate_v2,
        failed_unit=failed_unit if isinstance(failed_unit, dict) else None,
        source_fragment=source_fragment,
    )
    fix = {
        "enabled": llm_config.enabled,
        "status": "ok",
        "reason": None,
        "suggestions": [suggestion],
    }
except Exception as exc:
    fix = {
        "enabled": llm_config.enabled,
        "status": "error",
        "reason": str(exc),
        "suggestions": [],
    }

(out_dir / "validate-v2-broken.json").write_text(
    json.dumps(validate_v2, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
(out_dir / "llm").mkdir(parents=True, exist_ok=True)
(out_dir / "llm" / "fix-suggestions-broken.json").write_text(
    json.dumps(fix, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(f"validate-v2 status: {validate_v2.get('status')}")
print(f"diagnostics: {len(validate_v2.get('diagnostics', []))}")
for item in validate_v2.get("diagnostics", [])[:5]:
    print(f"- {item.get('file')}:{item.get('line')} {item.get('message')}")

print(f"fix-agent enabled: {fix.get('enabled')}")
print(f"fix-agent status: {fix.get('status')}")
print(f"fix-agent reason: {fix.get('reason')}")
for item in fix.get("suggestions", [])[:3]:
    print(f"- suggestion item_key: {item.get('item_key')}")
    print(f"  fixes: {len(item.get('fixes', []))}")
    print(f"  warnings: {item.get('warnings')}")
PY
