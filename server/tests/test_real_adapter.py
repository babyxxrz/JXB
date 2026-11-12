# test_real_adapter.py — RealControlAdapter(HTTP 下行桥)测试
# 对假控制服务器(fake_control.py)验证:指令受理、状态轮询、不可达置 fault、
# 超时语义、配置下发。证明严晨越侧在朱玉贺桥接就绪前已可联调。
# 运行:cd server && python -m unittest tests.test_real_adapter -v

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
PORT = 8766
FAKE_URL = f"http://127.0.0.1:{PORT}"
LOG_FILE = Path(tempfile.mkdtemp(prefix="jxb-fake-")) / "fake.log"


def read_log():
    """读取假控制服务器收到的请求记录。"""
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class RealAdapterTest(unittest.TestCase):
    proc = None

    @classmethod
    def setUpClass(cls):
        env = {**os.environ, "FAKE_CONTROL_LOG": str(LOG_FILE)}
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "tests.fake_control:app",
             "--port", str(PORT), "--log-level", "warning"],
            cwd=SERVER_DIR, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # 等待假控制就绪
        import httpx
        deadline = time.monotonic() + 15
        while True:
            try:
                httpx.get(f"{FAKE_URL}/status", timeout=2)
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise RuntimeError("fake_control 启动超时")
                time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)

    def setUp(self):
        if LOG_FILE.exists():
            LOG_FILE.unlink()

    def make_adapter(self, url=FAKE_URL, timeout_s=5.0):
        from app.control import RealControlAdapter
        return RealControlAdapter(control_url=url, timeout_s=timeout_s)

    def test_commands_accepted_and_recorded(self):
        """start/stop/self_check/demo 均以契约结构下发并被接收。"""
        adapter = self.make_adapter()
        self.assertTrue(asyncio.run(adapter.start()))
        self.assertTrue(asyncio.run(adapter.self_check()))
        self.assertTrue(asyncio.run(adapter.demo("wave")))
        self.assertTrue(asyncio.run(adapter.stop()))

        log = read_log()
        actions = [e["action"] for e in log if e["kind"] == "task_command"]
        self.assertEqual(actions, ["start", "self_check", "demo", "stop"])
        # request_id 每次唯一
        ids = [e["request_id"] for e in log if e["kind"] == "task_command"]
        self.assertEqual(len(ids), len(set(ids)))
        # demo 带 demo_action 透传
        demo = [e for e in log if e.get("action") == "demo"][0]
        self.assertEqual(demo["demo_action"], "wave")

    def test_state_poll(self):
        """轮询 /status 后状态映射到 get_state。"""
        adapter = self.make_adapter()
        asyncio.run(adapter.start())          # 假控制转 running
        time.sleep(0.3)
        asyncio.run(adapter._poll_once())
        self.assertEqual(adapter.get_state()["state"], "running")

    def test_unreachable_reports_fault(self):
        """控制不可达:state 上报 fault,看板明示,不静默。"""
        adapter = self.make_adapter(url="http://127.0.0.1:1", timeout_s=1.0)
        asyncio.run(adapter._poll_once())
        self.assertEqual(adapter.get_state()["state"], "fault")
        # 指令在不可达时返回 accepted=false,不抛异常
        self.assertFalse(asyncio.run(adapter.start()))

    def test_command_timeout_returns_not_accepted(self):
        """指令超时(模拟 ROS2 服务 6s 无响应 > 5s 上限)→ accepted=false。"""
        adapter = self.make_adapter(timeout_s=1.0)
        t0 = time.monotonic()
        self.assertFalse(asyncio.run(adapter._command("slow")))
        self.assertLess(time.monotonic() - t0, 4, "超时应提前返回,不挂起看板")

    def test_push_config(self):
        """配置下发成功且内容与看板 /api/config 结构一致。"""
        adapter = self.make_adapter()
        cfg = {"confidence_threshold": 0.5, "workspace": {"x_min": -60}, "buzzer": True}
        self.assertTrue(asyncio.run(adapter.push_config(cfg)))
        log = [e for e in read_log() if e["kind"] == "config"]
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["confidence_threshold"], 0.5)

    def test_push_config_unreachable(self):
        """控制不可达:下发失败返回 False(保存优先,不抛异常)。"""
        adapter = self.make_adapter(url="http://127.0.0.1:1", timeout_s=1.0)
        self.assertFalse(asyncio.run(adapter.push_config({})))


if __name__ == "__main__":
    unittest.main()
