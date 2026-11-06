# -*- coding: utf-8 -*-
"""dofbot_control_server: 机械臂控制模块主服务节点（朱玉贺）。

对应技术设计文档第 5 章:
- 5.3 pick_place 服务: 校验坐标范围与机械臂状态后串行执行动作, 禁止并行执行两项运动任务
- 5.4 运动控制与动作组: 挥手/舞蹈演示、固定点位夹取搬运与堆叠
- 5.5 停止与异常处理: STOP_REQUESTED <= 1s 停止派发新动作; CONTROL_TIMEOUT(>20s) 记失败
- 5.6 开机自检: 读取舵机位置、RGB 灯循环红绿蓝、蜂鸣器短响
- 7.4 task_event 上报; 7.5 task_command 接收

话题/服务:
  服务  pick_place         (dofbot_info/srv/PickPlace)     张鹏源/闭环触发
  服务  task_command       (dofbot_info/srv/TaskCommand)   严晨越下发 start/stop
  服务  play_action_group  (dofbot_info/srv/PlayActionGroup) 看板触发演示动作组
  服务  confirm_task       (dofbot_info/srv/ConfirmTask)   操作人确认抓取结果
  话题  task_event         (dofbot_info/msg/TaskEvent)     事件上报(严晨越订阅)
  话题  control_status     (dofbot_info/msg/ControlStatus) 状态广播(闭环/看板)
"""
import math
import threading
import time
import uuid

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from ament_index_python.packages import get_package_share_directory

from dofbot_info.msg import ControlStatus, TaskEvent
from dofbot_info.srv import ConfirmTask, Kinemarics, PickPlace, PlayActionGroup, TaskCommand

from .calibration import CalibrationError, load_calibration
from .config_loader import ConfigError, load_config
from .drivers import DriverError, create_driver

COLORS = ("red", "yellow", "blue", "green")
TERMINAL_STATUS = ("succeeded", "failed", "skipped", "stopped")


class ControlError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code


