# test_stats.py — 分类统计测试
# 统计口径:按颜色、按状态汇总,任务数按 task_id 去重,成功率 = 成功任务/总任务。

import os
import sys
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="jxb-test-stats-")
os.environ["JXB_DATA_DIR"] = _TMP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import app          # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tests.test_events import make_event  # noqa: E402


class StatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        import sqlite3
        from app.db import DB_PATH
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM events")

    def test_stats_aggregation(self):
        """3 个任务:2 成功 1 失败,平均耗时 1000ms,成功率 2/3。"""
        events = [
            # 任务 1:红,成功,耗时 1000ms
            make_event("T001", "queued", occurred_at_ms=1000, color="red"),
            make_event("T001", "run", occurred_at_ms=1100, color="red",
                       started_at_ms=1100),
            make_event("T001", "end", occurred_at_ms=2100, color="red",
                       status="succeeded", started_at_ms=1100, finished_at_ms=2100,
                       result_basis="controller_only"),
            # 任务 2:蓝,失败
            make_event("T002", "queued", occurred_at_ms=2000, color="blue"),
            make_event("T002", "end", occurred_at_ms=2200, color="blue",
                       status="failed", error_code="LOW_CONFIDENCE"),
            # 任务 3:红,成功,耗时 1000ms
            make_event("T003", "queued", occurred_at_ms=3000, color="red"),
            make_event("T003", "end", occurred_at_ms=4000, color="red",
                       status="succeeded", started_at_ms=3000, finished_at_ms=4000),
        ]
        self.client.post("/api/events", json=events)

        s = self.client.get("/api/stats").json()
        self.assertEqual(s["total_tasks"], 3, "任务数按 task_id 去重")
        self.assertEqual(s["succeeded"], 2)
        self.assertEqual(s["failed"], 1)
        self.assertAlmostEqual(s["success_rate"], 2 / 3, places=6)
        self.assertEqual(s["avg_duration_ms"], 1000.0, "平均耗时只统计有起止时间的终态事件")
        self.assertEqual(s["by_color"]["red"], {"succeeded": 2, "failed": 0})
        self.assertEqual(s["by_color"]["blue"], {"succeeded": 0, "failed": 1})

    def test_stats_time_filter(self):
        """时间范围过滤后统计同步收窄。"""
        events = [
            make_event("T001", "end", occurred_at_ms=1000, status="succeeded", color="red"),
            make_event("T002", "end", occurred_at_ms=5000, status="succeeded", color="red"),
        ]
        self.client.post("/api/events", json=events)
        s = self.client.get("/api/stats", params={"time_from_ms": 0, "time_to_ms": 3000}).json()
        self.assertEqual(s["total_tasks"], 1)
        self.assertEqual(s["succeeded"], 1)


if __name__ == "__main__":
    unittest.main()
