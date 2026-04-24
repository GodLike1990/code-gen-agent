"""Sandboxed per-thread workspace directory."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


class Sandbox:
    """Per-thread isolated directory with path-traversal protection."""

    def __init__(self, root: str | Path, thread_id: str) -> None:
        self.root = Path(root).resolve()
        self.thread_id = thread_id
        self.dir = (self.root / thread_id).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel_path: str) -> Path:
        """Resolve rel_path inside the sandbox; raise on escape."""
        if os.path.isabs(rel_path):
            raise ValueError(f"absolute path not allowed: {rel_path}")
        target = (self.dir / rel_path).resolve()
        try:
            target.relative_to(self.dir)
        except ValueError as e:
            raise ValueError(f"path escapes sandbox: {rel_path}") from e
        return target

    def write(self, rel_path: str, content: str) -> Path:
        target = self.resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)
        return target

    def read(self, rel_path: str) -> str:
        return self.resolve(rel_path).read_text(encoding="utf-8")

    def list_files(self) -> list[str]:
        files: list[str] = []
        for p in self.dir.rglob("*"):
            if p.is_file():
                files.append(str(p.relative_to(self.dir)))
        return files

    def cleanup(self) -> None:
        if self.dir.exists():
            shutil.rmtree(self.dir)


def get_sandbox(workspace_root: str, thread_id: str) -> Sandbox:
    return Sandbox(workspace_root, thread_id)
