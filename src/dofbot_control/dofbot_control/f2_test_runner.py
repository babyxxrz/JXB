# -*- coding: utf-8 -*-
"""F2/F4 验收测试工具（朱玉贺, 交付物"10 次实机分拣记录"的自动记录工具）。

模式一(缺省) 分拣测试: 连续 N 次分拣, 记录每次耗时与结果, 输出 CSV 并判定 F2
  (连续 10 次成功 >= 8 次; 单次 <= 20s 完成或报告失败)。
模式二 故障注入: F4 三类异常各注入 3 次(LOW_CONFIDENCE / OUT_OF_WORKSPACE / STOP_REQUESTED),
  校验 9 次均进入规定处理路径。

仿真/实机均可使用: 仿真由本工具直接发布检测帧; 实机时由张鹏源的检测接口发布真实帧,
  本工具仅负责记录（--listen 模式, 监听所有 task_event）。

用法:
  ros2 run dofbot_control f2_test --runs 10 --points "red,320,240;blue,260,240;..."
  ros2 run dofbot_control f2_test --runs 10 --random
  ros2 run dofbot_control f2_test --inject low_conf
  ros2 run dofbot_control f2_test --inject out_ws --points "..."
  ros2 run dofbot_control f2_test --inject stop --points "..."
  ros2 run dofbot_control f2_test --listen --duration 300
"""
import argparse
import csv
import os
import sys
import time

import rclpy
from rclpy.node import Node

from ament_index_python.packages import get_package_share_directory

from dofbot_info.msg import ControlStatus, DetectResult, Detection, TaskEvent
from dofbot_info.srv import TaskCommand

from .calibration import load_calibration
from .config_loader import load_config

TERMINAL = ("succeeded", "failed", "skipped", "stopped")
COLORS = ("red", "yellow", "blue", "green")


