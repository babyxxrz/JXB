# test_events.py — 事件入库与查询测试
# 覆盖验收 F3 的关键项:event_id 幂等入库、20 条记录完整率 100%、筛选与分页。
# 运行:cd server && python -m unittest tests.test_events -v

import os
import sys
import tempfile
import unittest
from pathlib import Path

# 在导入应用前把数据目录指到临时位置,测试互不污染、不留残库
_TMP = tempfile.mkdtemp(prefix="jxb-test-")
os.environ["JXB_DATA_DIR"] = _TMP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import app          # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def make_event(task_id, suffix, **over):
    """按 task_event 契约构造事件(可空字段用 null,不用 0 代替)。"""
    base = {
        "event_id": f"{task_id}-{suffix}",
        "task_id": task_id,
        "occurred_at_ms": 1_700_000_000_000,
        "status": "queued",
        "color": "red",
        "x_mm": 1.0, "y_mm": 2.0, "z_mm": 3.0,
        "started_at_ms": None, "finished_at_ms": None,
        "error_code": None, "mode": "simulation", "result_basis": "none",
    }
    base.update(over)
    return base


class EventsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # 每个用例前清空事件表
        import sqlite3
        from app.db import DB_PATH
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM events")

    def test_ingest_and_idempotent(self):
        """相同 event_id 不重复入库(契约幂等)。"""
        ev = make_event("T001", "queued")
        r1 = self.client.post("/api/events", json=[ev])
        r2 = self.client.post("/api/events", json=[ev])
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["inserted"], 1)
        self.assertEqual(r2.json()["inserted"], 0, "重复 event_id 应被忽略")
        events = self.client.get("/api/events").json()
        self.assertEqual(len(events), 1)

    def test_enum_validation(self):
        """契约枚举严格校验:非法 status/color/mode 返回 422,防止静默写入脏数据。"""
        bad_status = make_event("T010", "end", status="success")   # 契约无此值
        r = self.client.post("/api/events", json=[bad_status])
        self.assertEqual(r.status_code, 422)

        bad_color = make_event("T011", "end", status="succeeded", color="RED")
        r = self.client.post("/api/events", json=[bad_color])
        self.assertEqual(r.status_code, 422)

        bad_mode = make_event("T012", "end", status="succeeded", mode="mock")
        r = self.client.post("/api/events", json=[bad_mode])
        self.assertEqual(r.status_code, 422)

        # 全被拒绝,库里不应有任何残留
        self.assertEqual(len(self.client.get("/api/events").json()), 0)

    def test_null_fields_preserved(self):
        """未知坐标用 null 表示,查询结果不得把 null 变成 0。"""
        ev = make_event("T002", "queued", x_mm=None, y_mm=None, z_mm=None)
        self.client.post("/api/events", json=[ev])
        got = self.client.get("/api/events").json()[0]
        self.assertIsNone(got["x_mm"])
        self.assertIsNone(got["y_mm"])
        self.assertIsNone(got["z_mm"])

    def test_query_filters(self):
        """按颜色 / 状态 / 时间范围筛选。"""
        events = [
            make_event("T001", "end", occurred_at_ms=1000, status="succeeded", color="red"),
            make_event("T002", "end", occurred_at_ms=2000, status="failed", color="blue"),
            make_event("T003", "end", occurred_at_ms=3000, status="succeeded", color="green"),
        ]
        self.client.post("/api/events", json=events)

        red = self.client.get("/api/events", params={"color": "red"}).json()
        self.assertEqual([e["task_id"] for e in red], ["T001"])

        ok = self.client.get("/api/events", params={"status": "succeeded"}).json()
        self.assertEqual(len(ok), 2)

        win = self.client.get(
            "/api/events", params={"time_from_ms": 1500, "time_to_ms": 2500}
        ).json()
        self.assertEqual([e["task_id"] for e in win], ["T002"])

    def test_pagination(self):
        """分页:45 条按 20 条/页 → 第 3 页 5 条。"""
        events = [
            make_event(f"T{i:03d}", "end", occurred_at_ms=1000 + i, status="succeeded")
            for i in range(1, 46)
        ]
        self.client.post("/api/events", json=events)
        p1 = self.client.get("/api/events", params={"page": 1, "page_size": 20}).json()
        p3 = self.client.get("/api/events", params={"page": 3, "page_size": 20}).json()
        self.assertEqual(len(p1), 20)
        self.assertEqual(len(p3), 5)

    def test_since_incremental(self):
        """增量拉取:since 指定 event_id,只返回其后的新事件。"""
        events = [
            make_event("T001", "end", occurred_at_ms=1000),
            make_event("T002", "end", occurred_at_ms=2000),
            make_event("T003", "end", occurred_at_ms=3000),
        ]
        self.client.post("/api/events", json=events)
        since = self.client.get("/api/events", params={"since": "T001-end"}).json()
        self.assertEqual([e["task_id"] for e in since], ["T003", "T002"])

    def test_completeness_20(self):
        """验收 F3:20 条测试任务记录完整率 100%。"""
        events = [
            make_event(f"T{i:03d}", "end", occurred_at_ms=1000 + i, status="succeeded")
            for i in range(1, 21)
        ]
        r = self.client.post("/api/events", json=events)
        self.assertEqual(r.json()["inserted"], 20)
        got = self.client.get("/api/events", params={"page_size": 100}).json()
        got_ids = {e["event_id"] for e in got}
        self.assertEqual(got_ids, {e["event_id"] for e in events})
        # 完整率 = 可查询到的记录数 / 入库记录数
        self.assertEqual(len(got_ids) / len(events), 1.0, "20 条记录完整率应为 100%")


if __name__ == "__main__":
    unittest.main()
