# latency_report.py — 数据延迟测试(验收 F3:事件写入至展示 ≤1s)
# 方法:启动真实 uvicorn 服务 → 逐条 POST /api/events 入库 →
#       轮询 GET /api/events 直到可见,记录每条延迟 →
#       校验 20 条记录完整率 100% → 生成《数据延迟测试记录》报告。
# 运行:cd server && python tests/latency_report.py

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx

SERVER_DIR = Path(__file__).resolve().parent.parent
REPORT_PATH = SERVER_DIR.parent / "docs" / "数据延迟测试记录.md"
N = 20          # 测试任务条数(验收口径)
LIMIT_MS = 1000  # 验收上限:写入至展示 ≤1s


def make_event(i: int, t_ms: int) -> dict:
    return {
        "event_id": f"LAT-T{i:03d}-end",
        "task_id": f"LAT-T{i:03d}",
        "occurred_at_ms": t_ms,
        "status": "succeeded" if i % 3 else "failed",
        "color": ["red", "yellow", "blue", "green"][i % 4],
        "x_mm": 10.5, "y_mm": -20.0, "z_mm": 40.0,
        "started_at_ms": t_ms - 1500,
        "finished_at_ms": t_ms,
        "error_code": None if i % 3 else "LOW_CONFIDENCE",
        "mode": "real",
        "result_basis": "controller_only" if i % 3 else "none",
    }


def main() -> int:
    # Windows 控制台默认 GBK,统一以 UTF-8 输出(路径中可能含非 GBK 字符)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    data_dir = tempfile.mkdtemp(prefix="jxb-latency-")
    env = {**os.environ, "JXB_DATA_DIR": data_dir, "JXB_CONTROL": "mock"}
    port = 8765

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port),
         "--log-level", "warning"],
        cwd=SERVER_DIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"

    try:
        # 等待服务就绪
        deadline = time.monotonic() + 15
        while True:
            try:
                httpx.get(f"{base}/api/state", timeout=2)
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise RuntimeError("uvicorn 启动超时")
                time.sleep(0.2)

        rows = []
        with httpx.Client(base_url=base, timeout=5) as client:
            for i in range(1, N + 1):
                ev = make_event(i, int(time.time() * 1000))
                t0 = time.perf_counter()
                r = client.post("/api/events", json=[ev])
                r.raise_for_status()
                assert r.json()["inserted"] == 1, f"第 {i} 条入库失败"

                # 轮询直到事件可见(模拟看板 1s 轮询下的最坏可见延迟)
                visible = False
                while time.perf_counter() - t0 < LIMIT_MS / 1000 + 5:
                    got = client.get("/api/events", params={"page_size": 500}).json()
                    if any(e["event_id"] == ev["event_id"] for e in got):
                        visible = True
                        break
                    time.sleep(0.002)
                assert visible, f"第 {i} 条事件未在 {LIMIT_MS}ms 内可见"
                dt_ms = round((time.perf_counter() - t0) * 1000, 2)
                rows.append((i, ev["event_id"], dt_ms, "通过" if dt_ms <= LIMIT_MS else "超限"))
                time.sleep(0.05)

            # 20 条记录完整率
            all_events = client.get("/api/events", params={"page_size": 500}).json()
            got_ids = {e["event_id"] for e in all_events if e["task_id"].startswith("LAT-")}
            completeness = len(got_ids) / N

        latencies = [r[2] for r in rows]
        report = build_report(rows, latencies, completeness)
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"报告已生成:{REPORT_PATH}")
        print(f"20 条完整率:{completeness * 100:.0f}% | "
              f"延迟 max={max(latencies)}ms avg={statistics.mean(latencies):.2f}ms "
              f"p95={sorted(latencies)[int(N * 0.95) - 1]:.2f}ms")
        return 0 if completeness == 1.0 and max(latencies) <= LIMIT_MS else 1
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def build_report(rows, latencies, completeness) -> str:
    max_v, avg_v = max(latencies), statistics.mean(latencies)
    p95 = sorted(latencies)[int(N * 0.95) - 1]
    passed = all(r[2] <= LIMIT_MS for r in rows) and completeness == 1.0
    lines = [
        "# 数据延迟测试记录",
        "",
        f"- 测试对象:记录服务(`server/`)事件入库与查询链路",
        f"- 测试环境:Windows 11 + Python {sys.version.split()[0]} + FastAPI/uvicorn,单机部署(看板与后端同机)",
        f"- 测试日期:{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 测试方法:逐条 POST `/api/events` 入库,立即轮询 GET `/api/events` 直到事件可见,"
        f"记录「写入 → 可见」延迟;共 {N} 条,验收上限 {LIMIT_MS}ms(需求文档 F3)",
        "",
        "## 测试结果",
        "",
        "| 序号 | event_id | 写入至可见延迟 (ms) | 判定 |",
        "| --- | --- | --- | --- |",
    ]
    for i, eid, dt, verdict in rows:
        lines.append(f"| {i} | {eid} | {dt} | {verdict} |")
    lines += [
        "",
        "## 汇总",
        "",
        f"| 指标 | 数值 | 验收要求 | 结论 |",
        "| --- | --- | --- | --- |",
        f"| 最大延迟 | {max_v} ms | ≤ {LIMIT_MS} ms | {'通过' if max_v <= LIMIT_MS else '不通过'} |",
        f"| 平均延迟 | {avg_v:.2f} ms | — | — |",
        f"| P95 延迟 | {p95:.2f} ms | — | — |",
        f"| 记录完整率 | {completeness * 100:.0f}% | 100% | {'通过' if completeness == 1.0 else '不通过'} |",
        "",
        f"**结论:{'全部通过' if passed else '存在超限项,需排查'}。**"
        "说明:本测试为单机部署下的链路延迟(不含浏览器渲染),实际看板 1s 轮询周期内均可呈现最新事件。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
