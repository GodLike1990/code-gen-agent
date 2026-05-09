"""代码生成节点。"""
from __future__ import annotations

from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState
from code_gen_agent.sandbox import Sandbox


@register_node("codegen")
class CodegenNode(BaseNode):
    """代码生成节点 — 根据任务列表生成或修复文件。

    有两种工作模式：
    - 初次生成（repair_mode=False）：根据 tasks 生成全部文件
    - 修复模式（repair_mode=True）：check_results 存在失败项时，
      将失败信息和现有代码一并传给 LLM，让其生成 diff/补丁

    生成的文件通过 Sandbox 写入磁盘（会校验路径，防止目录穿越）。
    输出写入 state["generated_files"]，并重置 state["check_results"] 为空
    以触发下一轮 checks 节点重新检查。
    """

    prompt_key = "codegen"

    async def run(self, state: AgentState) -> dict[str, Any]:
        tasks = state.get("tasks") or []
        language = state.get("language") or "python"
        existing = dict(state.get("generated_files") or {})
        check_results = state.get("check_results") or {}
        repair_mode = bool(check_results) and any(
            not r.get("passed") for r in check_results.values()
        )

        repair_context = ""
        existing_files_ctx = ""
        if repair_mode:
            # 汇总失败信息
            failed = {
                name: {"issues": r.get("issues", []), "raw": (r.get("raw_output") or "")[:2000]}
                for name, r in check_results.items()
                if not r.get("passed")
            }
            repair_context = str(failed)
            existing_files_ctx = "\n".join(
                f"--- {p} ---\n{c}" for p, c in existing.items()
            )

        rendered = self.prompts.render(
            "codegen",
            language=language,
            tasks=tasks,
            repair_context=repair_context,
            existing_files=existing_files_ctx,
        )
        default = {"files": []}
        payload = await call_llm_json(self.llm, rendered["system"], rendered["user"], default)
        if not isinstance(payload, dict):
            payload = default

        files_out = payload.get("files") or []

        # 工作区由上游准备，传入 Sandbox 作为根目录，thread_id 置空以直接写入
        workspace_dir = state.get("workspace_dir") or "."
        sandbox = Sandbox(root=workspace_dir, thread_id="")

        updated = dict(existing)
        events_extra: list[dict[str, Any]] = []
        for f in files_out:
            if not isinstance(f, dict):
                continue
            path = str(f.get("path") or "").strip()
            content = f.get("content")
            if not path or not isinstance(content, str):
                continue
            try:
                sandbox.write(path, content)
            except ValueError:
                self.log.warning(
                    "path_escape_rejected",
                    extra={"thread_id": state.get("thread_id"), "node": "codegen", "path": path},
                )
                continue
            except OSError as e:
                self.log.warning(
                    "write_failed",
                    extra={
                        "thread_id": state.get("thread_id"),
                        "node": "codegen",
                        "path": path,
                        "error": str(e),
                    },
                )
                continue
            updated[path] = content
            events_extra.append({"type": "file_generated", "path": path})

        return {
            "generated_files": updated,
            # 重置检查结果，触发下一轮 checks 节点重新运行
            "check_results": {},
            "events": events_extra,
        }
