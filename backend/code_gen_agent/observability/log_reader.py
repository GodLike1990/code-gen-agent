"""Read JSON-Lines log file and filter by thread_id.

Used as a fallback for `/agent/runs/{tid}/logs` when the in-memory
`LogCollector` doesn't have entries for the requested thread (e.g. after a
backend restart).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_log_file(path: str, thread_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Return log records matching `thread_id`, ascending by ts, capped at `limit`.

    Silent on missing file / permission / malformed lines — returns `[]` or
    best-effort partial list. Callers should treat the output as a hint, not
    the source of truth.
    """
    if not path:
        return []
    p = Path(path)
    try:
        if not p.exists():
            return []
    except OSError:
        return []

    out: list[dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("thread_id") == thread_id:
                    out.append(rec)
    except OSError:
        return out

    # Keep latest `limit` records, chronological order.
    if len(out) > limit:
        out = out[-limit:]
    return out
