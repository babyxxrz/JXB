# -*- coding: utf-8 -*-
"""dofbot_sorter: 单块积木分拣闭环（技术设计文档 3.1 流程）。

订阅张鹏源的 detect 结果, 完成:
  ① 目标选择: 置信度 >= 阈值且位于有效工作区内; 帧超过 1s 未用则重新采集; 禁止复用旧帧
  ② 标定转换: 图像坐标(px) -> 机械臂基坐标系(mm), 禁止直接将像素值当毫米值
  ③ 坐标校验: 有效工作区 = 相机可见 ∩ 标定有效 ∩ 机械臂可达 ∩ 路径无障碍 的交集
  ④ 提交 pick_place 服务; 任务完成后必须重新检测（frame_id 去重保证）
  ⑤ 异常兜底: 低置信度补采最多 2 帧仍不足 -> 跳过并记录 LOW_CONFIDENCE;
     HSV 兜底检测(fallback=True)直接采用并标记 mode=fallback（3.4 / 9.2）

话题:
  订阅 detect_result   (dofbot_info/msg/DetectResult)  张鹏源发布
  订阅 control_status  (dofbot_info/msg/ControlStatus) 控制服务广播
  发布 task_event      (dofbot_info/msg/TaskEvent)      skipped 类事件
"""
import time
import uuid

import rclpy
from rclpy.node import Node

from ament_index_python.packages import get_package_share_directory

from dofbot_info.msg import DetectResult, TaskEvent, ControlStatus
from dofbot_info.srv import PickPlace

from .calibration import CalibrationError, load_calibration
from .config_loader import ConfigError, load_config


