# -*- coding: utf-8 -*-
"""dofbot_event_bridge: task_event 的 HTTP 桥接（朱玉贺 -> 严晨越, 对应接口样例）。

订阅控制模块的 ROS2 话题 `/task_event`, 把分拣事件转成接口样例的 JSON 格式,
POST 到记录服务 `POST /api/events`（严晨越 FastAPI, 幂等入库）。

契约要点（与 docs/接口样例.md 一致）:
- 请求体为事件数组; 坐标/时间未知用 JSON null 不用 0;
- task_event 仅承载分拣任务（color 必填枚举）, 非分拣事件（自检/演示动作组）不转发;
- 本桥接只负责事件上行, 指令下行(server -> ROS2 task_command)属待定项 T1/T7, 另议。

用法（launch 文件带 with_event_bridge:=true 时自动启动）:
  ros2 run dofbot_control dofbot_event_bridge
"""
import json
import queue
import threading
import urllib.error
import urllib.request

import rclpy
from rclpy.node import Node

from ament_index_python.packages import get_package_share_directory

from dofbot_info.msg import TaskEvent

from .config_loader import ConfigError, load_config

COLORS = ("red", "yellow", "blue", "green")


def to_api_event(ev):
    """ROS2 消息 -> 接口样例 JSON（null 语义转换）。"""
    return {
        "event_id": ev.event_id,
        "task_id": ev.task_id,
        "occurred_at_ms": ev.occurred_at_ms,
        "status": ev.status,
        "color": ev.color,
        "x_mm": ev.x_mm if ev.has_position else None,
        "y_mm": ev.y_mm if ev.has_position else None,
        "z_mm": ev.z_mm if ev.has_position else None,
        "started_at_ms": ev.started_at_ms if ev.has_times else None,
        "finished_at_ms": ev.finished_at_ms if ev.has_times else None,
        "error_code": ev.error_code or None,
        "mode": ev.mode,
        "result_basis": ev.result_basis,
    }


class EventBridge(Node):
    def __init__(self):
        super().__init__("dofbot_event_bridge")
        self.declare_parameter("config_file", "")
        config_file = self.get_parameter("config_file").value
        if not config_file:
            config_file = get_package_share_directory("dofbot_control") + "/config/dofbot_config.yaml"
        try:
            config = load_config(config_file)
        except ConfigError as exc:
            self.get_logger().fatal("配置加载失败: %s" % exc)
            raise
        self.server_url = (config.get("server", {}).get("url", "http://127.0.0.1:8000")).rstrip("/")

        self._queue = queue.Queue()
        self.create_subscription(TaskEvent, "task_event", self._on_event, 10)
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        self.get_logger().info("事件桥接就绪, 目标 %s/api/events" % self.server_url)

    def _on_event(self, ev):
        if ev.color not in COLORS:
            # 自检/演示动作组等非分拣事件不进 task_event 契约, 静默跳过
            self.get_logger().debug("跳过非分拣事件 task=%s status=%s" % (ev.task_id, ev.status))
            return
        self._queue.put(to_api_event(ev))

    def _run(self):
        while True:
            item = self._queue.get()
            batch = [item]
            # 尽量批量: 把当前积压的事件一起上报（服务端接受数组）
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                self._post(batch)
                self.get_logger().info("已上报 %d 条事件" % len(batch))
            except Exception as exc:
                self.get_logger().warn("上报失败(%d 条, 将丢弃): %s" % (len(batch), exc))

    def _post(self, events):
        data = json.dumps(events).encode("utf-8")
        req = urllib.request.Request(
            self.server_url + "/api/events",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status != 200:
                raise RuntimeError("HTTP %d: %s" % (resp.status, body[:200]))
            self.get_logger().debug("服务端响应: %s" % body)


def main(args=None):
    rclpy.init(args=args)
    node = EventBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
