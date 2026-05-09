"""静态 lint 检查器（Python 用 Ruff，JS/TS 用 ESLint，否则跳过）。"""
from __future__ import annotations

import json
import shutil
from typing import Any

from code_gen_agent.checkers._subprocess import run_subprocess
from code_gen_agent.checkers.base import CheckResult, Issue, register_checker


@register_checker("lint")
class LintChecker:
    name = "lint"

    async def run(
        self, workspace: str, files: dict[str, str], context: dict[str, Any] | None = None
    ) -> CheckResult:
        py = [p for p in files if p.endswith(".py")]
        js = [p for p in files if p.endswith((".js", ".jsx", ".ts", ".tsx"))]

        issues: list[Issue] = []
        raw_parts: list[str] = []

        if py and shutil.which("ruff"):
            rc, out, err = await run_subprocess(
                ["ruff", "check", "--output-format=json", *py], cwd=workspace, timeout=60
            )
            raw_parts.append(f"[ruff rc={rc}]\n{out}\n{err}")
            try:
                for d in json.loads(out or "[]"):
                    issues.append(
                        Issue(
                            file=d.get("filename", ""),
                            line=int((d.get("location") or {}).get("row", 0)),
                            severity="warn",
                            message=d.get("message", ""),
                            code=d.get("code", ""),
                        )
                    )
            except Exception:
                pass

        if js and shutil.which("eslint"):
            rc, out, err = await run_subprocess(
                ["eslint", "-f", "json", *js], cwd=workspace, timeout=60
            )
            raw_parts.append(f"[eslint rc={rc}]\n{out}\n{err}")
            try:
                for f in json.loads(out or "[]"):
                    for m in f.get("messages", []):
                        issues.append(
                            Issue(
                                file=f.get("filePath", ""),
                                line=int(m.get("line", 0)),
                                severity="error" if m.get("severity") == 2 else "warn",
                                message=m.get("message", ""),
                                code=m.get("ruleId") or "",
                            )
                        )
            except Exception:
                pass

        has_error = any(i.severity == "error" for i in issues)
        passed = not has_error
        return CheckResult(
            name=self.name,
            passed=passed,
            severity="error" if has_error else "warn" if issues else "info",
            issues=issues,
            raw_output="\n".join(raw_parts),
        )
