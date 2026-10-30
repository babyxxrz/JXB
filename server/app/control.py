# control.py — 控制适配器
# 记录服务通过统一的适配器接口向控制模块下发指令、读取状态:
#   MockControlAdapter  无硬件演示:本地模拟状态机与分拣事件流,事件经与真实路径
#                       相同的 ingest() 入库,可当作朱玉贺模块的联调参照实现;
#   RealControlAdapter  真实控制:经 ROS2 桥接(待定项 T1/T7 确认后实现)。
# 契约:接收成功仅代表接受命令,不代表运动已完成;停止 ≤1s 内停止派发新动作。

import asyncio
import random
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from . import db

COLORS = ["red", "yellow", "blue", "green"]
ERRORS = ["LOW_CONFIDENCE", "OUT_OF_WORKSPACE", "CONTROL_TIMEOUT"]
STATES = ("idle", "running", "stopping", "fault")


class ControlAdapter(ABC):
    """控制模块抽象:state 取值为 idle/running/stopping/fault"""

    @abstractmethod
    def get_state(self) -> dict: ...

    @abstractmethod
    async def start(self) -> bool: ...

    @abstractmethod
    async def stop(self) -> bool: ...

    @abstractmethod
    async def self_check(self) -> bool: ...

    @abstractmethod
    async def demo(self, action: str) -> bool: ...


