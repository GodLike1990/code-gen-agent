"""多维度并行检查编排节点。"""
from __future__ import annotations

import asyncio
from typing import Any

from code_gen_agent.checkers.base import CheckerRegistry
from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("checks")
class ChecksNode(BaseNode):
    """多维度并行检查节点 — 对生成代码执行质量门禁。

    并发运行所有启用的 checker（asyncio.gather），每个 checker 有 90s 超时：
    - lint：语法/风格检查（Python→ruff，JS/TS→eslint）
    - security：安全扫描（semgrep / bandit）
    - compile：编译/类型检查
    - test：运行单元测试（pytest / go test / jest / cargo test）
    - llm_review：LLM 自审代码质量

    全部通过 → routing 进入 verify；任一失败 → 进入 repair（最多 max_repairs 次）。
    结果写入 state["check_results"]，格式为 {checker_name: CheckResult.to_dict()}。
    """

    DEFAULT_CHECKS = ["lint", "security", "compile", "test", "llm_review"]

    async def run(self, state: AgentState) -> dict[str, Any]:
        files = dict(state.get("generated_files") or {})
        workspace = state.get("workspace_dir") or "."
        enabled = state.get("enable_checks") or self.DEFAULT_CHECKS  # type: ignore[assignment]

        context = {"llm": self.llm, "prompts": self.prompts, "tasks": state.get("tasks") or []}

        async def run_one(name: str):
            cls = CheckerRegistry.get(name)
            inst = cls()
            try:
                return await asyncio.wait_for(inst.run(workspace, files, context), timeout=90)
            except asyncio.TimeoutError:
                from code_gen_agent.checkers.base import CheckResult

                return CheckResult(
                    name=name, passed=False, severity="error", raw_output="checker timeout"
                )

        results = await asyncio.gather(*[run_one(n) for n in enabled])
        serialized = {r.name: r.to_dict() for r in results}
        all_pass = all(r.passed for r in results)

        return {
            "check_results": serialized,
            "events": [{"type": "check_report", "passed": all_pass, "summary": {r.name: r.passed for r in results}}],
        }
