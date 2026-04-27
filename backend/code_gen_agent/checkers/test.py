"""Test runner checker — supports Python (pytest), JS/TS (jest/vitest), Go, Java, Rust."""
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
            p.startswith("tests/") or p.endswith("_test.py") or p.startswith("test_")
            for p in files
            if p.endswith(".py")
        )
        has_js_tests = any(
            p.endswith((".test.js", ".test.ts", ".spec.js", ".spec.ts")) for p in files
        )
        has_go_tests = any(p.endswith("_test.go") for p in files)
        # Java: files matching *Test.java or *Tests.java
        has_java_tests = any(
            (p.endswith("Test.java") or p.endswith("Tests.java")) for p in files
        )
        # Rust: #[cfg(test)] blocks live in the same source file — check by presence of .rs files
        # (cargo test runs them automatically; we just need any .rs file)
        has_rust = any(p.endswith(".rs") for p in files)

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
                issues.append(Issue(file="", line=0, severity="error", message="pytest: tests failed"))

        if has_js_tests and shutil.which("npx"):
            rc, out, err = await run_subprocess(
                ["npx", "--yes", "jest", "--silent"], cwd=workspace, timeout=180
            )
            raw_parts.append(f"[jest rc={rc}]\n{out[-2000:]}\n{err[-500:]}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message="jest: tests failed"))

        if has_go_tests and shutil.which("go"):
            rc, out, err = await run_subprocess(
                ["go", "test", "./..."], cwd=workspace, timeout=120
            )
            raw_parts.append(f"[go test rc={rc}]\n{out[-2000:]}\n{err[-500:]}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message="go test: tests failed"))

        if has_java_tests and shutil.which("mvn"):
            rc, out, err = await run_subprocess(
                ["mvn", "-q", "test"], cwd=workspace, timeout=180
            )
            raw_parts.append(f"[mvn test rc={rc}]\n{out[-2000:]}\n{err[-500:]}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message="mvn test: tests failed"))
        elif has_java_tests and shutil.which("gradle"):
            rc, out, err = await run_subprocess(
                ["gradle", "test", "--quiet"], cwd=workspace, timeout=180
            )
            raw_parts.append(f"[gradle test rc={rc}]\n{out[-2000:]}\n{err[-500:]}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message="gradle test: tests failed"))

        if has_rust and shutil.which("cargo"):
            rc, out, err = await run_subprocess(
                ["cargo", "test", "--quiet"], cwd=workspace, timeout=180
            )
            raw_parts.append(f"[cargo test rc={rc}]\n{out[-2000:]}\n{err[-500:]}")
            if rc != 0:
                issues.append(Issue(file="", line=0, severity="error", message="cargo test: tests failed"))

        has_any = has_py_tests or has_js_tests or has_go_tests or has_java_tests or has_rust
        if not has_any:
            return CheckResult(
                name=self.name,
                passed=False,
                severity="error",
                issues=[Issue(
                    file="",
                    line=0,
                    severity="error",
                    message=(
                        "No test file found. Add a test file following the language convention: "
                        "Python → test_<module>.py | Go → <module>_test.go | "
                        "TypeScript → <module>.test.ts | Java → <Module>Test.java | "
                        "Rust → #[cfg(test)] block in source file"
                    ),
                )],
                raw_output="no tests found — failing to enforce MVP test requirement",
            )

        passed = not issues
        return CheckResult(
            name=self.name,
            passed=passed,
            severity="error" if issues else "info",
            issues=issues,
            raw_output="\n".join(raw_parts),
        )
