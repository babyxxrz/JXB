# -*- coding: utf-8 -*-
"""fake_detect: 仿真检测发布器（联调用, 模拟张鹏源的 detect 接口输出）。

等待上一帧对应任务进入终态后再发布下一帧, 符合"任务完成后必须重新检测"约定。

用法:
  ros2 run dofbot_control fake_detect --points "red,320,240;blue,220,200"
  ros2 run dofbot_control fake_detect --random 10
  ros2 run dofbot_control fake_detect --low-conf 3   # 连续 3 帧低置信度(触发 LOW_CONFIDENCE 兜底路径)
"""
import argparse
import sys
import time

import rclpy
from rclpy.node import Node

from dofbot_info.msg import DetectResult, Detection, TaskEvent

TERMINAL = ("succeeded", "failed", "skipped", "stopped")


def parse_points(text):
    points = []
    for item in text.split(";"):
        parts = item.split(",")
        if len(parts) != 3:
            raise ValueError("点位格式错误: %s (应为 color,u_px,v_px)" % item)
        points.append((parts[0], float(parts[1]), float(parts[2])))
    return points


class FakeDetectPublisher(Node):
    def __init__(self, points=None, random_n=0, low_conf_n=0, interval=0.5):
        super().__init__("fake_detect")
        self._points = list(points or [])
        self._random_n = random_n
        self._low_conf_n = low_conf_n
        self._interval = interval
        self._seq = 0
        self._pending_frame = None
        self._pub = self.create_publisher(DetectResult, "detect_result", 10)
        self.create_subscription(TaskEvent, "task_event", self._on_event, 10)
        self.create_timer(0.2, self._tick)
        self.get_logger().info("fake_detect 就绪: %d 个固定点, random=%d, low_conf=%d" %
                               (len(self._points), random_n, low_conf_n))

    def _on_event(self, ev):
        # 任务事件 task_id 为 "<frame_id>-<detection_id>"; 闭环跳过事件为 "auto-<frame_id>-..."
        matches = (self._pending_frame and
                   (ev.task_id.startswith(self._pending_frame) or
                    ev.task_id.startswith("auto-" + self._pending_frame)))
        if ev.status in TERMINAL and matches:
            self._pending_frame = None
            self.get_logger().info("帧 %s 任务已终态(%s), 可发布下一帧" %
                                   (ev.task_id.split("-")[0], ev.status))

    def _publish_frame(self, color, u, v, confidence, fallback=False):
        self._seq += 1
        frame_id = "sim-%03d" % self._seq
        msg = DetectResult()
        msg.frame_id = frame_id
        msg.captured_at_ms = int(time.time() * 1000)
        msg.image_width_px = 640
        msg.image_height_px = 480
        det = Detection()
        det.detection_id = "sim-det-%03d" % self._seq
        det.color = color
        det.confidence = float(confidence)
        det.center_u_px = float(u)
        det.center_v_px = float(v)
        det.fallback = fallback
        msg.detections = [det]
        self._pub.publish(msg)
        self._pending_frame = frame_id
        self.get_logger().info("发布检测帧 %s: %s at (%.0f, %.0f) conf=%.2f%s" %
                               (frame_id, color, u, v, confidence, " [fallback]" if fallback else ""))
        return frame_id

    def _next_point(self):
        """返回 (color, u, v, confidence) 或 None。--low-conf 模式发布低于阈值(0.5)的帧。"""
        if self._points:
            color, u, v = self._points.pop(0)
            return (color, u, v, 0.95)
        if self._random_n > 0:
            self._random_n -= 1
            return ("red", 240.0 + (self._random_n % 5) * 40.0, 240.0, 0.95)
        if self._low_conf_n > 0:
            self._low_conf_n -= 1
            return ("red", 320.0, 240.0, 0.3)
        return None

    def _tick(self):
        if self._pending_frame is not None:
            return
        point = self._next_point()
        if point is None:
            return
        color, u, v, confidence = point
        self._publish_frame(color, u, v, confidence)


def main(args=None):
    parser = argparse.ArgumentParser(description="仿真检测发布器")
    parser.add_argument("--points", default="", help='点位列表, 如 "red,320,240;blue,220,200"')
    parser.add_argument("--random", type=int, default=0, help="随机发布 N 帧(图像中心区域)")
    parser.add_argument("--low-conf", type=int, default=0, help="连续发布 N 帧低置信度检测")
    parser.add_argument("--interval", type=float, default=0.5, help="帧间隔, s")
    argv = parser.parse_args(args[1:] if args else sys.argv[1:])
    points = parse_points(argv.points) if argv.points else None
    rclpy.init()
    node = FakeDetectPublisher(points, argv.random, argv.low_conf, argv.interval)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