class ControlServer(Node):
    def __init__(self):
        super().__init__("dofbot_control_server")
        self.declare_parameter("config_file", "")
        config_file = self.get_parameter("config_file").value
        if not config_file:
            config_file = get_package_share_directory("dofbot_control") + "/config/dofbot_config.yaml"
        try:
            self.config = load_config(config_file)
        except ConfigError as exc:
            self.get_logger().fatal("配置加载失败: %s" % exc)
            raise
        self.control = self.config["control"]
        self.workspace = self.config["workspace"]

        # 标定（对应 5.1, 标定文件不存在时服务仍启动, 但 pick_place 拒绝执行）
        self.calibration = None
        try:
            self.calibration = load_calibration(self.config["calibration"].get("file"))
            self.get_logger().info("已加载标定 calibration_id=%s" % self.calibration.calibration_id)
        except CalibrationError as exc:
            self.get_logger().error(str(exc))

        # 驱动层（实机 Arm_Lib / 仿真, 见 drivers.py）
        self.driver = create_driver(self.config["driver"], self.get_logger())
        self.get_logger().info("驱动模式: %s" % self.driver.mode)
        try:
            self.driver.connect()
        except DriverError as exc:
            self.get_logger().fatal("驱动连接失败: %s" % exc)
            raise

        # 状态机: idle -> running -> stopping -> fault(人工复位)
        self._lock = threading.RLock()  # 可重入: 回调持锁时发布终态事件会再次加锁
        self._state = "idle"
        self._busy = False
        self._stop_event = threading.Event()
        self._executed_task_ids = set()     # task_id 幂等: 相同 task_id 不重复执行
        self._terminal_events = {}          # task_id -> 终态事件(供操作人确认)
        self._gripper_deg = self.config["robot"]["gripper_open_deg"]

        # 反解服务客户端（任务2 的 trial_service）
        self._ik_client = self.create_client(Kinemarics, "trial_service")

        # 服务
        self.create_service(PickPlace, "pick_place", self._on_pick_place)
        self.create_service(TaskCommand, "task_command", self._on_task_command)
        self.create_service(PlayActionGroup, "play_action_group", self._on_play_action_group)
        self.create_service(ConfirmTask, "confirm_task", self._on_confirm_task)

        # 发布
        self._event_pub = self.create_publisher(TaskEvent, "task_event", 10)
        self._status_pub = self.create_publisher(ControlStatus, "control_status", 10)

        self._publish_status()
        self.get_logger().info("控制服务就绪, 初始状态 idle（等待 task_command start 与自检）")

    # ------------------------------------------------------------------ 状态
    def _publish_status(self):
        msg = ControlStatus()
        with self._lock:
            msg.state = self._state
            msg.busy = self._busy
        msg.mode = self.driver.mode
        self._status_pub.publish(msg)

    def _set_fault(self, reason):
        with self._lock:
            self._state = "fault"
        self.get_logger().error("进入 fault 状态: %s（需人工复位: 重新下发 start 并自检通过）" % reason)
        self._publish_status()

    # ------------------------------------------------------------------ 事件
    def _now_ms(self):
        return int(time.time() * 1000)

    def _new_event(self, ctx, status, error="", started_ms=None, finished_ms=None):
        ev = TaskEvent()
        ev.event_id = "%s-%s" % (ctx.get("task_id", "none"), uuid.uuid4().hex[:8])
        ev.task_id = ctx.get("task_id", "")
        ev.occurred_at_ms = self._now_ms()
        ev.status = status
        ev.color = ctx.get("color", "")
        ev.x_mm = float(ctx.get("x_mm", 0.0))
        ev.y_mm = float(ctx.get("y_mm", 0.0))
        ev.z_mm = float(ctx.get("z_mm", 0.0))
        ev.has_position = bool(ctx.get("has_position", True))
        ev.started_at_ms = started_ms or 0
        ev.finished_at_ms = finished_ms or 0
        ev.has_times = started_ms is not None and finished_ms is not None
        ev.error_code = error
        ev.mode = ctx.get("mode_override") or self.driver.mode
        # 仅控制器完成动作、未确认实际抓取结果时, 不记为已验证成功
        ev.result_basis = "controller_only" if status == "succeeded" else "none"
        return ev

    def _publish_event(self, ev):
        if ev.status in TERMINAL_STATUS:
            with self._lock:
                self._terminal_events[ev.task_id] = ev
                # 只保留最近 200 条终态事件, 防止长时间运行内存增长
                if len(self._terminal_events) > 200:
                    for key in list(self._terminal_events)[:len(self._terminal_events) - 200]:
                        self._terminal_events.pop(key, None)
        self._event_pub.publish(ev)
        self.get_logger().info("task_event: task=%s status=%s error=%s mode=%s" %
                               (ev.task_id, ev.status, ev.error_code or "-", ev.mode))

    # ------------------------------------------------------------------ 服务: task_command
    def _self_check(self):
        """开机自检（5.6）: 读舵机位置 -> RGB 循环红绿蓝 -> 蜂鸣器短响; 任一异常返回 False。"""
        self.get_logger().info("执行开机自检 ...")
        try:
            joints = self.driver.read_joints()
            if len(joints) != 6:
                raise DriverError("舵机读数数量异常: %s" % joints)
            for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255)):
                self.driver.set_rgb(*color)
                time.sleep(0.2)
            self.driver.set_rgb(0, 0, 0)
            self.driver.buzzer(True)
            time.sleep(0.2)
            self.driver.buzzer(False)
            self.get_logger().info("自检通过, 舵机位置: %s" % joints)
            return True
        except Exception as exc:
            self.get_logger().error("自检失败: %s" % exc)
            return False

    def _on_task_command(self, request, response):
        with self._lock:
            if request.action == "start":
                if self._state == "running":
                    response.accepted = True
                    response.state = "running"
                    response.error_code = ""
                elif self._state == "stopping":
                    response.accepted = False
                    response.state = "stopping"
                    response.error_code = "STOPPING"
                else:  # idle 或 fault(人工复位): 自检通过后进入 running
                    if self._busy:
                        response.accepted = False
                        response.state = self._state
                        response.error_code = "BUSY"
                    else:
                        ok = self._self_check()
                        self._state = "running" if ok else "fault"
                        response.accepted = ok
                        response.state = self._state
                        response.error_code = "" if ok else "SELF_CHECK_FAILED"
                        ctx = {"task_id": "self-check-%d" % self._now_ms(), "color": "",
                               "has_position": False}
                        self._publish_event(self._new_event(
                            ctx, "succeeded" if ok else "failed", "" if ok else "SELF_CHECK_FAILED"))
                self._publish_status()
                return response
            if request.action == "stop":
                if self._busy:
                    # 停止派发新动作; 运动线程在两步之间检查停止标志(<=1s)
                    self._stop_event.set()
                    self._state = "stopping"
                else:
                    self._state = "idle"
                response.accepted = True
                response.state = self._state
                response.error_code = ""
                self._publish_status()
                return response
            response.accepted = False
            response.state = self._state
            response.error_code = "BAD_ACTION"
            return response

    # ------------------------------------------------------------------ 服务: pick_place
    def _validate_pick_place(self, request):
        ws = self.workspace
        if not (ws["x_min_mm"] <= request.x_mm <= ws["x_max_mm"] and
                ws["y_min_mm"] <= request.y_mm <= ws["y_max_mm"] and
                ws["z_min_mm"] <= request.z_mm <= ws["z_max_mm"]):
            return "OUT_OF_WORKSPACE"
        if request.color not in COLORS:
            return "BAD_COLOR"
        if request.bin_id not in self.config["bins"]:
            return "BAD_BIN"
        if self.calibration is None:
            return "NOT_CALIBRATED"
        if request.calibration_id != self.calibration.calibration_id:
            return "CALIBRATION_MISMATCH"
        return ""

    def _on_pick_place(self, request, response):
        with self._lock:
            response.status = self._state
            if self._state == "fault":
                response.error_code = "FAULT"
                return response
            if self._state != "running":
                response.error_code = "NOT_RUNNING"
                return response
            if self._busy:
                response.error_code = "BUSY"
                return response
            if request.task_id in self._executed_task_ids:
                response.error_code = "DUPLICATE_TASK"
                return response
            error = self._validate_pick_place(request)
            if error:
                response.error_code = error
                return response
            self._busy = True
            self._executed_task_ids.add(request.task_id)
            self._stop_event.clear()  # 任务接受时清除历史停止标志(停止请求此后到达才会中止本任务)

        ctx = {
            "task_id": request.task_id,
            "frame_id": request.frame_id,
            "detection_id": request.detection_id,
            "color": request.color,
            "x_mm": request.x_mm,
            "y_mm": request.y_mm,
            "z_mm": request.z_mm,
            "bin_id": request.bin_id,
            "calibration_id": request.calibration_id,
            "has_position": True,
            "mode_override": request.mode or None,  # fallback=HSV 兜底定位(9.2)
        }
        queued = self._new_event(ctx, "queued")
        self._publish_event(queued)
        self._publish_status()
        response.accepted = True
        response.status = "queued"
        response.error_code = ""
        response.event_id = queued.event_id
        # 串行执行: 运动任务在后台线程执行, 服务回调立即返回（接受仅代表已入队）
        threading.Thread(target=self._execute_task, args=(ctx,), daemon=True).start()
        return response

    # ------------------------------------------------------------------ 运动执行
    def _check_abort(self, started_ms):
        if self._stop_event.is_set():
            raise ControlError("STOP_REQUESTED", "收到停止请求")
        if self._now_ms() - started_ms > self.control["move_timeout_ms"]:
            raise ControlError("CONTROL_TIMEOUT", "运动超过 %d ms 未完成" % self.control["move_timeout_ms"])

    def _ik(self, x_mm, y_mm, z_mm):
        """调用任务2反解服务, 返回 5 个关节舵机角度(90=URDF 零位)。"""
        timeout = self.control["ik_timeout_ms"] / 1000.0
        if not self._ik_client.wait_for_service(timeout_sec=timeout):
            raise ControlError("IK_SOLVE_FAILED", "反解服务 trial_service 不可用")
        req = Kinemarics.Request()
        req.tar_x = x_mm / 1000.0
        req.tar_y = y_mm / 1000.0
        req.tar_z = z_mm / 1000.0
        req.roll = 0.0
        req.pitch = 0.0
        req.yaw = 0.0
        req.kin_name = self.control["ik_mode"]  # ik_top: 顶部垂直抓取
        future = self._ik_client.call_async(req)
        deadline = time.time() + timeout
        while not future.done() and time.time() < deadline:
            time.sleep(0.02)
        if not future.done():
            raise ControlError("IK_SOLVE_FAILED", "反解服务调用超时")
        resp = future.result()
        joints = [resp.joint1, resp.joint2, resp.joint3, resp.joint4, resp.joint5]
        if any(math.isnan(j) for j in joints):
            raise ControlError("IK_SOLVE_FAILED", "反解失败(位置不可达): %.1f %.1f %.1f" % (x_mm, y_mm, z_mm))
        return joints

    def _move_to(self, x_mm, y_mm, z_mm):
        joints = self._ik(x_mm, y_mm, z_mm)
        angles = [int(round(j)) for j in joints] + [self._gripper_deg]
        self.get_logger().info("运动到 (%.0f, %.0f, %.0f) mm, 舵机: %s" % (x_mm, y_mm, z_mm, angles))
        self.driver.move_joints(angles, self.control["step_time_ms"])

    def _set_gripper(self, opened):
        self._gripper_deg = (self.config["robot"]["gripper_open_deg"] if opened
                             else self.config["robot"]["gripper_close_deg"])
        joints = list(self.driver.read_joints()[:5]) + [self._gripper_deg]
        self.get_logger().info("夹爪 -> %s (%d deg)" % ("张开" if opened else "闭合", self._gripper_deg))
        self.driver.move_joints(joints, 500)

    def _home(self):
        joints = list(self.config["robot"]["home_joints"]) + [self._gripper_deg]
        self.get_logger().info("回待机位 %s" % joints)
        self.driver.move_joints(joints, self.control["step_time_ms"])

    def _run_pick_place_step(self, started_ms, x, y, z, place_x, place_y, place_z):
        """一次完整的 抓取->搬运->释放 动作序列（3.1 步骤④）。"""
        z_lift = self.workspace["z_lift_mm"]
        self._check_abort(started_ms)
        self._set_gripper(True)                                    # 张开夹爪
        self._check_abort(started_ms)
        self._move_to(x, y, z_lift)                                # 预抓取位(目标正上方)
        self._check_abort(started_ms)
        self._move_to(x, y, z)                                     # 下降到抓取高度
        self._check_abort(started_ms)
        self._set_gripper(False)                                   # 闭合夹爪
        self._check_abort(started_ms)
        self._move_to(x, y, z_lift)                                # 抬升
        self._check_abort(started_ms)
        self._move_to(place_x, place_y, z_lift)                    # 移动到放置点正上方
        self._check_abort(started_ms)
        self._move_to(place_x, place_y, place_z)                   # 下降到释放高度
        self._check_abort(started_ms)
        self._set_gripper(True)                                    # 张开夹爪释放
        self._check_abort(started_ms)
        self._move_to(place_x, place_y, z_lift)                    # 抬升
        self._check_abort(started_ms)
        self._home()                                               # 回待机位

    def _execute_task(self, ctx):
        started_ms = self._now_ms()
        self._publish_event(self._new_event(ctx, "running", started_ms=started_ms))
        status, error = "succeeded", ""
        try:
            bincfg = self.config["bins"][ctx["bin_id"]]
            self._run_pick_place_step(
                started_ms,
                ctx["x_mm"], ctx["y_mm"], ctx["z_mm"],
                bincfg["x_mm"], bincfg["y_mm"], bincfg["z_release_mm"])
        except ControlError as exc:
            status = "stopped" if exc.code == "STOP_REQUESTED" else "failed"
            error = exc.code
            self.get_logger().warn("任务 %s 中止: %s" % (ctx["task_id"], exc))
            if exc.code == "CONTROL_TIMEOUT":
                self._set_fault("CONTROL_TIMEOUT: 运动超时(>%d ms), 需人工复位" % self.control["move_timeout_ms"])
        except DriverError as exc:
            status, error = "failed", "DRIVER_ERROR"
            self.get_logger().error("任务 %s 驱动错误: %s" % (ctx["task_id"], exc))
            self._set_fault("DRIVER_ERROR: %s" % exc)
        finally:
            finished_ms = self._now_ms()
            with self._lock:
                self._busy = False
                if self._state == "stopping":
                    self._state = "idle"
            self._publish_event(self._new_event(ctx, status, error, started_ms, finished_ms))
            self._publish_status()

    # ------------------------------------------------------------------ 动作组(5.4)
    def _on_play_action_group(self, request, response):
        with self._lock:
            response.state = self._state
            if self._state == "fault":
                response.error_code = "FAULT"
                return response
            if self._busy:
                response.error_code = "BUSY"
                return response
            group = self.config["action_groups"].get(request.group_name)
            if group is None:
                response.error_code = "UNKNOWN_GROUP"
                return response
            self._busy = True
            self._stop_event.clear()  # 同上: 任务接受时清除历史停止标志
        repeat = request.repeat if request.repeat > 0 else int(group.get("repeat", 1))
        ctx = {"task_id": "group-%s-%s" % (request.group_name, uuid.uuid4().hex[:8]),
               "color": "", "has_position": False, "action_group": request.group_name}
        queued = self._new_event(ctx, "queued")
        self._publish_event(queued)
        self._publish_status()
        response.accepted = True
        response.status = "queued"
        response.error_code = ""
        threading.Thread(target=self._execute_group, args=(ctx, request.group_name, repeat), daemon=True).start()
        return response

    def _execute_group(self, ctx, group_name, repeat):
        group = self.config["action_groups"][group_name]
        started_ms = self._now_ms()
        self._publish_event(self._new_event(ctx, "running", started_ms=started_ms))
        status, error = "succeeded", ""
        try:
            for _ in range(repeat):
                if group.get("type", "keyframes") == "keyframes":
                    for frame in group.get("frames", []):
                        self._check_abort(started_ms)
                        joints = [int(j) for j in frame["joints"]]
                        self.get_logger().info("动作组[%s] 舵机: %s" % (group_name, joints))
                        self.driver.move_joints(joints, int(frame.get("time_ms", 500)))
                else:  # pick_place 序列: 大自然搬运工 / 叠罗汉
                    for step in group.get("steps", []):
                        pick = step["pick"]
                        place = step["place"]
                        if "bin_id" in place:
                            bincfg = self.config["bins"][place["bin_id"]]
                            place_xyz = (bincfg["x_mm"], bincfg["y_mm"], bincfg["z_release_mm"])
                        else:
                            place_xyz = (place["x_mm"], place["y_mm"], place["z_mm"])
                        self._run_pick_place_step(
                            started_ms, pick["x_mm"], pick["y_mm"], pick["z_mm"], *place_xyz)
        except ControlError as exc:
            status = "stopped" if exc.code == "STOP_REQUESTED" else "failed"
            error = exc.code
            if exc.code == "CONTROL_TIMEOUT":
                self._set_fault("CONTROL_TIMEOUT")
        except DriverError as exc:
            status, error = "failed", "DRIVER_ERROR"
            self._set_fault("DRIVER_ERROR: %s" % exc)
        finally:
            finished_ms = self._now_ms()
            with self._lock:
                self._busy = False
                if self._state == "stopping":
                    self._state = "idle"
            self._publish_event(self._new_event(ctx, status, error, started_ms, finished_ms))
            self._publish_status()

    # ------------------------------------------------------------------ 服务: confirm_task
    def _on_confirm_task(self, request, response):
        with self._lock:
            terminal = self._terminal_events.get(request.task_id)
        if terminal is None:
            response.accepted = False
            response.error_code = "UNKNOWN_TASK"
            return response
        if terminal.status != "succeeded":
            response.accepted = False
            response.error_code = "NOT_SUCCEEDED"
            return response
        if terminal.result_basis == "operator_confirmed":
            response.accepted = False
            response.error_code = "ALREADY_CONFIRMED"
            return response
        # 补发一条 result_basis=operator_confirmed 的事件（event_id 不同, 看板按 event_id 幂等入库）
        confirmed = TaskEvent()
        confirmed.event_id = "%s-confirmed-%s" % (request.task_id, uuid.uuid4().hex[:8])
        confirmed.task_id = request.task_id
        confirmed.occurred_at_ms = self._now_ms()
        confirmed.status = terminal.status
        confirmed.color = terminal.color
        confirmed.x_mm = terminal.x_mm
        confirmed.y_mm = terminal.y_mm
        confirmed.z_mm = terminal.z_mm
        confirmed.has_position = terminal.has_position
        confirmed.started_at_ms = terminal.started_at_ms
        confirmed.finished_at_ms = terminal.finished_at_ms
        confirmed.has_times = terminal.has_times
        confirmed.error_code = terminal.error_code
        confirmed.mode = terminal.mode
        confirmed.result_basis = "operator_confirmed"
        self._event_pub.publish(confirmed)
        with self._lock:
            self._terminal_events[request.task_id] = confirmed  # 防止重复确认
        self.get_logger().info("任务 %s 已被操作人确认(operator_confirmed)" % request.task_id)
        response.accepted = True
        response.error_code = ""
        return response


def main(args=None):
    rclpy.init(args=args)
    node = ControlServer()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
