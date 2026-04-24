"""Test runner checker (pytest / jest)."""
from __future__ import annotations

import shutil
import sys
from typing import Any

from code_gen_agent.checkers._subprocess import run_subprocess
from code_gen_agent.checkers.base import CheckResult, Issue, register_checker


@register_checker("test")
class TestChecker:
    name = "test"

    async def run(
        self, workspace: str, files: dict[str, str], context: dict[str, Any] | None = None
    ) -> CheckResult:
        has_py_tests = any(
            p.startswith("tests/") or p.endswith("_test.py") or "test_" in p
            for p in files
            if p.endswith(".py")
        )
        has_js_tests = any(
            p.endswith((".test.js", ".test.ts", ".spec.js", ".spec.ts")) for p in files
        )

        issues: list[Issue] = []
        raw_parts: list[str] = []

        if has_py_tests:
            rc, out, err = await run_subprocess(
                [sys.executable, "-m", "pytest", "-q", "--no-header"],
                cwd=workspace,
                timeout=120,
            )
            raw_parts.append(f"[pytest rc={rc}]\n{out[-2000:]}\n{err[-500:]}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message="tests failed"))

        if has_js_tests and shutil.which("npx"):
            rc, out, err = await run_subprocess(
                ["npx", "--yes", "jest", "--silent"], cwd=workspace, timeout=180
            )
            raw_parts.append(f"[jest rc={rc}]\n{out[-2000:]}\n{err[-500:]}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message="jest failed"))

        if not (has_py_tests or has_js_tests):
            return CheckResult(
                name=self.name,
                passed=True,
                severity="info",
                issues=[],
                raw_output="no tests found — skipped",
            )

        passed = not issues
        return CheckResult(
            name=self.name,
            passed=passed,
            severity="error" if issues else "info",
            issues=issues,
            raw_output="\n".join(raw_parts),
        )
