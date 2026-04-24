"""Code generation node."""
from __future__ import annotations

from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState
from code_gen_agent.sandbox import Sandbox


@register_node("codegen")
class CodegenNode(BaseNode):
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
            # summarize failures
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

        # The workspace directory is prepared upstream; we pass it as the sandbox
        # root with an empty thread_id so Sandbox writes directly into it.
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
            # reset check results so the next checks node re-runs
            "check_results": {},
            "events": events_extra,
        }
