"""HTTP API 的请求/响应 schema。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CreateRunRequest(BaseModel):
    user_input: str
    thread_id: str | None = None


class ResumeRequest(BaseModel):
    human_feedback: Any
