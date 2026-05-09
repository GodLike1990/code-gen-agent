"""checker 用的子进程工具函数。"""
from __future__ import annotations

import asyncio


async def run_subprocess(
    cmd: list[str], cwd: str, timeout: float = 60.0
) -> tuple[int, str, str]:
    """运行子进程并返回 (rc, stdout, stderr)，超时时 rc=-1。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return -2, "", f"command not found: {cmd[0]}"
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"timeout after {timeout}s"
    return (
        proc.returncode or 0,
        stdout_b.decode("utf-8", errors="replace"),
        stderr_b.decode("utf-8", errors="replace"),
    )
