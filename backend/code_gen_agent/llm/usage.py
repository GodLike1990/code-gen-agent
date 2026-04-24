"""Token / cost usage tracking across LLM calls."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


@dataclass
class UsageRecord:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, input_t: int, output_t: int) -> None:
        self.input_tokens += input_t
        self.output_tokens += output_t
        self.total_tokens += input_t + output_t
        self.calls += 1


# rough default pricing per 1K tokens (USD). Users can override via set_pricing.
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "claude-3-5-sonnet-latest": (0.003, 0.015),
    "deepseek-coder": (0.00014, 0.00028),
}


class UsageTracker(BaseCallbackHandler):
    """LangChain callback handler that aggregates token usage per model."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._by_model: dict[str, UsageRecord] = defaultdict(UsageRecord)
        self._pricing: dict[str, tuple[float, float]] = dict(DEFAULT_PRICING)

    def set_pricing(self, model: str, input_per_1k: float, output_per_1k: float) -> None:
        self._pricing[model] = (input_per_1k, output_per_1k)

    # LangChain callback hook
    def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: D401
        try:
            output = response.llm_output or {}
            usage = output.get("token_usage") or output.get("usage") or {}
            model = output.get("model_name") or output.get("model") or "unknown"
            input_t = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            output_t = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            if input_t or output_t:
                with self._lock:
                    self._by_model[model].add(input_t, output_t)
        except Exception:
            # never fail user flow on accounting errors
            pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_in = sum(r.input_tokens for r in self._by_model.values())
            total_out = sum(r.output_tokens for r in self._by_model.values())
            cost = 0.0
            by_model: dict[str, dict[str, Any]] = {}
            for model, rec in self._by_model.items():
                p = self._pricing.get(model, (0.0, 0.0))
                model_cost = rec.input_tokens / 1000 * p[0] + rec.output_tokens / 1000 * p[1]
                cost += model_cost
                by_model[model] = {
                    "input_tokens": rec.input_tokens,
                    "output_tokens": rec.output_tokens,
                    "total_tokens": rec.total_tokens,
                    "calls": rec.calls,
                    "cost_usd": round(model_cost, 6),
                }
            return {
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
                "total_tokens": total_in + total_out,
                "total_cost_usd": round(cost, 6),
                "by_model": by_model,
            }
