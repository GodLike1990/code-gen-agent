"""Prompt template loader with jinja2 rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined


class PromptRegistry:
    """Load YAML prompt templates from a directory.

    Each YAML file defines a prompt with `system` and `user` fields. The key is
    the file stem (e.g. `intent.yaml` -> key `intent`).
    """

    def __init__(self, prompts_dir: str | Path | None = None) -> None:
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent
        self.prompts_dir = Path(prompts_dir)
        self._cache: dict[str, dict[str, str]] = {}
        self._env = Environment(undefined=StrictUndefined, autoescape=False)

    def _load(self, key: str) -> dict[str, str]:
        if key in self._cache:
            return self._cache[key]
        path = self.prompts_dir / f"{key}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "system" not in data:
            raise ValueError(f"Invalid prompt file {path}: expected dict with 'system'")
        self._cache[key] = data
        return data

    def render(self, key: str, **variables: Any) -> dict[str, str]:
        """Render system+user templates into concrete strings."""
        tmpl = self._load(key)
        rendered: dict[str, str] = {}
        for field in ("system", "user"):
            source = tmpl.get(field, "")
            rendered[field] = self._env.from_string(source).render(**variables) if source else ""
        return rendered

    def reload(self) -> None:
        """Clear cache to allow hot reload."""
        self._cache.clear()
