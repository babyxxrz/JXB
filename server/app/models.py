# models.py — 接口契约的 Pydantic 模型
# 字段名、类型与含义严格对应《技术设计文档》第 7 章,不得改名。
# 可空字段一律 Optional(None),不使用 0 代替。

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class TaskEvent(BaseModel):
    """task_event:朱玉贺(控制)→ 严晨越(记录服务)

    枚举字段按契约严格校验:值不合法返回 422,防止联调时静默写入脏数据。
    error_code 为"最低错误码"集合,允许按文档流程新增,故不做枚举限制。
    """
    event_id: str = Field(..., description="事件唯一标识(幂等键)")
    task_id: str = Field(..., description="任务唯一标识")
    occurred_at_ms: int = Field(..., description="发生时间戳,ms")
    status: Literal["queued", "running", "succeeded", "failed", "skipped", "stopped"]
    color: Literal["red", "yellow", "blue", "green"]
    x_mm: Optional[float] = Field(None, description="抓取坐标,未知用 null")
    y_mm: Optional[float] = Field(None, description="抓取坐标,未知用 null")
    z_mm: Optional[float] = Field(None, description="抓取坐标,未知用 null")
    started_at_ms: Optional[int] = Field(None, description="开始时间戳,ms")
    finished_at_ms: Optional[int] = Field(None, description="结束时间戳,ms")
    error_code: Optional[str] = Field(None, description="最低错误码见契约")
    mode: Literal["real", "fallback", "simulation"] = "real"
    result_basis: Literal["operator_confirmed", "controller_only", "none"] = "none"


class CommandIn(BaseModel):
    """task_command:严晨越(看板)→ 朱玉贺(控制)"""
    request_id: str = Field(..., description="请求标识")
    action: str = Field(..., description="start/stop/self_check/demo")
    demo_action: Optional[str] = Field(None, description="演示动作:wave/dance")


class CommandOut(BaseModel):
    """task_command 返回值:接收成功仅代表接受命令,不代表运动已完成"""
    accepted: bool
    state: str = Field(..., description="idle/running/stopping/fault")
    error_code: Optional[str] = None


class Config(BaseModel):
    """参数配置(契约 8.2):置信度阈值、工作区、容器位置、抓取高度、RGB 灯、蜂鸣器"""
    confidence_threshold: float = 0.5
    workspace: dict = Field(
        default_factory=lambda: {"x_min": -60, "x_max": 60, "y_min": -60, "y_max": 60},
        description="有效工作区,mm(≥120×120)",
    )
    grab_height_mm: float = 40
    bins: dict = Field(
        default_factory=lambda: {
            "red": {"x": 160, "y": 90},
            "yellow": {"x": 160, "y": -90},
            "blue": {"x": -160, "y": 90},
            "green": {"x": -160, "y": -90},
        },
        description="四色容器中心坐标,mm",
    )
    rgb_mode: str = "cycle"
    buzzer: bool = True
