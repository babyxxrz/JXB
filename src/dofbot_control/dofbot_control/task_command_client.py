# -*- coding: utf-8 -*-
"""task_command 客户端: 下发 start/stop 启停指令（对应 7.5, 严晨越看板同款调用方式）。

用法:
  ros2 run dofbot_control task_command_client start
  ros2 run dofbot_control task_command_client stop
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

    def send(self, action):
        if not self._client.wait_for_service(timeout_sec=5.0):
            print("[ERROR] task_command 服务不可用")
            return False
        req = TaskCommand.Request()
        req.request_id = "cli-%d" % int(time.time() * 1000)
        req.action = action
        future = self._client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if not future.done():
            print("[ERROR] 请求超时")
            return False
        resp = future.result()
        print("action=%s -> accepted=%s, state=%s, error=%s" %
              (action, resp.accepted, resp.state, resp.error_code or "-"))
        return resp.accepted


def main(args=None):
    parser = argparse.ArgumentParser(description="task_command 启停客户端")
    parser.add_argument("action", choices=["start", "stop"])
    argv = parser.parse_args(args[1:] if args else sys.argv[1:])
    rclpy.init()
    node = TaskCommandClient()
    try:
        node.send(argv.action)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
