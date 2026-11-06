# -*- coding: utf-8 -*-
"""pick_place 手动客户端: 联调时直接下发一次固定点位抓取-搬运任务（对应 7.3）。

需要控制服务处于 running 状态（先 task_command_client start）。
calibration_id 缺省从标定文件读取。

用法:
  ros2 run dofbot_control pick_place_client red 80 40 60 --bin blue
"""
import argparse
import sys
import time
import uuid

import rclpy
from rclpy.node import Node

from ament_index_python.packages import get_package_share_directory

from dofbot_info.srv import PickPlace

from .calibration import load_calibration
from .config_loader import load_config


class PickPlaceClient(Node):
    def __init__(self):
        super().__init__("pick_place_client")
        self._client = self.create_client(PickPlace, "pick_place")

    def send(self, task_id, color, x_mm, y_mm, z_mm, bin_id, calibration_id, mode):
        if not self._client.wait_for_service(timeout_sec=5.0):
            print("[ERROR] pick_place 服务不可用")
            return False
        req = PickPlace.Request()
        req.task_id = task_id
        req.frame_id = "manual-%d" % int(time.time() * 1000)
        req.detection_id = "manual"
        req.color = color
        req.x_mm = float(x_mm)
        req.y_mm = float(y_mm)
        req.z_mm = float(z_mm)
        req.bin_id = bin_id
        req.calibration_id = calibration_id
        req.mode = mode
        future = self._client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if not future.done():
            print("[ERROR] 请求超时")
            return False
        resp = future.result()
        print("task_id=%s -> accepted=%s, status=%s, error=%s, event_id=%s" %
              (task_id, resp.accepted, resp.status, resp.error_code or "-", resp.event_id))
        return resp.accepted


def main(args=None):
    parser = argparse.ArgumentParser(description="pick_place 手动客户端")
    parser.add_argument("color", choices=["red", "yellow", "blue", "green"])
    parser.add_argument("x_mm", type=float, help="抓取坐标 x, mm（基坐标系）")
    parser.add_argument("y_mm", type=float, help="抓取坐标 y, mm")
    parser.add_argument("z_mm", type=float, help="抓取高度 z, mm")
    parser.add_argument("--bin", default=None, help="目标容器 red/yellow/blue/green, 缺省=同色容器")
    parser.add_argument("--calibration-id", default=None, help="标定版本, 缺省=当前标定文件")
    parser.add_argument("--mode", default="", help="空=按驱动模式; fallback=HSV 兜底")
    argv = parser.parse_args(args[1:] if args else sys.argv[1:])

    calibration_id = argv.calibration_id
    if calibration_id is None:
        config_file = get_package_share_directory("dofbot_control") + "/config/dofbot_config.yaml"
        config = load_config(config_file)
        calibration_id = load_calibration(config["calibration"]["file"]).calibration_id

    rclpy.init()
    node = PickPlaceClient()
    try:
        node.send("manual-%s" % uuid.uuid4().hex[:8], argv.color,
                  argv.x_mm, argv.y_mm, argv.z_mm,
                  argv.bin or argv.color, calibration_id, argv.mode)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
