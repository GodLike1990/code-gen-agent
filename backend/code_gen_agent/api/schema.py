"""Agent 图结构内省端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from code_gen_agent import CodeGenAgent
from code_gen_agent.api.deps import get_agent

router = APIRouter(prefix="/agent")


@router.get("/graph/schema")
def graph_schema(agent: CodeGenAgent = Depends(get_agent)) -> dict:
    return agent.get_graph_schema()
