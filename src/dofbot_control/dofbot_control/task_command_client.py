# -*- coding: utf-8 -*-
"""task_command 客户端: 下发 start/stop/self_check/demo 指令（对应 7.5 与接口样例扩展）。

用法:
  ros2 run dofbot_control task_command_client start
  ros2 run dofbot_control task_command_client stop
  ros2 run dofbot_control task_command_client self_check
  ros2 run dofbot_control task_command_client demo --demo-action wave
"""
import argparse
import sys
import time

import rclpy
from rclpy.node import Node

from dofbot_info.srv import TaskCommand


class TaskCommandClient(Node):
    def __init__(self):
        super().__init__("task_command_client")
        self._client = self.create_client(TaskCommand, "task_command")

    def send(self, action, demo_action=""):
        if not self._client.wait_for_service(timeout_sec=5.0):
            print("[ERROR] task_command 服务不可用")
            return False
        req = TaskCommand.Request()
        req.request_id = "cli-%d" % int(time.time() * 1000)
        req.action = action
        req.demo_action = demo_action
        future = self._client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if not future.done():
            print("[ERROR] 请求超时")
            return False
        resp = future.result()
        print("action=%s%s -> accepted=%s, state=%s, error=%s" %
              (action, ("/" + demo_action) if demo_action else "",
               resp.accepted, resp.state, resp.error_code or "-"))
        return resp.accepted


def main(args=None):
    parser = argparse.ArgumentParser(description="task_command 指令客户端")
    parser.add_argument("action", choices=["start", "stop", "self_check", "demo"])
    parser.add_argument("--demo-action", default="", help="action=demo 时的动作名 wave/dance 等")
    argv = parser.parse_args(args[1:] if args else sys.argv[1:])
    rclpy.init()
    node = TaskCommandClient()
    try:
        node.send(argv.action, argv.demo_action)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
