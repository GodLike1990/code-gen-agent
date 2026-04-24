"""Request history endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from code_gen_agent.api.deps import get_request_store, valid_tid
from code_gen_agent.persistence import RequestStore

router = APIRouter(prefix="/agent/history")


@router.get("")
def list_history(store: RequestStore = Depends(get_request_store)) -> dict:
    return {"items": store.list()}


@router.get("/{thread_id}")
def get_history_item(
    thread_id: str = Depends(valid_tid),
    store: RequestStore = Depends(get_request_store),
) -> dict:
    rec = store.get(thread_id)
    if rec is None:
        raise HTTPException(404, "thread not found")
    return rec
