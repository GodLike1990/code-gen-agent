"""图、API 和流式层的字符串常量中心。

集中管理所有字面量的好处：
- 单次 grep 即可找到所有使用点
- 拼写错误会产生 NameError，而非静默错误行为
- 后端与前端的 SSE 协议在此一目了然

后端 ↔ 前端协议
────────────────
EVENT_* 和 STATUS_* 常量在前端的映射：
  frontend/src/constants/events.ts   （SSE_EVENT 对象）
  frontend/src/constants/status.ts   （RUN_STATUS_* 对象）
此处任何重命名都必须同步修改前端对应文件。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 图节点名称
# 必须与 builder.py 中传给 StateGraph.add_node() 的字符串键一致
# ---------------------------------------------------------------------------
NODE_INTENT    = "intent"
NODE_CLARIFY   = "clarify"
NODE_DECOMPOSE = "decompose"
NODE_CODEGEN   = "codegen"
NODE_CHECKS    = "checks"
NODE_REPAIR    = "repair"
NODE_HITL      = "hitl"
NODE_VERIFY    = "verify"
NODE_PACKAGE   = "package"

# 有序流水线 — 仅用于迭代和文档
ALL_NODES = [
    NODE_INTENT, NODE_CLARIFY, NODE_DECOMPOSE, NODE_CODEGEN,
    NODE_CHECKS, NODE_REPAIR, NODE_HITL, NODE_VERIFY, NODE_PACKAGE,
]

# ---------------------------------------------------------------------------
# HITL 决策动作
# 由 hitl 节点写入 AgentState["next_action"]，由 route_after_hitl 消费
# 前端在 ResumeRequest.human_feedback["action"] 字段中发送
# ---------------------------------------------------------------------------
HITL_ACTION_RETRY = "retry"   # 重置 repair_attempts，重新运行 codegen
HITL_ACTION_PATCH = "patch"   # 合并用户提供的文件，重新运行 checks
HITL_ACTION_ABORT = "abort"   # 路由到 END，流式层将 final_status 标为 "aborted"

# ---------------------------------------------------------------------------
# routing.py 函数返回的路由目标
# 即 builder.py 中条件边 dispatch map 的字符串键
# ---------------------------------------------------------------------------
ROUTE_END      = "end"
ROUTE_CODEGEN  = NODE_CODEGEN
ROUTE_REPAIR   = NODE_REPAIR
ROUTE_HITL     = NODE_HITL
ROUTE_CLARIFY  = NODE_CLARIFY
ROUTE_DECOMPOSE = NODE_DECOMPOSE
ROUTE_VERIFY   = NODE_VERIFY
ROUTE_PACKAGE  = NODE_PACKAGE

# ---------------------------------------------------------------------------
# streaming.py 发出的 SSE 事件类型
# 前端订阅 GET /agent/runs/{tid}/events 并按事件名分发
# 对应前端 frontend/src/constants/events.ts
# ---------------------------------------------------------------------------
EVENT_STATE_DELTA   = "state_delta"    # 每次节点更新后发出，触发前端状态轮询
EVENT_INTERRUPT     = "interrupt"      # 通用 LangGraph interrupt（clarify 或 hitl）
EVENT_CLARIFY       = "clarify"        # Agent 需要用户澄清
EVENT_HITL          = "hitl"           # Agent 升级为人工介入
EVENT_HITL_DECISION = "hitl_decision"  # HITL 节点记录了用户决策
EVENT_DONE          = "done"           # 运行结束（data 中携带 final_status）
EVENT_ERROR         = "error"          # 未处理异常
# 节点级事件使用前缀 + 节点名，如 "node:intent"、"node:codegen"
EVENT_NODE_PREFIX   = "node:"

# ---------------------------------------------------------------------------
# 运行 final_status 值
# 由 streaming.py 写入 RequestStore，并包含在 "done" SSE 事件中
# 前端 RequirementRecord.status 联合类型必须涵盖所有这些值
#
# 与前端 RunStatus 的映射：
#   STATUS_INTERRUPTED → RunStatus "hitl"（前端对 HITL 暂停的别名）
#   STATUS_RUNNING     → RunStatus "running"
#   其余                → 同名
# ---------------------------------------------------------------------------
STATUS_RUNNING     = "running"
STATUS_DONE        = "done"
STATUS_INTERRUPTED = "interrupted"  # Agent 在 interrupt() 处暂停，等待人工输入
STATUS_ABORTED     = "aborted"      # 用户通过 HITL abort 主动终止运行
STATUS_CANCELLED   = "cancelled"    # 客户端中途断开（CancelledError）
STATUS_FAILED      = "failed"       # 未处理异常，agent 无法恢复

# ---------------------------------------------------------------------------
# interrupt 类型字符串
# 由 clarify/hitl 节点写入 interrupt() 值字典
# 供 runs.py GET /interrupt 告知前端展示哪种表单
# ---------------------------------------------------------------------------
INTERRUPT_TYPE_CLARIFY = "clarify"
INTERRUPT_TYPE_HITL    = "hitl"
