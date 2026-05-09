"""使用 jinja2 渲染的 Prompt 模板加载器。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined


class PromptRegistry:
    """从目录加载 YAML Prompt 模板。

    每个 YAML 文件定义包含 system 和 user 字段的 prompt，
    键名为文件 stem（如 intent.yaml → 键 intent）。
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
        """将 system + user 模板渲染为具体字符串。"""
        tmpl = self._load(key)
        rendered: dict[str, str] = {}
        for field in ("system", "user"):
            source = tmpl.get(field, "")
            rendered[field] = self._env.from_string(source).render(**variables) if source else ""
        return rendered

    def reload(self) -> None:
        """清除缓存，支持热重载。"""
        self._cache.clear()
