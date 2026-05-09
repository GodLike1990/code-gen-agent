"""节点共享工具函数。"""
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
    """调用 LLM 并将响应解析为 JSON，解析失败时返回 default。"""
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = getattr(resp, "content", "") or ""
    if not isinstance(content, str):
        # LangChain 有时返回列表形式的 content parts
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    try:
        return json.loads(strip_fences(content))
    except Exception:
        return default
