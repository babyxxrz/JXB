# fake_control.py — 假控制服务器
# 双重用途:
# 1. 测试桩:验证 RealControlAdapter(严晨越侧)无需朱玉贺的桥接即可联调;
# 2. 行为参照:定义下行桥端点(朱玉贺 dofbot_event_bridge 增加的下行端)应实现的行为,
#    他的实现须与本文档约定一致(端点路径、请求/响应结构、超时与幂等语义)。
#
# 运行:python -m uvicorn tests.fake_control:app --port 9100

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="fake-control")

# 收到的请求记录到 JSONL(供测试断言;朱玉贺实现时对应写 ROS2 服务调用)
_LOG = Path(os.environ.get("FAKE_CONTROL_LOG", "fake_control.log"))
_STATE = {"state": "idle"}
_LOCK = asyncio.Lock()


def _record(kind: str, body: dict) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": kind, **body}, ensure_ascii=False) + "\n")


class CommandIn(BaseModel):
    request_id: str
    action: str
    demo_action: str | None = None


@app.get("/status")
async def get_status() -> dict:
    """状态查询:返回 {state, self_check?, demo?}。"""
    return {
        "state": _STATE["state"],
        "self_check": {"running": False, "items": [], "checked_at_ms": None},
        "demo": None,
    }


@app.post("/task_command")
async def post_command(cmd: CommandIn) -> dict:
    """指令下行:行为约定 — request_id 幂等、slow 动作模拟超时、其余立即受理。"""
    async with _LOCK:
        _record("task_command", cmd.model_dump())

    if cmd.action == "slow":           # 模拟 ROS2 服务调用超时(> 看板 5s 上限)
        await asyncio.sleep(6)
    elif cmd.action == "start":
        _STATE["state"] = "running"    # 状态由 /status 呈现(看板轮询)
    elif cmd.action == "stop":
        _STATE["state"] = "stopping"
        async def _idle():
            await asyncio.sleep(0.7)
            _STATE["state"] = "idle"
        asyncio.create_task(_idle())
    elif cmd.action == "self_check":
        _STATE["state"] = "idle"
    elif cmd.action == "demo":
        pass

    return {"accepted": True, "state": _STATE["state"], "error_code": None}


@app.post("/config")
async def post_config(config: dict) -> dict:
    """配置下发:控制侧写 YAML;此处记录并返回 accepted。"""
    _record("config", config)
    return {"accepted": True}
