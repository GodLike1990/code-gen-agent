"""检查点工厂。"""
from __future__ import annotations

from code_gen_agent.config import AgentConfig


def create_checkpointer(cfg: AgentConfig):
    """根据 state_backend 创建 LangGraph 检查点。"""
    backend = cfg.state_backend
    dsn = cfg.state_dsn

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if backend == "sqlite":
        # sqlite 使用异步 saver，必须在运行中的事件循环内创建。
        # 见 CodeGenAgent.setup()：agent 在 FastAPI 启动时惰性构建。
        # 此处返回 None，跳过 setup() 的调用方（如脚本模式）
        # 将回退到 MemorySaver 语义。
        return None
    if backend == "redis":
        from code_gen_agent.persistence.redis import create_redis_checkpointer

        return create_redis_checkpointer(dsn)
    if backend == "db":
        from code_gen_agent.persistence.db import create_db_checkpointer

        return create_db_checkpointer(dsn)
    raise ValueError(f"unknown state_backend: {backend}")
