# routes/events.py — task_event 入库与查询
# POST /api/events:朱玉贺(控制)上报事件,event_id 幂等入库;
# GET  /api/events:看板增量拉取(since)+ 筛选 + 分页。

from typing import List, Optional
from fastapi import APIRouter, HTTPException

from .. import db
from ..models import TaskEvent

router = APIRouter(prefix="/api", tags=["events"])


@router.post("/events")
def post_events(events: List[TaskEvent]) -> dict:
    """幂等入库:相同 event_id 不重复入库,返回实际新增条数。"""
    if not events:
        return {"inserted": 0}
    inserted = db.ingest([e.model_dump() for e in events])
    return {"inserted": inserted}


@router.get("/events")
def get_events(
    since: Optional[str] = None,
    color: Optional[str] = None,
    status: Optional[str] = None,
    time_from_ms: Optional[int] = None,
    time_to_ms: Optional[int] = None,
    page: int = 1,
    page_size: int = 200,
):
    """查询事件,最新在前。since 传 event_id,仅返回该事件之后的事件(增量拉取)。"""
    return db.query(
        since_event_id=since,
        color=color,
        status=status,
        time_from_ms=time_from_ms,
        time_to_ms=time_to_ms,
        page=page,
        page_size=page_size,
    )
