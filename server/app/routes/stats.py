# routes/stats.py — 分类统计
# GET /api/stats:按颜色、状态汇总,附任务数、成功率与平均耗时。

from typing import Optional
from fastapi import APIRouter

from .. import db

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats(
    time_from_ms: Optional[int] = None,
    time_to_ms: Optional[int] = None,
) -> dict:
    """分类统计:统计口径与看板分类统计页一致,须与日志及现场结果一致。"""
    return db.stats(time_from_ms=time_from_ms, time_to_ms=time_to_ms)
