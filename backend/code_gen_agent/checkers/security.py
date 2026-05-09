"""安全扫描检查器 — 优先使用 Semgrep，Python 回退到 Bandit。"""
from __future__ import annotations

import json
import shutil
from typing import Any

from code_gen_agent.checkers._subprocess import run_subprocess
from code_gen_agent.checkers.base import CheckResult, Issue, register_checker


@register_checker("security")
class SecurityChecker:
    name = "security"

    async def run(
        self, workspace: str, files: dict[str, str], context: dict[str, Any] | None = None
    ) -> CheckResult:
        issues: list[Issue] = []
        raw_parts: list[str] = []

        if shutil.which("semgrep"):
            rc, out, err = await run_subprocess(
                ["semgrep", "--config=auto", "--json", "--quiet", workspace],
                cwd=workspace,
                timeout=120,
            )
            raw_parts.append(f"[semgrep rc={rc}]\n{err[:1000]}")
            try:
                data = json.loads(out or "{}")
                for r in data.get("results", []):
                    sev = (r.get("extra", {}).get("severity") or "WARNING").upper()
                    issues.append(
                        Issue(
                            file=r.get("path", ""),
                            line=int(r.get("start", {}).get("line", 0)),
                            severity="error" if sev in ("ERROR", "HIGH", "CRITICAL") else "warn",
                            message=r.get("extra", {}).get("message", ""),
                            code=r.get("check_id", ""),
                        )
                    )
            except Exception:
                pass
        elif shutil.which("bandit"):
            py_files = [p for p in files if p.endswith(".py")]
            if py_files:
                rc, out, err = await run_subprocess(
                    ["bandit", "-q", "-f", "json", *py_files],
                    cwd=workspace,
                    timeout=60,
                )
                raw_parts.append(f"[bandit rc={rc}]\n{err[:500]}")
                try:
                    data = json.loads(out or "{}")
                    for r in data.get("results", []):
                        sev = (r.get("issue_severity") or "LOW").upper()
                        issues.append(
                            Issue(
                                file=r.get("filename", ""),
                                line=int(r.get("line_number", 0)),
                                severity="error" if sev in ("HIGH", "CRITICAL") else "warn",
                                message=r.get("issue_text", ""),
                                code=r.get("test_id", ""),
                            )
                        )
                except Exception:
                    pass

        has_error = any(i.severity == "error" for i in issues)
        return CheckResult(
            name=self.name,
            passed=not has_error,
            severity="error" if has_error else "warn" if issues else "info",
            issues=issues,
            raw_output="\n".join(raw_parts),
        )
