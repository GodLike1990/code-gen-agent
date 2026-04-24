"""Shared helpers for nodes."""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def strip_fences(text: str) -> str:
    return _JSON_FENCE.sub("", text).strip()


async def call_llm_json(
    llm: BaseChatModel, system: str, user: str, default: Any
) -> Any:
    """Invoke LLM and parse its response as JSON. Return `default` on parse failure."""
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = getattr(resp, "content", "") or ""
    if not isinstance(content, str):
        # LangChain sometimes returns list content parts
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    try:
        return json.loads(strip_fences(content))
    except Exception:
        return default
