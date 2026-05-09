"""Package：将工作区压缩为可下载的 ZIP 文件。"""
from __future__ import annotations

import time
import zipfile
from pathlib import Path
from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


_SKIP_SUFFIXES = (".tmp",)
_SKIP_DIRS = {".git", "__pycache__", "node_modules"}


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.name.endswith(_SKIP_SUFFIXES):
            continue
        yield p


@register_node("package")
class PackageNode(BaseNode):
    """打包节点 — 图的最终节点，将工作区压缩为可下载 ZIP。

    遍历 workspace_dir 下的所有文件（跳过 .git / __pycache__ / node_modules
    和 .tmp 文件），打包为 {thread_id}.zip 存放在工作区父目录。

    结果写入 state["artifact"]，包含 zip_path / size_bytes / file_count。
    前端 /requirement 页面通过 artifact.zip_path 判断是否显示下载按钮。
    工作区为空时不生成 zip，artifact.zip_path=None。
    """

    name = "package"

    async def run(self, state: AgentState) -> dict[str, Any]:
        workspace_dir = state.get("workspace_dir")
        thread_id = state.get("thread_id") or "unknown"
        if not workspace_dir:
            return {"artifact": None}

        ws = Path(workspace_dir).resolve()
        if not ws.exists():
            self.log.warning(
                "package_no_workspace",
                extra={"thread_id": thread_id, "event": "package_skipped", "workspace": str(ws)},
            )
            result = {
                "zip_path": None,
                "size_bytes": 0,
                "file_count": 0,
                "created_at": int(time.time() * 1000),
                "reason": "workspace missing",
            }
            return {
                "artifact": result,
                "events": [{"type": "artifact", **result}],
            }

        # zip 放在工作区同级目录，以 thread_id 命名
        zip_path = ws.parent / f"{thread_id}.zip"

        file_count = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in _iter_files(ws):
                arcname = p.relative_to(ws).as_posix()
                zf.write(p, arcname=arcname)
                file_count += 1

        size_bytes = zip_path.stat().st_size if zip_path.exists() else 0
        if file_count == 0:
            # 工作区为空，删除空 zip
            try:
                zip_path.unlink()
            except OSError:
                pass
            result = {
                "zip_path": None,
                "size_bytes": 0,
                "file_count": 0,
                "created_at": int(time.time() * 1000),
                "reason": "workspace empty",
            }
        else:
            result = {
                "zip_path": str(zip_path),
                "size_bytes": size_bytes,
                "file_count": file_count,
                "created_at": int(time.time() * 1000),
            }
            self.log.info(
                "package_built",
                extra={
                    "thread_id": thread_id,
                    "event": "package_built",
                    "zip_path": str(zip_path),
                    "size_bytes": size_bytes,
                    "file_count": file_count,
                },
            )

        return {
            "artifact": result,
            "events": [{"type": "artifact", **result}],
        }
