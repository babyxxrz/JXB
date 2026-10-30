# routes/state.py — 设备状态、指令下发与参数配置
# GET  /api/state   看板读取设备状态(≤1s 轮询);
# POST /api/command task_command 契约:start/stop/self_check/demo;
# GET/PUT /api/config 参数配置(契约 8.2,运动中禁止修改运动相关参数)。

from fastapi import APIRouter, HTTPException

from .. import db
from ..control import ControlAdapter
from ..models import CommandIn, CommandOut, Config

router = APIRouter(prefix="/api", tags=["state"])

_adapter: ControlAdapter | None = None


def set_adapter(adapter: ControlAdapter) -> None:
    """由 main 注入控制适配器(mock / real)。"""
    global _adapter
    _adapter = adapter


@router.get("/state")
def get_state() -> dict:
    return _adapter.get_state()


@router.post("/command")
async def post_command(cmd: CommandIn) -> CommandOut:
    """task_command:接收成功仅代表接受命令,不代表运动已完成。"""
    accepted = False
    try:
        if cmd.action == "start":
            accepted = await _adapter.start()
        elif cmd.action == "stop":
            accepted = await _adapter.stop()
        elif cmd.action == "self_check":
            accepted = await _adapter.self_check()
        elif cmd.action == "demo":
            accepted = await _adapter.demo(cmd.demo_action or "")
        else:
            raise HTTPException(status_code=400, detail=f"未知指令:{cmd.action}")
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="真实控制桥接尚未实现(待定项 T1/T7)")

    return CommandOut(
        accepted=accepted,
        state=_adapter.get_state()["state"],
        error_code=None,
    )


@router.get("/config")
def get_config() -> dict:
    return db.load_config()


@router.put("/config")
def put_config(config: Config) -> dict:
    """保存参数配置。运动相关参数由前端在运动中锁定,后端再校验一次。"""
    if _adapter.get_state()["state"] != "idle":
        raise HTTPException(status_code=409, detail="运动中禁止修改运动相关参数")
    data = config.model_dump()
    db.save_config(data)
    return data
