"""LangChain 回调，每次 LLM 调用输出一条简洁日志。

每条 llm_call 日志包含：
- thread_id（若已设置）
- 模型名称
- 输入/输出/总 token 数
- latency_ms
- prompt_preview（第一条人类/系统消息的前 200 字符）
- completion_preview（响应文本的前 200 字符）
"""
from __future__ import annotations

import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from code_gen_agent.observability.logger import get_logger
from code_gen_agent.observability.metrics import llm_metrics

_PREVIEW_LEN = 200

log = get_logger("llm")


class LlmLogCallback(BaseCallbackHandler):
    """每次 LLM 调用发出一条结构化 llm_call 日志。"""

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
        # 将所有消息内容拼接为一个预览字符串
        parts: list[str] = []
        for msg_list in messages:
            for msg in msg_list:
                content = getattr(msg, "content", "") or ""
                if content:
                    parts.append(str(content)[:_PREVIEW_LEN])
        self._prompt_preview = " | ".join(parts)[:_PREVIEW_LEN]

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        latency_ms = round((time.perf_counter() - self._start) * 1000, 1)
        model = "unknown"
        provider = "unknown"
        input_t = 0
        output_t = 0
        try:
            output = response.llm_output or {}
            usage = output.get("token_usage") or output.get("usage") or {}
            model = output.get("model_name") or output.get("model") or "unknown"
            provider = (output.get("system_fingerprint") and "openai") or provider
            input_t = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            output_t = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)

            # 从 generations[0][0] 中提取补全文本
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
            # 日志异常不能干扰 agent 主流程
            pass
        # 指标上报（与日志解耦，失败静默）
        try:
            m = llm_metrics()
            p_model = str(model)
            if input_t:
                m["tokens"].labels(provider=provider, model=p_model, kind="prompt").inc(input_t)
            if output_t:
                m["tokens"].labels(provider=provider, model=p_model, kind="completion").inc(output_t)
            m["calls"].labels(provider=provider, model=p_model, status="ok").inc()
        except Exception:  # noqa: BLE001
            pass

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        try:
            m = llm_metrics()
            m["calls"].labels(provider="unknown", model="unknown", status="error").inc()
        except Exception:  # noqa: BLE001
            pass
