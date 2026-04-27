"""LangChain callback that logs a concise LLM call summary per invocation.

Each ``llm_call`` log line contains:
- thread_id  (if set on the callback)
- model name
- input / output / total token counts
- latency_ms
- prompt_preview  (first 200 chars of the first human/system message)
- completion_preview  (first 200 chars of the response text)
"""
from __future__ import annotations

import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from code_gen_agent.observability.logger import get_logger

_PREVIEW_LEN = 200

log = get_logger("llm")


class LlmLogCallback(BaseCallbackHandler):
    """Emit one structured ``llm_call`` log line per LLM invocation."""

    def __init__(self, thread_id: str | None = None) -> None:
        super().__init__()
        self.thread_id = thread_id
        self._start: float = 0.0
        self._prompt_preview: str = ""

    def on_llm_start(self, serialized: Any, prompts: list[str], **kwargs: Any) -> None:
        self._start = time.perf_counter()
        if prompts:
            self._prompt_preview = (prompts[0] or "")[:_PREVIEW_LEN]

    def on_chat_model_start(self, serialized: Any, messages: list[list], **kwargs: Any) -> None:
        self._start = time.perf_counter()
        # Flatten all message contents into one preview string.
        parts: list[str] = []
        for msg_list in messages:
            for msg in msg_list:
                content = getattr(msg, "content", "") or ""
                if content:
                    parts.append(str(content)[:_PREVIEW_LEN])
        self._prompt_preview = " | ".join(parts)[:_PREVIEW_LEN]

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        latency_ms = round((time.perf_counter() - self._start) * 1000, 1)
        try:
            output = response.llm_output or {}
            usage = output.get("token_usage") or output.get("usage") or {}
            model = output.get("model_name") or output.get("model") or "unknown"
            input_t = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            output_t = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)

            # Pull completion text from generations[0][0].
            completion_preview = ""
            if response.generations:
                gen = response.generations[0]
                if gen:
                    raw = gen[0]
                    text = getattr(raw, "text", None) or ""
                    if not text:
                        msg = getattr(raw, "message", None)
                        text = getattr(msg, "content", "") or ""
                    completion_preview = str(text)[:_PREVIEW_LEN]

            log.info(
                "llm_call",
                extra={
                    "event": "llm_call",
                    "thread_id": self.thread_id,
                    "model": model,
                    "input_tokens": input_t,
                    "output_tokens": output_t,
                    "total_tokens": input_t + output_t,
                    "latency_ms": latency_ms,
                    "prompt_preview": self._prompt_preview,
                    "completion_preview": completion_preview,
                },
            )
        except Exception:
            # Never let logging break the agent.
            pass