class F2TestRunner(Node):
    def __init__(self, runs, points, random_mode, inject, listen, duration_s):
        super().__init__("f2_test_runner")
        config_file = get_package_share_directory("dofbot_control") + "/config/dofbot_config.yaml"
        self.config = load_config(config_file)
        self.workspace = self.config["workspace"]
        self.calibration = load_calibration(self.config["calibration"]["file"])
        self.move_timeout_ms = self.config["control"]["move_timeout_ms"]

        self._runs = runs
        self._points = points
        self._random_mode = random_mode
        self._inject = inject
        self._listen = listen
        self._duration_s = duration_s

        self._state = "idle"
        self._waiting_for = None
        self._got = None
        self._records = []       # 分拣记录
        self._inject_records = []  # 注入记录
        self._seq = 0

        self.create_subscription(ControlStatus, "control_status", self._on_status, 10)
        self.create_subscription(TaskEvent, "task_event", self._on_event, 10)
        self._detect_pub = self.create_publisher(DetectResult, "detect_result", 10)
        self._cmd_client = self.create_client(TaskCommand, "task_command")

    # ------------------------------------------------------------------ 订阅
    def _on_status(self, msg):
        self._state = msg.state

    def _on_event(self, ev):
        # 任务事件 task_id 为 "<frame_id>-<detection_id>"; 闭环跳过事件为 "auto-<frame_id>-..."
        matches = (self._waiting_for and
                   (ev.task_id.startswith(self._waiting_for) or
                    ev.task_id.startswith("auto-" + self._waiting_for)))
        if ev.status in TERMINAL and matches:
            self._got = ev
        if self._listen:
            self._records.append(self._event_to_row(ev, "-"))
            self.get_logger().info("记录事件: %s %s" % (ev.task_id, ev.status))

    @staticmethod
    def _event_to_row(ev, index):
        duration = ""
        if ev.has_times and ev.started_at_ms:
            duration = ev.finished_at_ms - ev.started_at_ms
        return {
            "run_index": index,
            "task_id": ev.task_id,
            "color": ev.color,
            "x_mm": ev.x_mm if ev.has_position else "",
            "y_mm": ev.y_mm if ev.has_position else "",
            "z_mm": ev.z_mm if ev.has_position else "",
            "started_at_ms": ev.started_at_ms if ev.has_times else "",
            "finished_at_ms": ev.finished_at_ms if ev.has_times else "",
            "duration_ms": duration,
            "status": ev.status,
            "error_code": ev.error_code,
            "mode": ev.mode,
            "pass": "",
        }

    # ------------------------------------------------------------------ 辅助
    def _spin(self, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

    def _wait_for(self, predicate, timeout_s, what):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if predicate():
                return True
        self.get_logger().warn("等待超时: %s" % what)
        return False

    def _send_command(self, action):
        if not self._cmd_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error("task_command 服务不可用")
            return None
        req = TaskCommand.Request()
        req.request_id = "f2-%d" % int(time.time() * 1000)
        req.action = action
        future = self._cmd_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=15.0)
        return future.result() if future.done() else None

    def _publish_detection(self, color, u, v, confidence=0.95):
        self._seq += 1
        frame_id = "f2-%03d" % self._seq
        msg = DetectResult()
        msg.frame_id = frame_id
        msg.captured_at_ms = int(time.time() * 1000)
        msg.image_width_px = 640
        msg.image_height_px = 480
        det = Detection()
        det.detection_id = "f2-det-%03d" % self._seq
        det.color = color
        det.confidence = float(confidence)
        det.center_u_px = float(u)
        det.center_v_px = float(v)
        det.fallback = False
        msg.detections = [det]
        self._detect_pub.publish(msg)
        return frame_id

    def _in_workspace_mm(self, x, y):
        ws = self.workspace
        return ws["x_min_mm"] <= x <= ws["x_max_mm"] and ws["y_min_mm"] <= y <= ws["y_max_mm"]

    def _inv_map(self, x_mm, y_mm):
        """标定逆变换: 工作区内 mm 点 -> 图像像素点。需要 numpy, 无则返回 None。"""
        try:
            import numpy as np
            h = np.array(self.calibration.h, dtype=float)
            p = np.linalg.solve(h, np.array([x_mm, y_mm, 1.0]))
            return float(p[0] / p[2]), float(p[1] / p[2])
        except Exception as exc:
            self.get_logger().warn("标定逆变换失败(缺 numpy?): %s" % exc)
            return None

    def _gen_random_point(self, i):
        """工作区内随机 mm 点 -> 像素点。"""
        ws = self.workspace
        import random
        for _ in range(50):
            x = random.uniform(ws["x_min_mm"] * 0.7, ws["x_max_mm"] * 0.7)
            y = random.uniform(ws["y_min_mm"] * 0.7, ws["y_max_mm"] * 0.7)
            px = self._inv_map(x, y)
            if px and 0 <= px[0] <= 640 and 0 <= px[1] <= 480:
                return COLORS[i % 4], px[0], px[1], x, y
        raise RuntimeError("无法在工作区内生成随机点")

    # ------------------------------------------------------------------ 分拣测试
    def run_sort_test(self):
        if not self.calibration.valid:
            self.get_logger().error("标定无效, 无法运行分拣测试（请先 hand_eye_calibrate）")
            return
        self.get_logger().info("=== F2 分拣测试: %d 次 ===" % self._runs)
        resp = self._send_command("start")
        if resp is None or not resp.accepted:
            self.get_logger().error("启动失败: %s" % (resp and resp.error_code))
            return
        self._wait_for(lambda: self._state == "running", 10.0, "状态进入 running")
        points = []
        if self._points:
            points = list(self._points)
        for i in range(self._runs):
            if self._random_mode:
                try:
                    color, u, v, x_mm, y_mm = self._gen_random_point(i)
                except RuntimeError as exc:
                    self.get_logger().error("随机点生成失败(%s), 使用图像中心点" % exc)
                    color, u, v = COLORS[i % 4], 320.0, 240.0
                    x_mm, y_mm = self.calibration.to_mm(u, v)
            elif points:
                color, u, v = points[i % len(points)]
                x_mm, y_mm = self.calibration.to_mm(u, v)
            else:
                color, u, v = COLORS[i % 4], 320.0, 240.0
                x_mm, y_mm = self.calibration.to_mm(u, v)
            # 注意: skipped 类事件可能在发布后立即到达, 等待标志须在发布前设置
            self._waiting_for = "f2-%03d" % (self._seq + 1)
            self._got = None
            frame_id = self._publish_detection(color, u, v)
            timeout_s = self.move_timeout_ms / 1000.0 + 15.0
            ok = self._wait_for(lambda: self._got is not None, timeout_s, "任务 %s 终态事件" % frame_id)
            ev = self._got
            if not ok or ev is None:
                row = {"run_index": i + 1, "task_id": frame_id, "color": color,
                       "x_mm": round(x_mm, 1), "y_mm": round(y_mm, 1),
                       "z_mm": self.workspace["z_grasp_mm"],
                       "started_at_ms": "", "finished_at_ms": "", "duration_ms": "",
                       "status": "timeout", "error_code": "EVENT_TIMEOUT", "mode": "-", "pass": "FAIL"}
            else:
                row = self._event_to_row(ev, i + 1)
                duration = row["duration_ms"]
                row["pass"] = "PASS" if (ev.status == "succeeded" and
                                         duration != "" and duration <= 20000) else "FAIL"
            self._records.append(row)
            self.get_logger().info("第 %d 次: %s (%.1f, %.1f) mm -> %s %s %s" %
                                   (i + 1, color, x_mm, y_mm, row["status"],
                                    row["error_code"] or "-", row["pass"]))
            self._spin(0.5)
        self._send_command("stop")
        self._print_and_save_sort()

    def _print_and_save_sort(self):
        ok_count = sum(1 for r in self._records if r["pass"] == "PASS")
        over_time = sum(1 for r in self._records
                        if r["duration_ms"] not in ("", "-") and int(r["duration_ms"]) > 20000)
        print("\n===== F2 分拣记录 =====")
        for r in self._records:
            print("%3s  %-28s %-6s %-10s %-9s %-9s %s" %
                  (r["run_index"], r["task_id"], r["color"], r["status"],
                   str(r["duration_ms"]), r["error_code"] or "-", r["pass"]))
        f2_pass = ok_count >= max(8, int(self._runs * 0.8)) and over_time == 0
        print("成功 %d/%d, 超时 %d 次 -> F2 判定: %s" %
              (ok_count, len(self._records), over_time, "PASS" if f2_pass else "FAIL"))
        path = self._save_csv("f2_sort_", self._records,
                              ["run_index", "task_id", "color", "x_mm", "y_mm", "z_mm",
                               "started_at_ms", "finished_at_ms", "duration_ms", "status",
                               "error_code", "mode", "pass"])
        print("记录已保存: %s" % path)

    # ------------------------------------------------------------------ 故障注入
    def run_inject(self):
        self.get_logger().info("=== F4 故障注入: %s x3 ===" % self._inject)
        for iteration in range(1, 4):
            expected = {"low_conf": ("skipped", "LOW_CONFIDENCE"),
                        "out_ws": ("skipped", "OUT_OF_WORKSPACE"),
                        "stop": ("stopped", "STOP_REQUESTED")}[self._inject]
            row = {"fault_type": self._inject, "iteration": iteration,
                   "expected": "%s/%s" % expected, "observed": "-", "pass": "FAIL"}
            if self._inject == "low_conf":
                row["observed"] = self._inject_low_conf()
            elif self._inject == "out_ws":
                row["observed"] = self._inject_out_ws()
            else:
                row["observed"] = self._inject_stop()
            exp_status, exp_error = expected
            row["pass"] = "PASS" if (row["observed"].endswith(exp_error)) else "FAIL"
            self._inject_records.append(row)
            self.get_logger().info("注入 %s #%d: 期望 %s -> 观察 %s [%s]" %
                                   (self._inject, iteration, expected, row["observed"], row["pass"]))
        all_pass = all(r["pass"] == "PASS" for r in self._inject_records)
        print("\n===== F4 注入记录 (%s) =====" % self._inject)
        for r in self._inject_records:
            print("%d  %s -> %s [%s]" % (r["iteration"], r["expected"], r["observed"], r["pass"]))
        print("F4 判定: %s" % ("PASS" if all_pass else "FAIL"))
        path = self._save_csv("f2_inject_%s_" % self._inject, self._inject_records,
                              ["fault_type", "iteration", "expected", "observed", "pass"])
        print("记录已保存: %s" % path)

    def _start_once(self):
        resp = self._send_command("start")
        ok = resp is not None and resp.accepted
        if ok:
            self._wait_for(lambda: self._state == "running", 10.0, "状态进入 running")
        return ok

    def _inject_low_conf(self):
        if not self._start_once():
            return "start_failed"
        # 连续 3 帧低置信度(补采 2 帧仍不足 -> 跳过并记录 LOW_CONFIDENCE)
        self._waiting_for = "auto-f2-"
        self._got = None
        for _ in range(3):
            self._publish_detection("red", 320.0, 240.0, confidence=0.3)
            self._spin(0.6)
        self._wait_for(lambda: self._got is not None, 10.0, "LOW_CONFIDENCE 跳过事件")
        ev = self._got
        self._send_command("stop")
        return "%s/%s" % (ev.status, ev.error_code) if ev else "timeout"

    def _inject_out_ws(self):
        if not self._start_once():
            return "start_failed"
        # 图像角落像素经标定后必然落在工作区外
        corners = [(10.0, 10.0), (630.0, 470.0), (630.0, 10.0)]
        u, v = corners[(self._seq) % 3]
        self._waiting_for = "f2-%03d" % (self._seq + 1)
        self._got = None
        self._publish_detection("red", u, v)
        self._wait_for(lambda: self._got is not None, 10.0, "OUT_OF_WORKSPACE 跳过事件")
        ev = self._got
        self._send_command("stop")
        return "%s/%s" % (ev.status, ev.error_code) if ev else "timeout"

    def _inject_stop(self):
        if not self._start_once():
            return "start_failed"
        u = v = 320.0
        if self._points:
            _, u, v = self._points[0]
        self._waiting_for = "f2-%03d" % (self._seq + 1)
        self._got = None
        self._publish_detection("red", u, v)
        self._spin(1.5)  # 任务进入执行后下发停止
        self._send_command("stop")
        self._wait_for(lambda: self._got is not None, 15.0, "STOP_REQUESTED 停止事件")
        ev = self._got
        return "%s/%s" % (ev.status, ev.error_code) if ev else "timeout"

    # ------------------------------------------------------------------ 输出
    def _save_csv(self, prefix, rows, fieldnames):
        outdir = os.path.join(os.getcwd(), "f2_records")
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, "%s%s.csv" % (prefix, time.strftime("%Y%m%d_%H%M%S")))
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def run_listen(self):
        self.get_logger().info("监听模式 %d s, 记录所有 task_event ..." % self._duration_s)
        self._spin(self._duration_s)
        path = self._save_csv("f2_listen_", self._records,
                              ["run_index", "task_id", "color", "x_mm", "y_mm", "z_mm",
                               "started_at_ms", "finished_at_ms", "duration_ms", "status",
                               "error_code", "mode", "pass"])
        print("共记录 %d 条事件, 已保存: %s" % (len(self._records), path))


