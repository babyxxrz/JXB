# main.py — 记录服务入口
# 三步运行:
#   cd server
#   pip install -r requirements.txt
#   python -m uvicorn app.main:app --port 8000
# 浏览器打开 http://127.0.0.1:8000 (前端静态页面与 API 同源同端口)。

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import db
from .control import MockControlAdapter, RealControlAdapter
from .routes import events, stats, state

# 控制适配器选择:环境变量 JXB_CONTROL=real 时走真实桥接,默认 mock 演示
CONTROL_MODE = os.environ.get("JXB_CONTROL", "mock")
adapter = MockControlAdapter() if CONTROL_MODE == "mock" else RealControlAdapter()

db.init_db()
state.set_adapter(adapter)

app = FastAPI(title="机械臂垃圾分拣 · 记录服务", version="0.1.0")

# 联调期放开跨域,方便控制模块/其他成员从任意来源调用 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由先注册,静态前端后挂载(Starlette 按注册顺序匹配)
app.include_router(events.router)
app.include_router(stats.router)
app.include_router(state.router)

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.on_event("shutdown")
def _cleanup():
    """进程退出时取消模拟引擎的后台任务。"""
    for task in getattr(adapter, "_pending", set()):
        task.cancel()
