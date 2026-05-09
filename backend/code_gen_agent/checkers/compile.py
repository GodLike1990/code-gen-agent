"""各语言编译/语法检查器。"""
from __future__ import annotations

import shutil
import sys
from typing import Any

from code_gen_agent.checkers._subprocess import run_subprocess
from code_gen_agent.checkers.base import CheckResult, Issue, register_checker


@register_checker("compile")
class CompileChecker:
    name = "compile"

    async def run(
        self, workspace: str, files: dict[str, str], context: dict[str, Any] | None = None
    ) -> CheckResult:
        issues: list[Issue] = []
        raw_parts: list[str] = []

        py = [p for p in files if p.endswith(".py")]
        if py:
            rc, out, err = await run_subprocess(
                [sys.executable, "-m", "py_compile", *py], cwd=workspace, timeout=60
            )
            raw_parts.append(f"[py_compile rc={rc}]\n{out}\n{err}")
            if rc != 0:
                issues.append(
                    Issue(file="", line=0, severity="error", message=err or "py_compile failed")
                )

        ts = [p for p in files if p.endswith((".ts", ".tsx"))]
        if ts and shutil.which("tsc"):
            rc, out, err = await run_subprocess(
                ["tsc", "--noEmit", *ts], cwd=workspace, timeout=120
            )
            raw_parts.append(f"[tsc rc={rc}]\n{out}\n{err}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message=out or err))

        go = [p for p in files if p.endswith(".go")]
        if go and shutil.which("go"):
            rc, out, err = await run_subprocess(["go", "build", "./..."], cwd=workspace, timeout=120)
            raw_parts.append(f"[go build rc={rc}]\n{out}\n{err}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message=err))

        passed = not issues
        return CheckResult(
            name=self.name,
            passed=passed,
            severity="error" if issues else "info",
            issues=issues,
            raw_output="\n".join(raw_parts),
        )
