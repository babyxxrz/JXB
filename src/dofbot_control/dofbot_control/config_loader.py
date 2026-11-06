# -*- coding: utf-8 -*-
"""配置加载: 读取 dofbot_config.yaml, 处理相对路径与缺省值。

配置项说明见技术设计文档 8.2（工作区边界/容器位置/置信度阈值等均在此维护,
由看板参数配置页展示, 运动中禁止修改运动相关参数）。
"""
import os

import yaml

DEFAULT_CONFIG = {
    "driver": {"mode": "auto", "port": "/dev/ttyUSB0", "baud": 9600},
    "robot": {"home_joints": [90, 90, 90, 90, 90], "gripper_open_deg": 140, "gripper_close_deg": 60},
    "workspace": {
        "x_min_mm": -100.0, "x_max_mm": 100.0,
        "y_min_mm": -80.0, "y_max_mm": 80.0,
        "z_min_mm": 30.0, "z_max_mm": 180.0,
        "z_grasp_mm": 60.0, "z_lift_mm": 120.0,
    },
    "bins": {},
    "detect": {
        "confidence_threshold": 0.5,
        "max_frame_age_ms": 1000,
        "retry_frames_on_low_confidence": 2,
    },
    "control": {
        "move_timeout_ms": 20000,
        "step_pause_ms": 200,
        "step_time_ms": 800,
        "ik_timeout_ms": 5000,
        "ik_mode": "ik_top",
    },
    "action_groups": {},
    "gesture_color_map": {},  # 待定项 T3: fist/like/ok/palm -> red/yellow/blue/green
}


class ConfigError(Exception):
    pass


def _merge(defaults, loaded):
    """把已加载配置合并到缺省配置上（仅一层深度合并, 子字典整体覆盖）。"""
    merged = dict(defaults)
    for key, value in (loaded or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path):
    """加载 YAML 配置并返回 dict。相对路径（如标定文件）相对于配置所在目录解析。"""
    if not os.path.isfile(path):
        raise ConfigError("配置文件不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    config = _merge(DEFAULT_CONFIG, raw)
    config["_config_dir"] = os.path.dirname(os.path.abspath(path))
    config["_config_file"] = os.path.abspath(path)

    # 标定文件路径: 相对路径按配置文件所在目录解析
    calib = config.get("calibration") or {}
    calib_path = calib.get("file", "")
    if calib_path and not os.path.isabs(calib_path):
        calib["file"] = os.path.join(config["_config_dir"], calib_path)
    config["calibration"] = calib

    # 校验工作区尺寸（需求: 有效工作区至少 120mm x 120mm）
    ws = config["workspace"]
    if (ws["x_max_mm"] - ws["x_min_mm"]) < 120.0 or (ws["y_max_mm"] - ws["y_min_mm"]) < 120.0:
        raise ConfigError("工作区不足 120x120mm: %s" % ws)
    # 校验四个容器齐备
    for color in ("red", "yellow", "blue", "green"):
        if color not in config["bins"]:
            raise ConfigError("缺少容器配置 bins.%s" % color)
    return config