class SorterNode(Node):
    def __init__(self):
        super().__init__("dofbot_sorter")
        self.declare_parameter("config_file", "")
        config_file = self.get_parameter("config_file").value
        if not config_file:
            config_file = get_package_share_directory("dofbot_control") + "/config/dofbot_config.yaml"
        try:
            self.config = load_config(config_file)
        except ConfigError as exc:
            self.get_logger().fatal("配置加载失败: %s" % exc)
            raise
        self.workspace = self.config["workspace"]
        self.detect_cfg = self.config["detect"]
        self.bin_override = self.config.get("bin_override", {})
        self._config_file = config_file

        try:
            self.calibration = load_calibration(self.config["calibration"].get("file"))
            self.get_logger().info("已加载标定 calibration_id=%s" % self.calibration.calibration_id)
        except CalibrationError as exc:
            self.calibration = None
            self.get_logger().error(str(exc))

        # 控制服务状态
        self._state = "idle"
        self._busy = True
        self._mode = "simulation"
        # 帧管理: 任务完成后必须重新检测, 禁止复用旧帧连续抓取
        self._last_used_frame_id = None
        self._low_conf_streak = 0

        self.create_subscription(DetectResult, "detect_result", self._on_detect, 10)
        self.create_subscription(ControlStatus, "control_status", self._on_status, 10)
        self._pp_client = self.create_client(PickPlace, "pick_place")
        self._event_pub = self.create_publisher(TaskEvent, "task_event", 10)
        self.get_logger().info("分拣闭环就绪, 等待 control_status 与 detect_result")

    def _reload_config(self):
        """热加载（提案 2）: 重新读取配置与标定, 看板 POST /config 后下次 start 生效。"""
        try:
            config = load_config(self._config_file)
        except ConfigError as exc:
            self.get_logger().error("配置重载失败(沿用旧配置): %s" % exc)
            return
        self.config = config
        self.workspace = config["workspace"]
        self.detect_cfg = config["detect"]
        self.bin_override = config.get("bin_override", {})
        try:
            self.calibration = load_calibration(config["calibration"].get("file"))
        except CalibrationError as exc:
            self.calibration = None
            self.get_logger().error(str(exc))
        self.get_logger().info("配置已热加载")

    def _on_status(self, msg):
        prev = self._state
        self._state = msg.state
        self._busy = msg.busy
        self._mode = msg.mode
        if prev != "running" and msg.state == "running":
            self._reload_config()  # 每次 start 进入 running 时热加载配置

    def _on_detect(self, msg):
        if self._state != "running" or self._busy:
            return
        if msg.frame_id == self._last_used_frame_id:
            return  # 旧帧不重复用于生成任务
        now_ms = int(time.time() * 1000)
        if now_ms - msg.captured_at_ms > self.detect_cfg["max_frame_age_ms"]:
            self.get_logger().info("丢弃过期帧 %s (age=%d ms), 等待重新采集" %
                                   (msg.frame_id, now_ms - msg.captured_at_ms))
            return

        # ① 目标选择: 置信度 >= 阈值; HSV 兜底结果(fallback=True)直接采用
        threshold = self.detect_cfg["confidence_threshold"]
        candidates = [d for d in msg.detections if d.fallback or d.confidence >= threshold]
        if not candidates:
            if not msg.detections:
                return  # 无目标返回空数组, 等待下一帧(3.1), 不产生跳过事件
            # 有检测但均低于阈值: 补采最多 2 帧仍不足 -> 跳过并记录 LOW_CONFIDENCE
            best = max(msg.detections, key=lambda d: d.confidence)
            self._low_conf_streak += 1
            self.get_logger().info("帧 %s 无有效目标(第 %d 次), 最高置信度 %.2f(阈值 %.2f)" %
                                   (msg.frame_id, self._low_conf_streak, best.confidence, threshold))
            if self._low_conf_streak >= 1 + self.detect_cfg["retry_frames_on_low_confidence"]:
                self._publish_skipped(msg, best, "LOW_CONFIDENCE")
                self._low_conf_streak = 0
                self._last_used_frame_id = msg.frame_id
            return
        self._low_conf_streak = 0
        det = max(candidates, key=lambda d: d.confidence)

        # ② 标定转换 + ③ 坐标校验
        if self.calibration is None:
            self._publish_skipped(msg, det, "NOT_CALIBRATED")
            self._last_used_frame_id = msg.frame_id
            return
        try:
            x_mm, y_mm = self.calibration.to_mm(det.center_u_px, det.center_v_px)
        except CalibrationError as exc:
            self.get_logger().error(str(exc))
            self._publish_skipped(msg, det, "CALIBRATION_ERROR")
            self._last_used_frame_id = msg.frame_id
            return
        ws = self.workspace
        if not (ws["x_min_mm"] <= x_mm <= ws["x_max_mm"] and
                ws["y_min_mm"] <= y_mm <= ws["y_max_mm"]):
            self.get_logger().warn("目标 (%.1f, %.1f) mm 超出工作区, 拒绝运动" % (x_mm, y_mm))
            self._publish_skipped(msg, det, "OUT_OF_WORKSPACE", x_mm, y_mm)
            self._last_used_frame_id = msg.frame_id
            return

        # ④ 提交 pick_place 服务
        if not self._pp_client.wait_for_service(timeout_sec=3.0):
            self.get_logger().error("pick_place 服务不可用")
            return
        req = PickPlace.Request()
        req.task_id = "%s-%s" % (msg.frame_id, det.detection_id)
        req.frame_id = msg.frame_id
        req.detection_id = det.detection_id
        req.color = det.color
        req.x_mm = float(x_mm)
        req.y_mm = float(y_mm)
        req.z_mm = float(ws["z_grasp_mm"])
        req.bin_id = self.bin_override.get(det.color, det.color)
        req.calibration_id = self.calibration.calibration_id
        req.mode = "fallback" if det.fallback else ""
        self._last_used_frame_id = msg.frame_id
        self.get_logger().info("提交分拣任务 %s: %s (%.1f, %.1f, %.1f) mm -> 容器 %s%s" %
                               (req.task_id, det.color, x_mm, y_mm, req.z_mm, req.bin_id,
                                " [fallback]" if det.fallback else ""))
        future = self._pp_client.call_async(req)
        future.add_done_callback(lambda fut, d=det: self._on_pp_response(fut, d))

    def _on_pp_response(self, future, det):
        """服务被拒绝时补记 skipped 事件（接受的任务由控制服务上报事件）。"""
        resp = future.result()
        if resp.accepted:
            return
        ctx = {"task_id": "rejected-%s-%s" % (det.detection_id, uuid.uuid4().hex[:6]),
               "color": det.color, "has_position": False,
               "mode_override": "fallback" if det.fallback else self._mode}
        self._publish_event(ctx, "skipped", resp.error_code)

    def _publish_skipped(self, frame, det, error, x_mm=None, y_mm=None):
        ctx = {
            "task_id": "auto-%s-%s" % (frame.frame_id, uuid.uuid4().hex[:6]),
            "color": det.color if det is not None else "",
            "x_mm": float(x_mm) if x_mm is not None else 0.0,
            "y_mm": float(y_mm) if y_mm is not None else 0.0,
            "z_mm": 0.0,
            "has_position": x_mm is not None,
            "mode_override": ("fallback" if det is not None and det.fallback else self._mode),
        }
        self._publish_event(ctx, "skipped", error)

    def _publish_event(self, ctx, status, error):
        ev = TaskEvent()
        ev.event_id = "%s-%s" % (ctx["task_id"], uuid.uuid4().hex[:8])
        ev.task_id = ctx["task_id"]
        ev.occurred_at_ms = int(time.time() * 1000)
        ev.status = status
        ev.color = ctx.get("color", "")
        ev.x_mm = ctx.get("x_mm", 0.0)
        ev.y_mm = ctx.get("y_mm", 0.0)
        ev.z_mm = ctx.get("z_mm", 0.0)
        ev.has_position = ctx.get("has_position", False)
        ev.has_times = False
        ev.error_code = error
        ev.mode = ctx.get("mode_override", self._mode)
        ev.result_basis = "none"
        self._event_pub.publish(ev)
        self.get_logger().info("task_event: task=%s status=%s error=%s mode=%s" %
                               (ev.task_id, ev.status, ev.error_code or "-", ev.mode))


def main(args=None):
    rclpy.init(args=args)
    node = SorterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
