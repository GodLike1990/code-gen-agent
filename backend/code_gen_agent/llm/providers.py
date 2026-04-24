"""Provider-specific defaults."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    default_model: str
    default_base_url: str | None = None


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(default_model="gpt-4o-mini"),
    "anthropic": ProviderSpec(default_model="claude-3-5-sonnet-latest"),
    "deepseek": ProviderSpec(
        default_model="deepseek-coder",
        default_base_url="https://api.deepseek.com/v1",
    ),
    "ernie": ProviderSpec(default_model="ERNIE-4.0-8K"),
}


def get_spec(provider: str) -> ProviderSpec:
    if provider not in PROVIDER_SPECS:
        raise ValueError(f"Unknown provider: {provider}")
    return PROVIDER_SPECS[provider]