class MockControlAdapter(ControlAdapter):
    """演示用模拟控制:自检 → 分拣循环 → 停止,事件按契约字段入库。"""

    def __init__(self):
        self.state = "idle"
        self.self_check = {"running": False, "items": [], "checked_at_ms": None}
        self.demo = None
        self._seq = self._restore_seq()
        self._pending: set[asyncio.Task] = set()
        self._current: dict | None = None   # 在途任务:{task_id, terminal}

    # ------------------------------ 状态 ------------------------------

    def get_state(self) -> dict:
        return {"state": self.state, "self_check": self.self_check, "demo": self.demo}

    # ------------------------------ 指令 ------------------------------

    async def start(self) -> bool:
        """启动任务:自检通过后进入 running,再开始串行分拣。"""
        if self.state != "idle" or self.self_check["running"]:
            return False
        self.self_check["running"] = True
        items = ["舵机位置", "RGB 灯", "蜂鸣器"]
        for i, name in enumerate(items):
            self._spawn(self._check_step(name, last=(i == len(items) - 1), then_run=True), 0.45 * (i + 1))
        return True

    async def stop(self) -> bool:
        """停止:取消未派发动作,在途任务记 stopped(STOP_REQUESTED),≤1s 回待机。"""
        if self.state != "running" and not self.self_check["running"]:
            return False
        for t in list(self._pending):
            t.cancel()
        if self._current and not self._current["terminal"]:
            self._current["terminal"] = True
            now = self._now_ms()
            db.ingest([self._event(self._current["task_id"], "stop", now, {
                "status": "stopped",
                "occurred_at_ms": now,
                "finished_at_ms": now,
                "error_code": "STOP_REQUESTED",
            })])
        self._current = None
        self.self_check["running"] = False
        self.state = "stopping"
        self._spawn(self._to_idle(), 0.7)   # 停止请求 ≤1s 验收
        return True

    async def self_check(self) -> bool:
        """仅开机自检,不启动分拣。"""
        if self.state != "idle" or self.self_check["running"]:
            return False
        self.self_check["running"] = True
        items = ["舵机位置", "RGB 灯", "蜂鸣器"]
        for i, name in enumerate(items):
            self._spawn(self._check_step(name, last=(i == len(items) - 1)), 0.45 * (i + 1))
        return True

    async def demo(self, action: str) -> bool:
        """演示动作(挥手/舞蹈):仅演示,不产生分拣任务事件。"""
        if self.state != "idle" or self.demo:
            return False
        self.demo = {"action": action, "until_ms": self._now_ms() + 1800}
        self._spawn(self._end_demo(), 1.8)
        return True

    # ------------------------------ 内部 ------------------------------

    def _spawn(self, coro, delay_s: float):
        """延迟 delay_s 后执行一次协程(可被 stop 取消)。coro 为协程对象。"""
        async def _run():
            try:
                await asyncio.sleep(delay_s)
                await coro
            except asyncio.CancelledError:
                coro.close()   # 取消时关闭未执行的协程,避免"never awaited"告警
                raise
            finally:
                self._pending.discard(asyncio.current_task())

        task = asyncio.create_task(_run())
        self._pending.add(task)

    def _spawn_loop(self, coro):
        """启动一个长驻协程(分拣循环),同样可被 stop 取消。coro 为协程对象。"""
        async def _run():
            try:
                await coro
            except asyncio.CancelledError:
                coro.close()
                raise
            finally:
                self._pending.discard(asyncio.current_task())

        task = asyncio.create_task(_run())
        self._pending.add(task)

    async def _check_step(self, name: str, last: bool, then_run: bool = False):
        items = self.self_check["items"] + [{"name": name, "status": "ok"}]
        if last:
            self.self_check = {
                "running": False, "items": items, "checked_at_ms": self._now_ms(),
            }
            if then_run and self.state == "idle":
                self.state = "running"
                self._spawn_loop(self._pick_loop())
        else:
            self.self_check["running"] = True
            self.self_check["items"] = items

    async def _to_idle(self):
        self.state = "idle"

    async def _end_demo(self):
        self.demo = None

    async def _pick_loop(self):
        """串行分拣循环:单次分拣结束后才派发下一次。"""
        while self.state == "running":
            await self._pick_once()
            await asyncio.sleep(random.uniform(0.6, 1.5))

    async def _pick_once(self):
        cfg = db.load_config()
        color = random.choice(COLORS)
        task_id = f"T{self._seq:03d}"
        self._seq += 1
        ws = cfg["workspace"]
        x = round(random.uniform(ws["x_min"], ws["x_max"]), 1)
        y = round(random.uniform(ws["y_min"], ws["y_max"]), 1)
        z = cfg["grab_height_mm"]
        self._current = {"task_id": task_id, "terminal": False}

        now = self._now_ms()
        db.ingest([self._event(task_id, "queued", now, {
            "status": "queued", "color": color, "x_mm": x, "y_mm": y, "z_mm": z,
        })])

        await asyncio.sleep(random.uniform(0.7, 1.6))
        if not self._alive(task_id):
            return
        started = self._now_ms()
        db.ingest([self._event(task_id, "run", started, {
            "status": "running", "color": color, "x_mm": x, "y_mm": y, "z_mm": z,
            "occurred_at_ms": started, "started_at_ms": started,
        })])

        await asyncio.sleep(random.uniform(0.9, 2.1))
        if not self._alive(task_id):
            return
        self._current["terminal"] = True

        r = random.random()
        if r < 0.78:
            status, mode, err = "succeeded", "real", None
        elif r < 0.88:
            status, mode, err = "failed", "real", random.choice(ERRORS)
        elif r < 0.95:
            status, mode, err = "skipped", "fallback", "LOW_CONFIDENCE"
        else:
            status, mode, err = "succeeded", "fallback", None

        finished = self._now_ms()
        # 控制超时任务耗时 >20s,与验收"单次 ≤20s 完成或报告失败"一致
        duration_ms = 20500 + random.randint(0, 4000) if err == "CONTROL_TIMEOUT" \
            else random.randint(900, 2100)
        started_rec = finished - duration_ms if err == "CONTROL_TIMEOUT" else started
        db.ingest([self._event(task_id, "end", finished, {
            "status": status, "color": color, "x_mm": x, "y_mm": y, "z_mm": z,
            "occurred_at_ms": finished, "started_at_ms": started_rec,
            "finished_at_ms": finished, "error_code": err, "mode": mode,
            "result_basis": "controller_only" if status == "succeeded" else "none",
        })])
        self._current = None

    def _alive(self, task_id: str) -> bool:
        """任务仍在途且未被停止。"""
        return self._current is not None and self._current["task_id"] == task_id

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    @staticmethod
    def _restore_seq() -> int:
        """从库中恢复任务序号,保证 task_id 不重复。"""
        max_seq = 0
        for e in db.query(page_size=500):
            m = re.match(r"^T(\d+)$", e["task_id"] or "")
            if m:
                max_seq = max(max_seq, int(m.group(1)))
        return max_seq + 1

    @staticmethod
    def _event(task_id: str, suffix: str, occurred_ms: int, fields: dict) -> dict:
        return {
            "event_id": f"{task_id}-{suffix}",
            "task_id": task_id,
            "occurred_at_ms": occurred_ms,
            "status": "queued",
            "color": "red",
            "x_mm": None, "y_mm": None, "z_mm": None,
            "started_at_ms": None, "finished_at_ms": None,
            "error_code": None, "mode": "real", "result_basis": "none",
            **fields,
        }


class RealControlAdapter(ControlAdapter):
    """真实控制桥接占位(待定项 T1/T7:运行时通信链路与 ROS2 发行版确认后实现)。

    计划形态:通过 ROS2 服务调用朱玉贺的 pick_place / task_command,事件由其
    POST /api/events 入库,本类只负责指令转发与状态查询,不生成事件。
    """

    def __init__(self):
        self.state = "idle"

    def get_state(self) -> dict:
        return {"state": self.state, "self_check": {"running": False, "items": []}, "demo": None}

    async def start(self) -> bool:
        raise NotImplementedError("真实控制桥接待 T1/T7 确认后实现")

    async def stop(self) -> bool:
        raise NotImplementedError("真实控制桥接待 T1/T7 确认后实现")

    async def self_check(self) -> bool:
        raise NotImplementedError("真实控制桥接待 T1/T7 确认后实现")

    async def demo(self, action: str) -> bool:
        raise NotImplementedError("真实控制桥接待 T1/T7 确认后实现")
