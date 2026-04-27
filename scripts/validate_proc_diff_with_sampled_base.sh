#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

DISCOVER_JSON=${1:-"$REPO_ROOT/out/discover.json"}
SAMPLE_SIZE=${2:-8}
RANDOM_SEED=${3:-20260424}
BASELINE_JSON=${4:-"$REPO_ROOT/out/existing-fuzz-sampled.json"}
OUT_JSON=${5:-"$REPO_ROOT/out/diff-sampled.json"}

mkdir -p "$(dirname "$BASELINE_JSON")" "$(dirname "$OUT_JSON")"

cd "$REPO_ROOT"

python3 - "$DISCOVER_JSON" "$SAMPLE_SIZE" "$RANDOM_SEED" "$BASELINE_JSON" <<'PY'
import json
import random
import sys
from pathlib import Path

discover_json = Path(sys.argv[1])
sample_size = int(sys.argv[2])
seed = int(sys.argv[3])
baseline_json = Path(sys.argv[4])

discover = json.loads(discover_json.read_text(encoding="utf-8"))
items = []
for match in discover:
    target = match.get("target")
    ops = match.get("capabilities", [])
    if not isinstance(target, str) or not isinstance(ops, list):
        continue
    for op in ops:
        if isinstance(op, str):
            items.append(
                {
                    "subsystem": match.get("subsystem", "proc"),
                    "target": target,
                    "op": op,
                    "module_file": match.get("metadata", {}).get("module_file"),
                }
            )

if not items:
    raise SystemExit("no interface items found in discover json")

sample_size = max(0, min(sample_size, len(items)))
random.seed(seed)
sampled = random.sample(items, sample_size)
baseline = {
    "agent": "sampled-existing-fuzz-v1",
    "sample_seed": seed,
    "sample_size": sample_size,
    "interfaces": sampled,
}
baseline_json.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"baseline json: {baseline_json}")
print(f"total interface items: {len(items)}")
print(f"sampled existing interfaces: {sample_size}")
for item in sampled[:10]:
    print(f"- sampled {item['target']}::{item['op']}")
if len(sampled) > 10:
    print(f"... {len(sampled) - 10} more sampled")
PY

bash "$REPO_ROOT/scripts/run_proc_diff_demo.sh" "$DISCOVER_JSON" "$BASELINE_JSON" "$OUT_JSON"

python3 - "$BASELINE_JSON" "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

baseline_json = Path(sys.argv[1])
out_json = Path(sys.argv[2])

baseline = json.loads(baseline_json.read_text(encoding="utf-8"))
diff = json.loads(out_json.read_text(encoding="utf-8"))

sampled = baseline.get("interfaces", [])
new_items = diff.get("new_items", [])

print(f"validated diff json: {out_json}")
print(f"existing interfaces: {len(sampled)}")
print(f"new interface items: {len(new_items)}")
print(f"expected new count: {sum(len(item.get('capabilities', [])) for item in diff.get('current', [])) - len(sampled)}")
PY
