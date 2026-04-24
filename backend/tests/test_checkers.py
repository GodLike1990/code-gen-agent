"""Tests for checker registry and CheckResult serialization."""
from __future__ import annotations

import code_gen_agent.checkers  # noqa: F401
from code_gen_agent.checkers.base import CheckerRegistry, CheckResult, Issue


def test_all_checkers_registered() -> None:
    names = CheckerRegistry.names()
    for n in ("lint", "security", "compile", "test", "llm_review"):
        assert n in names


def test_check_result_serialization() -> None:
    r = CheckResult(
        name="lint",
        passed=False,
        severity="error",
        issues=[Issue(file="a.py", line=1, severity="error", message="bad")],
        raw_output="out",
    )
    d = r.to_dict()
    assert d["passed"] is False
    assert d["issues"][0]["file"] == "a.py"
