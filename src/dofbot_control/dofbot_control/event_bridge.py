# -*- coding: utf-8 -*-
"""dofbot_event_bridge: 控制模块与记录服务之间的 HTTP 双向桥（朱玉贺）。

上行（朱玉贺 -> 严晨越）:
  订阅 ROS2 话题 /task_event, 转接口样例 JSON 后 POST 记录服务 /api/events。

下行（严晨越 -> 朱玉贺, 见 docs/联调冻结方案.md 附录五「下行桥接口规范」）:
  本地 HTTP 服务（默认 9100 端口）暴露三个端点:
    POST /task_command   指令下发 {request_id, action, demo_action?}
                         -> {accepted, state, error_code}
    GET  /status         状态查询 -> {state, self_check, demo}
    POST /config         配置下发（看板键名）-> {accepted}
  行为约定（参照 server/tests/fake_control.py）:
    - request_id 幂等: 重复请求返回相同结果, 不重复执行;
    - ROS2 服务调用 5s 超时 -> accepted=false + error_code=CONTROL_TIMEOUT, 不挂起看板;
    - 接收成功仅代表接受命令, 不代表运动已完成。

用法（launch 带 with_event_bridge:=true 时自动启动）:
  ros2 run dofbot_control dofbot_event_bridge
"""
import http.server
import json
import queue
import threading
import time
import urllib.request

import rclpy
from rclpy.node import Node

from ament_index_python.packages import get_package_share_directory

from dofbot_info.msg import ControlStatus, TaskEvent
from dofbot_info.srv import TaskCommand

from .config_loader import ConfigError, apply_runtime_config, load_config

COLORS = ("red", "yellow", "blue", "green")
ACTIONS = ("start", "stop", "self_check", "demo")


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


class _DownlinkHandler(http.server.BaseHTTPRequestHandler):
    """下行端点 HTTP 处理器（线程由 ThreadingHTTPServer 管理, bridge 由 EventBridge 注入）。"""

    bridge = None  # EventBridge 实例

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] == "/status":
            self._send(200, self.bridge.get_status())
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"accepted": False, "error_code": "BAD_JSON"})
            return
        path = self.path.split("?")[0]
        if path == "/task_command":
            self._send(200, self.bridge.handle_task_command(body))
        elif path == "/config":
            self._send(200, self.bridge.handle_config(body))
        else:
            self._send(404, {"detail": "not found"})

    def log_message(self, *args):  # 静默 stdlib 默认访问日志
        pass


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
        self._config_file = config_file
        server_cfg = config.get("server", {})
        self.server_url = server_cfg.get("url", "http://127.0.0.1:8000").rstrip("/")
        self.downlink_port = int(server_cfg.get("downlink_port", 9100))

        # ---- 上行: task_event -> POST /api/events ----
        self._queue = queue.Queue()
        self.create_subscription(TaskEvent, "task_event", self._on_event, 10)
        threading.Thread(target=self._run_uplink, daemon=True).start()

        # ---- 下行: HTTP 端点 -> ROS2 服务/状态/配置 ----
        self._state = "idle"
        self._request_cache = {}  # request_id -> 响应（幂等）
        self._cmd_client = self.create_client(TaskCommand, "task_command")
        self.create_subscription(ControlStatus, "control_status", self._on_status, 10)
        self._start_downlink()

        self.get_logger().info("桥接就绪: 上行 %s/api/events, 下行 0.0.0.0:%d" %
                               (self.server_url, self.downlink_port))

    # ------------------------------------------------------------------ 上行
    def _on_event(self, ev):
        if ev.color not in COLORS:
            return  # 自检/演示动作组等非分拣事件不进 task_event 契约
        self._queue.put(to_api_event(ev))

    def _run_uplink(self):
        while True:
            item = self._queue.get()
            batch = [item]
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
            data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status != 200:
                raise RuntimeError("HTTP %d: %s" % (resp.status, body[:200]))

    # ------------------------------------------------------------------ 下行
    def _start_downlink(self):
        _DownlinkHandler.bridge = self
        server = http.server.ThreadingHTTPServer(("0.0.0.0", self.downlink_port), _DownlinkHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def _on_status(self, msg):
        self._state = msg.state

    def get_status(self):
        """GET /status: 返回控制模块状态（self_check/demo 为占位, 参照 fake_control.py）。"""
        return {
            "state": self._state,
            "self_check": {"running": False, "items": [], "checked_at_ms": None},
            "demo": None,
        }

    def handle_task_command(self, body):
        """POST /task_command: request_id 幂等 + 转 ROS2 task_command 服务调用。"""
        request_id = str(body.get("request_id", "") or "")
        if request_id and request_id in self._request_cache:
            self.get_logger().info("request_id 幂等命中: %s" % request_id)
            return self._request_cache[request_id]
        action = str(body.get("action", "") or "")
        demo_action = str(body.get("demo_action", "") or "")
        resp = self._call_command(action, demo_action, request_id)
        if request_id:
            self._request_cache[request_id] = resp
        return resp

    def _call_command(self, action, demo_action, request_id):
        if action not in ACTIONS:
            return {"accepted": False, "state": self._state, "error_code": "BAD_ACTION"}
        if not self._cmd_client.wait_for_service(timeout_sec=5.0):
            return {"accepted": False, "state": self._state, "error_code": "CONTROL_TIMEOUT"}
        req = TaskCommand.Request()
        req.request_id = request_id
        req.action = action
        req.demo_action = demo_action
        future = self._cmd_client.call_async(req)
        deadline = time.time() + 5.0
        while not future.done() and time.time() < deadline:
            time.sleep(0.02)
        if not future.done():
            self.get_logger().warn("task_command %s 5s 超时" % action)
            return {"accepted": False, "state": self._state, "error_code": "CONTROL_TIMEOUT"}
        r = future.result()
        return {"accepted": r.accepted, "state": r.state, "error_code": r.error_code or None}

    def handle_config(self, body):
        """POST /config: 看板键名映射后写入运行时覆盖文件, 下次 start 热加载生效。"""
        try:
            apply_runtime_config(self._config_file, body)
            self.get_logger().info("配置已下发（运行时覆盖文件已写入）")
            return {"accepted": True}
        except Exception as exc:
            self.get_logger().error("配置下发失败: %s" % exc)
            return {"accepted": False, "error_code": "CONFIG_WRITE_FAILED"}


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
