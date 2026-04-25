#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

DISCOVER_JSON=${1:-"$REPO_ROOT/out/discover.json"}
EXISTING_JSON=${2:-"$REPO_ROOT/out/existing-fuzz-empty.json"}
OUT_JSON=${3:-"$REPO_ROOT/out/diff.json"}

mkdir -p "$(dirname "$EXISTING_JSON")" "$(dirname "$OUT_JSON")"

if [[ ! -f "$EXISTING_JSON" ]]; then
  printf '{}\n' > "$EXISTING_JSON"
fi

cd "$REPO_ROOT"

python3 - "$DISCOVER_JSON" "$EXISTING_JSON" "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

from core.pipeline import write_json
from core.protocols import WorkflowContext
from core.schemas import InterfaceSpec, SourceRef, to_jsonable
from modelers.simple_diff import SimpleDiffPlugin

discover_json = Path(sys.argv[1]).resolve()
existing_json = Path(sys.argv[2]).resolve()
out_json = Path(sys.argv[3]).resolve()

discover_payload = json.loads(discover_json.read_text(encoding="utf-8"))
existing_payload = json.loads(existing_json.read_text(encoding="utf-8"))

current = []
for item in discover_payload:
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

ctx = WorkflowContext(workspace=Path.cwd(), output_dir=out_json.parent)
diff = SimpleDiffPlugin().diff(current, existing_payload, ctx)
write_json(out_json, to_jsonable(diff))

print(f"diff json: {out_json}")
print(f"current interfaces: {len(diff.current)}")
print(f"existing interfaces: {len(diff.existing_keys)}")
print(f"new interface items: {len(diff.new_items)}")
for item in diff.new_items[:10]:
    print(f"- {item.get('target')}::{item.get('op')} -> {item.get('suggested_case_file')}")
if len(diff.new_items) > 10:
    print(f"... {len(diff.new_items) - 10} more")
PY
