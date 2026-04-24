"""Minimal quickstart.

Run:
    OPENAI_API_KEY=sk-... python examples/quickstart.py
"""
from __future__ import annotations

import asyncio
import os

from code_gen_agent import AgentConfig, CodeGenAgent


async def main() -> None:
    agent = CodeGenAgent(
        AgentConfig(
            provider="openai",
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model="gpt-4o-mini",
        )
    )
    async for event in agent.astream("Create a minimal FastAPI TODO app with tests"):
        print(event)


if __name__ == "__main__":
    asyncio.run(main())
