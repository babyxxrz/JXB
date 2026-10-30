# test_flow.py — 指令闭环测试(模拟控制适配器)
# 启动 → 自检 → running → 分拣事件 → 停止 → 待机,事件经真实 ingest 路径入库。
# 运行:cd server && python -m unittest tests.test_flow -v

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="jxb-test-flow-")
os.environ["JXB_DATA_DIR"] = _TMP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import app          # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def wait_until(fn, timeout_s, interval_s=0.1):
    """轮询直到条件成立,超时报错。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if fn():
            return
        time.sleep(interval_s)
    raise AssertionError(f"等待超时({timeout_s}s)")


class FlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 以上下文管理器启动 TestClient:后台异步任务(模拟控制引擎)依赖常驻事件循环
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        # 用例开始前确保设备待机
        self.client.post("/api/command", json={"request_id": "r-setup", "action": "stop"})
        wait_until(
            lambda: self.client.get("/api/state").json()["state"] == "idle", 3
        )
        import sqlite3
        from app.db import DB_PATH
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM events")

    def test_start_pick_stop_cycle(self):
        """启动 → running → 出现终态事件 → 停止 → 待机,停止后不再产生新事件。"""
        # 启动(自检通过后进入 running)
        r = self.client.post("/api/command", json={"request_id": "r1", "action": "start"})
        self.assertTrue(r.json()["accepted"])
        wait_until(
            lambda: self.client.get("/api/state").json()["state"] == "running", 8
        )

        # 等待至少一条终态事件(succeeded/failed/skipped)
        def has_terminal():
            evs = self.client.get("/api/events").json()
            return any(e["status"] in ("succeeded", "failed", "skipped") for e in evs)
        wait_until(has_terminal, 30)

        # 停止:≤1s 内停止派发,状态经 stopping 回到 idle
        r = self.client.post("/api/command", json={"request_id": "r2", "action": "stop"})
        self.assertTrue(r.json()["accepted"])
        wait_until(
            lambda: self.client.get("/api/state").json()["state"] == "idle", 3
        )

        count = len(self.client.get("/api/events").json())
        time.sleep(2.5)
        self.assertEqual(
            len(self.client.get("/api/events").json()), count,
            "停止后不应继续产生事件",
        )

    def test_reject_double_start(self):
        """运行中重复启动被拒绝(accepted=false)。"""
        self.client.post("/api/command", json={"request_id": "r3", "action": "start"})
        wait_until(
            lambda: self.client.get("/api/state").json()["state"] == "running", 8
        )
        r = self.client.post("/api/command", json={"request_id": "r4", "action": "start"})
        self.assertFalse(r.json()["accepted"], "运行中重复启动应被拒绝")

    def test_config_motion_locked_while_running(self):
        """运动中修改运动相关参数 → 409;仅改非运动参数 → 放行(契约 6.6)。"""
        self.client.post("/api/command", json={"request_id": "r5", "action": "start"})
        wait_until(
            lambda: self.client.get("/api/state").json()["state"] == "running", 8
        )
        cfg = self.client.get("/api/config").json()

        # 改工作区(运动参数)→ 409
        cfg["workspace"]["x_max"] += 10
        r = self.client.put("/api/config", json=cfg)
        self.assertEqual(r.status_code, 409, "运动相关参数运动中应被拒绝")
        cfg["workspace"]["x_max"] -= 10

        # 只改 RGB 模式(非运动参数)→ 200
        cfg["rgb_mode"] = "off" if cfg["rgb_mode"] != "off" else "solid"
        r = self.client.put("/api/config", json=cfg)
        self.assertEqual(r.status_code, 200, "非运动参数运动中应允许修改")
        self.assertEqual(self.client.get("/api/config").json()["rgb_mode"], cfg["rgb_mode"])


if __name__ == "__main__":
    unittest.main()
