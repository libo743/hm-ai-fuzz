#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

cd "$REPO_ROOT"

python3 - <<'PY'
import tempfile
from pathlib import Path

from tests.test_proc_workflow import (
    test_auto_scan_skips_irrelevant_trees_but_full_mode_can_find_them,
    test_diff_plugin_treats_all_interfaces_as_new_against_empty_json,
    test_generate_plugin_writes_minimal_proc_auto_txt,
    test_proc_discover_plugin_filters_by_target_module,
    test_proc_workflow_runs_end_to_end,
    test_validate_plugin_reports_success,
)

tests = [
    test_auto_scan_skips_irrelevant_trees_but_full_mode_can_find_them,
    test_proc_discover_plugin_filters_by_target_module,
    test_diff_plugin_treats_all_interfaces_as_new_against_empty_json,
    test_generate_plugin_writes_minimal_proc_auto_txt,
    test_validate_plugin_reports_success,
    test_proc_workflow_runs_end_to_end,
]

for test in tests:
    with tempfile.TemporaryDirectory(prefix="hm-ai-fuzz-test.") as tmp:
        test(Path(tmp))
        print(f"PASS {test.__name__}")

print(f"passed {len(tests)} tests")
PY
