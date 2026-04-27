from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from core.protocols import WorkflowContext
from core.schemas import GenerationResult, ValidationResult


class SyzkallerBuildValidatePlugin:
    name = "syz-build-debug"

    def validate(self, generation: GenerationResult, ctx: WorkflowContext) -> ValidationResult:
        if ctx.syzkaller_dir is None:
            raise ValueError("syzkaller_dir is required for validation")
        make_target = str(ctx.config.get("make_target", "descriptions"))
        timeout_sec = int(ctx.config.get("timeout_sec", 300))
        tracked_files = [item.path for item in generation.generated_files]

        cmd = ["make", make_target]
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=ctx.syzkaller_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                check=False,
            )
            duration = time.monotonic() - start
            status = "passed" if proc.returncode == 0 else "failed"
            stdout = proc.stdout
            stderr = proc.stderr
            returncode = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            status = "timeout"
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            returncode = None
            timed_out = True

        combined = "\n".join(part for part in (stdout, stderr) if part)
        diagnostics = _extract_errors(combined, tracked_files)
        return ValidationResult(
            status=status,
            diagnostics=diagnostics,
            metadata={
                "command": cmd,
                "make_target": make_target,
                "timeout_sec": timeout_sec,
                "returncode": returncode,
                "timed_out": timed_out,
                "duration_sec": round(duration, 3),
                "stdout_tail": stdout.splitlines()[-80:],
                "stderr_tail": stderr.splitlines()[-80:],
                "tracked_generated_files": tracked_files,
            },
        )


def _extract_errors(text: str, tracked_files: list[str]) -> list[dict[str, object]]:
    tracked_names = {Path(path).name for path in tracked_files}
    errors: list[dict[str, object]] = []
    seen: set[tuple[str, int | None, str]] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.search(r"(?P<file>[^:\s]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?P<msg>.+)", line)
        if match:
            file_name = match.group("file")
            line_no = int(match.group("line"))
            col = int(match.group("col")) if match.group("col") else None
            msg = match.group("msg").strip()
            key = (file_name, line_no, msg)
            if key not in seen:
                seen.add(key)
                errors.append(
                    {
                        "file": file_name,
                        "line": line_no,
                        "column": col,
                        "message": msg,
                        "tracked_file_hit": Path(file_name).name in tracked_names,
                    }
                )
            continue
        lower = line.lower()
        if "error" in lower or "failed" in lower:
            key = ("", None, line.strip())
            if key not in seen:
                seen.add(key)
                errors.append(
                    {
                        "file": None,
                        "line": None,
                        "column": None,
                        "message": line.strip(),
                        "tracked_file_hit": any(name in line for name in tracked_names),
                    }
                )
    return errors
