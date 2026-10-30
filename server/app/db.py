# db.py — SQLite 存储层
# 事件以 event_id 唯一约束保证幂等入库(契约:相同 event_id 不重复入库);
# 每次操作独立连接,避免跨线程共享连接问题。

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.environ.get("JXB_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = Path(os.environ.get("JXB_DB_PATH", DATA_DIR / "jxb.db"))
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "confidence_threshold": 0.5,
    "workspace": {"x_min": -60, "x_max": 60, "y_min": -60, "y_max": 60},
    "grab_height_mm": 40,
    "bins": {
        "red": {"x": 160, "y": 90},
        "yellow": {"x": 160, "y": -90},
        "blue": {"x": -160, "y": 90},
        "green": {"x": -160, "y": -90},
    },
    "rgb_mode": "cycle",
    "buzzer": True,
}


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """建表(幂等)。event_id 加唯一约束,重复事件插入即忽略。"""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                occurred_at_ms INTEGER NOT NULL,
                status TEXT NOT NULL,
                color TEXT NOT NULL,
                x_mm REAL,
                y_mm REAL,
                z_mm REAL,
                started_at_ms INTEGER,
                finished_at_ms INTEGER,
                error_code TEXT,
                mode TEXT NOT NULL DEFAULT 'real',
                result_basis TEXT NOT NULL DEFAULT 'none'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON events(occurred_at_ms)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON events(status)")


def ingest(events: list[dict]) -> int:
    """幂等入库:重复 event_id 忽略,返回本次实际新增条数。"""
    if not events:
        return 0
    init_db()
    rows = [
        (
            e["event_id"], e["task_id"], e["occurred_at_ms"], e["status"], e["color"],
            e.get("x_mm"), e.get("y_mm"), e.get("z_mm"),
            e.get("started_at_ms"), e.get("finished_at_ms"),
            e.get("error_code"), e.get("mode", "real"), e.get("result_basis", "none"),
        )
        for e in events
    ]
    with _connect() as conn:
        before = conn.total_changes
        conn.executemany(
            """
            INSERT OR IGNORE INTO events
            (event_id, task_id, occurred_at_ms, status, color,
             x_mm, y_mm, z_mm, started_at_ms, finished_at_ms,
             error_code, mode, result_basis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return conn.total_changes - before


def query(
    since_event_id: Optional[str] = None,
    color: Optional[str] = None,
    status: Optional[str] = None,
    time_from_ms: Optional[int] = None,
    time_to_ms: Optional[int] = None,
    page: int = 1,
    page_size: int = 200,
) -> list[dict]:
    """查询事件,默认按时间倒序(最新的在前),支持增量拉取(since)。"""
    init_db()
    where, params = [], []

    if since_event_id:
        where.append(
            "occurred_at_ms > COALESCE("
            "(SELECT occurred_at_ms FROM events WHERE event_id = ?), 0)"
        )
        params.append(since_event_id)
    if color:
        where.append("color = ?")
        params.append(color)
    if status:
        where.append("status = ?")
        params.append(status)
    if time_from_ms is not None:
        where.append("occurred_at_ms >= ?")
        params.append(time_from_ms)
    if time_to_ms is not None:
        where.append("occurred_at_ms <= ?")
        params.append(time_to_ms)

    sql = "SELECT * FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY occurred_at_ms DESC, id DESC LIMIT ? OFFSET ?"
    params += [max(1, page_size), max(0, (page - 1) * page_size)]

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def count(
    color: Optional[str] = None,
    status: Optional[str] = None,
    time_from_ms: Optional[int] = None,
    time_to_ms: Optional[int] = None,
) -> int:
    """按条件统计总数(用于分页与完整率校验)。"""
    init_db()
    where, params = [], []
    if color:
        where.append("color = ?")
        params.append(color)
    if status:
        where.append("status = ?")
        params.append(status)
    if time_from_ms is not None:
        where.append("occurred_at_ms >= ?")
        params.append(time_from_ms)
    if time_to_ms is not None:
        where.append("occurred_at_ms <= ?")
        params.append(time_to_ms)
    sql = "SELECT COUNT(*) FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    with _connect() as conn:
        return conn.execute(sql, params).fetchone()[0]


def stats(time_from_ms: Optional[int] = None, time_to_ms: Optional[int] = None) -> dict:
    """分类统计:按颜色、按状态汇总,附任务数与平均耗时。"""
    init_db()
    where, params = [], []
    if time_from_ms is not None:
        where.append("occurred_at_ms >= ?")
        params.append(time_from_ms)
    if time_to_ms is not None:
        where.append("occurred_at_ms <= ?")
        params.append(time_to_ms)

    def cond_sql(extra: list[str] = None) -> tuple[str, list]:
        parts = where + (extra or [])
        return (" WHERE " + " AND ".join(parts)) if parts else "", params

    with _connect() as conn:
        by_status = {
            r["status"]: r["n"]
            for r in conn.execute(
                f"SELECT status, COUNT(*) AS n FROM events{cond_sql()[0]} GROUP BY status",
                cond_sql()[1],
            ).fetchall()
        }
        # 口径与看板「各颜色分拣结果」图一致:只计成功/失败终态,不含中间状态
        by_color = {
            r["color"]: {"succeeded": r["ok"], "failed": r["bad"]}
            for r in conn.execute(
                f"""
                SELECT color,
                       SUM(CASE WHEN status='succeeded' THEN 1 ELSE 0 END) AS ok,
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS bad
                FROM events{cond_sql()[0]} GROUP BY color
                """,
                cond_sql()[1],
            ).fetchall()
        }
        tasks = conn.execute(
            f"SELECT COUNT(DISTINCT task_id) FROM events{cond_sql()[0]}", cond_sql()[1]
        ).fetchone()[0]
        avg_dur = conn.execute(
            f"""
            SELECT AVG(finished_at_ms - started_at_ms) FROM events
            {cond_sql(["finished_at_ms IS NOT NULL", "started_at_ms IS NOT NULL"])[0]}
            """,
            cond_sql(["finished_at_ms IS NOT NULL", "started_at_ms IS NOT NULL"])[1],
        ).fetchone()[0]

    succeeded = by_status.get("succeeded", 0)
    return {
        "total_tasks": tasks,
        "by_status": by_status,
        "by_color": by_color,
        "succeeded": succeeded,
        "failed": by_status.get("failed", 0),
        "success_rate": (succeeded / tasks) if tasks else None,
        "avg_duration_ms": round(avg_dur, 1) if avg_dur is not None else None,
    }


def load_config() -> dict:
    """读取参数配置(缺失时用默认值并回写)。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        return {**DEFAULT_CONFIG, **saved}
    except FileNotFoundError:
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
