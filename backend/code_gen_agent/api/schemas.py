"""Request/response schemas for the HTTP API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CreateRunRequest(BaseModel):
    user_input: str
    thread_id: str | None = None


class ResumeRequest(BaseModel):
    human_feedback: Any
