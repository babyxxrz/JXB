# -*- coding: utf-8 -*-
"""机械臂驱动层: 统一舵机/灯/蜂鸣器接口, 支持实机(Arm_Lib)与仿真两种驱动。

- ArmLibDriver: 实机模式, 调用板卡上的 Arm_Lib(Python) 驱动舵机。
  【注意】Arm_Lib 接口名以实机 SDK 为准, 全部集中在 ArmLibDriver 一个类中,
  若板卡 API 名称不同只需修改此处。
- SimArmDriver: 仿真/降级演示模式, 只打印日志并按配置时长等待, 用于联调与 F2 降级路径。
"""
import time

try:
    from Arm_Lib import Arm_Device  # 板卡课程 SDK
    HAS_ARM_LIB = True
except Exception:
    HAS_ARM_LIB = False


class DriverError(Exception):
    pass


class ArmDriver:
    """驱动接口。angles 均为 6 个舵机角度(0-180), 其中第 6 个为夹爪。"""

    mode = "simulation"  # real / simulation

    def connect(self):
        raise NotImplementedError

    def move_joints(self, angles, time_ms):
        raise NotImplementedError

    def read_joints(self):
        raise NotImplementedError

    def set_rgb(self, r, g, b):
        raise NotImplementedError

    def buzzer(self, on):
        raise NotImplementedError


class SimArmDriver(ArmDriver):
    mode = "simulation"

    def __init__(self, logger=None, step_pause_ms=0):
        self._logger = logger
        self._joints = [90, 90, 90, 90, 90, 90]
        self._step_pause_ms = step_pause_ms

    def _log(self, msg):
        if self._logger:
            self._logger.info("[SIM] " + msg)
        else:
            print("[SIM] " + msg)

    def connect(self):
        self._log("仿真驱动连接成功（不控制真实舵机）")

    def move_joints(self, angles, time_ms):
        self._joints = list(angles)
        self._log("移动到 %s (耗时 %d ms)" % (angles, time_ms))
        time.sleep(min(time_ms, 2000) / 1000.0)
        if self._step_pause_ms:
            time.sleep(self._step_pause_ms / 1000.0)

    def read_joints(self):
        return list(self._joints)

    def set_rgb(self, r, g, b):
        self._log("RGB 灯 -> (%d, %d, %d)" % (r, g, b))

    def buzzer(self, on):
        self._log("蜂鸣器 -> %s" % ("响" if on else "停"))


class ArmLibDriver(ArmDriver):
    """实机驱动: 通过板卡 Arm_Lib 控制舵机。"""

    mode = "real"

    def __init__(self, logger=None):
        self._logger = logger
        self._arm = None

    def _log(self, msg):
        if self._logger:
            self._logger.info("[ARM_LIB] " + msg)
        else:
            print("[ARM_LIB] " + msg)

    def connect(self):
        if not HAS_ARM_LIB:
            raise DriverError("未找到 Arm_Lib, 无法使用实机驱动（请确认板卡 SDK 已安装）")
        self._arm = Arm_Device()
        self._log("Arm_Lib 连接成功")

    def move_joints(self, angles, time_ms):
        if self._arm is None:
            raise DriverError("Arm_Lib 未连接")
        s1, s2, s3, s4, s5, s6 = [max(0, min(180, int(a))) for a in angles]
        self._arm.Arm_serial_servo_write6(s1, s2, s3, s4, s5, s6, int(time_ms))

    def read_joints(self):
        if self._arm is None:
            raise DriverError("Arm_Lib 未连接")
        return [self._arm.Arm_serial_servo_read(i) for i in range(1, 7)]

    def set_rgb(self, r, g, b):
        if self._arm is None:
            raise DriverError("Arm_Lib 未连接")
        self._arm.Arm_RGB_set(int(r), int(g), int(b))

    def buzzer(self, on):
        if self._arm is None:
            raise DriverError("Arm_Lib 未连接")
        if on:
            self._arm.Arm_Buzzer_On()
        else:
            self._arm.Arm_Buzzer_Off()


def create_driver(driver_config, logger=None):
    """按配置创建驱动: mode = auto(默认) / simulation / arm_lib。
    auto 优先尝试 Arm_Lib, 失败时降级仿真并在日志中明确警告（对应 9.2 降级路径）。"""
    mode = driver_config.get("mode", "auto")
    if mode == "simulation":
        return SimArmDriver(logger)
    if mode == "arm_lib":
        driver = ArmLibDriver(logger)
        driver.connect()  # 失败则抛出 DriverError, 不静默降级
        return driver
    # auto
    try:
        driver = ArmLibDriver(logger)
        driver.connect()
        return driver
    except DriverError as exc:
        if logger:
            logger.warning("Arm_Lib 不可用(%s), 降级为仿真模式" % exc)
        return SimArmDriver(logger)
