"""Package: zip the workspace into a single downloadable artifact."""
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

        # Place the zip next to the workspace dir (same parent), named by thread id.
        zip_path = ws.parent / f"{thread_id}.zip"

        file_count = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in _iter_files(ws):
                arcname = p.relative_to(ws).as_posix()
                zf.write(p, arcname=arcname)
                file_count += 1

        size_bytes = zip_path.stat().st_size if zip_path.exists() else 0
        if file_count == 0:
            # Remove an empty zip — no point keeping it.
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
