"""Agent 运行的 SSE 流式处理。

`stream_run` 是纯异步生成器：无隐式依赖，
接受 LangGraph 迭代器、thread id、RequestStore 和 logger，
便于在不依赖 FastAPI 的情况下单独进行单元测试。

SSE 帧协议
──────────
每帧为 {"event": <str>, "data": <json-str>}。
前端依赖的事件名称及数据结构：

  state_delta   {"thread_id", "node"}                   — 触发前端状态轮询
  clarify       {"thread_id", "node", "type", "questions", ...}
  hitl          {"thread_id", "node", "type", "summary", ...}
  interrupt     {"thread_id", "node", "type", ...}       — 通用 interrupt
  hitl_decision {"thread_id", "node", "type", "action"}  — 用户的 HITL 决策
  done          {"final_status"}                         — 运行结束
  error         {"thread_id", "error_type", "message", "last_node"}

final_status 状态机
───────────────────
  "done"        — 默认值；运行开始时设置，正常完成时保留
  "interrupted" — 检测到 LangGraph interrupt 时覆盖
  "aborted"     — hitl_decision action == "abort" 时覆盖
  "cancelled"   — CancelledError（客户端断开）时覆盖
  "failed"      — Exception（未处理错误）时覆盖

final_status 在 finally 块中写入 RequestStore，
同时包含在 "done" SSE 帧中，供前端立即更新本地状态。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from code_gen_agent.graph.constants import (
    EVENT_CLARIFY,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_HITL,
    EVENT_HITL_DECISION,
    EVENT_INTERRUPT,
    EVENT_STATE_DELTA,
    HITL_ACTION_ABORT,
    STATUS_ABORTED,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
)
from code_gen_agent.persistence import RequestStore


async def stream_run(
    coro_iter: AsyncIterator[dict],
    *,
    tid: str | None,
    store: RequestStore,
    logger: logging.Logger,
) -> AsyncIterator[dict[str, Any]]:
    """将 LangGraph 流式数据项转换为 SSE 帧。

    发出 state_delta、节点专属事件类型、interrupt / clarify / hitl、
    done 和 error 帧。在 finally 块中将 final_status + summary 写入请求存储。
    """
    final_status = STATUS_DONE
    last_node: str | None = None
    try:
        async for item in coro_iter:
            stream_tid = item.get("thread_id") or tid
            update = item.get("update") or {}
            for node, partial in update.items():
                last_node = node

                # LangGraph 在节点调用 interrupt() 时，以合成键 "__interrupt__"
                # 发出特殊更新。值是 Interrupt 对象的元组/列表，每个对象携带
                # 节点传给 interrupt() 的 .value 字典。
                # 将每个 Interrupt 转换为 clarify/hitl SSE 帧，
                # 以便前端渲染对应的交互 UI。
                if node == "__interrupt__" or not isinstance(partial, dict):
                    interrupts = partial if isinstance(partial, (list, tuple)) else [partial]
                    for itp in interrupts:
                        val = getattr(itp, "value", None)
                        if not isinstance(val, dict):
                            continue
                        # 任何 interrupt 都意味着运行已暂停等待输入
                        final_status = STATUS_INTERRUPTED
                        itype = val.get("type") or EVENT_INTERRUPT
                        yield {
                            "event": itype,
                            "data": json.dumps({
                                "thread_id": stream_tid,
                                "node": node,
                                "type": itype,
                                **{k: v for k, v in val.items() if k != "type"},
                            }),
                        }
                    yield {
                        "event": EVENT_STATE_DELTA,
                        "data": json.dumps({"thread_id": stream_tid, "node": node}),
                    }
                    continue

                events = (partial or {}).get("events") or []
                for ev in events:
                    if ev.get("type") == EVENT_INTERRUPT:
                        final_status = STATUS_INTERRUPTED
                    # hitl 节点发出 "hitl_decision" 事件，记录用户选择的动作。
                    # 在路由之前检测 abort，确保 "done" 帧携带 "aborted"，
                    # 让前端立即更新状态而无需等待下次轮询。
                    if ev.get("type") == EVENT_HITL_DECISION and ev.get("action") == HITL_ACTION_ABORT:
                        final_status = STATUS_ABORTED
                    yield {
                        "event": ev.get("type", "update"),
                        "data": json.dumps({"thread_id": stream_tid, "node": node, **ev}),
                    }
                yield {
                    "event": EVENT_STATE_DELTA,
                    "data": json.dumps({"thread_id": stream_tid, "node": node}),
                }
        yield {"event": EVENT_DONE, "data": json.dumps({"final_status": final_status})}
    except asyncio.CancelledError:
        # 客户端断开 / ASGI 任务取消。不要吞掉异常：重新抛出，
        # 让 uvicorn + starlette 正确清理。也不要 yield 帧，
        # 客户端已断开，yield 会再次抛出异常。
        final_status = STATUS_CANCELLED
        logger.info(
            "stream_cancelled",
            extra={
                "thread_id": tid,
                "node": last_node,
                "event": "cancelled",
            },
        )
        raise
    except Exception as e:
        final_status = STATUS_FAILED
        logger.exception(
            "stream_failed",
            extra={
                "thread_id": tid,
                "node": last_node,
                "event": EVENT_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            },
        )
        yield {
            "event": EVENT_ERROR,
            "data": json.dumps({
                "thread_id": tid,
                "error_type": type(e).__name__,
                "message": str(e),
                "last_node": last_node,
            }),
        }
    finally:
        if tid:
            summary = f"last_node={last_node}" if last_node else None
            store.update(tid, status=final_status, summary=summary)
            logger.info(
                "run_end",
                extra={
                    "thread_id": tid,
                    "event": "run_end",
                    "final_status": final_status,
                    "last_node": last_node,
                },
            )