def parse_points(text):
    points = []
    for item in text.split(";"):
        parts = item.split(",")
        if len(parts) != 3:
            raise ValueError("点位格式错误: %s (应为 color,u_px,v_px)" % item)
        points.append((parts[0], float(parts[1]), float(parts[2])))
    return points


def main(args=None):
    parser = argparse.ArgumentParser(description="F2/F4 验收测试工具")
    parser.add_argument("--runs", type=int, default=10, help="分拣次数(缺省 10)")
    parser.add_argument("--points", default="", help='点位列表, 如 "red,320,240;blue,260,240"')
    parser.add_argument("--random", action="store_true", help="工作区内随机点")
    parser.add_argument("--inject", choices=["low_conf", "out_ws", "stop"], default=None,
                        help="F4 故障注入模式(各注入 3 次)")
    parser.add_argument("--listen", action="store_true", help="监听模式(实机: 仅记录事件)")
    parser.add_argument("--duration", type=int, default=300, help="监听时长, s")
    argv = parser.parse_args(args[1:] if args else sys.argv[1:])
    points = parse_points(argv.points) if argv.points else None

    rclpy.init()
    node = F2TestRunner(argv.runs, points, argv.random, argv.inject, argv.listen, argv.duration)
    try:
        if argv.listen:
            node.run_listen()
        elif argv.inject:
            node.run_inject()
        else:
            node.run_sort_test()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
