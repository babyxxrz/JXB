# -*- coding: utf-8 -*-
"""手眼标定: 图像坐标(px) -> 机械臂基坐标系平面坐标(mm) 的转换（技术设计文档 5.1）。

- 图像原点左上角, u 向右、v 向下; 机器人坐标原点与轴方向以实机 SDK/URDF 定义为准,
  由标定图（docs/标定与坐标说明.md）明确。
- 禁止直接将像素值当作毫米值, 必须经过本模块的标定变换。
- 标定数据由 scripts 入口 hand_eye_calibrate 生成, validate_calibration 验收（9 点误差 <= 10mm）。
"""
import os
import time

import yaml


class CalibrationError(Exception):
    pass


class PlaneCalibration:
    """平面单应变换: [x_mm, y_mm, 1]^T ~ H * [u, v, 1]^T"""

    def __init__(self, calibration_id, h, created_at_ms=None, num_points=0, max_residual_mm=None):
        self.calibration_id = calibration_id
        self.h = h  # 3x3
        self.created_at_ms = created_at_ms or int(time.time() * 1000)
        self.num_points = num_points
        self.max_residual_mm = max_residual_mm
        self.valid = bool(h) and any(abs(v) > 1e-9 for row in h for v in row)

    def to_mm(self, u_px, v_px):
        if not self.valid:
            raise CalibrationError("标定无效(未标定或全零矩阵), 请先运行 hand_eye_calibrate")
        w = self.h[2][0] * u_px + self.h[2][1] * v_px + self.h[2][2]
        if abs(w) < 1e-9:
            raise CalibrationError("标定变换退化")
        x = (self.h[0][0] * u_px + self.h[0][1] * v_px + self.h[0][2]) / w
        y = (self.h[1][0] * u_px + self.h[1][1] * v_px + self.h[1][2]) / w
        return x, y


def load_calibration(path):
    if not path or not os.path.isfile(path):
        raise CalibrationError("标定文件不存在: %s（请运行 hand_eye_calibrate 完成手眼标定）" % path)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    try:
        return PlaneCalibration(
            calibration_id=data.get("calibration_id", "unknown"),
            h=data["h"],
            created_at_ms=data.get("created_at_ms"),
            num_points=data.get("num_points", 0),
            max_residual_mm=data.get("max_residual_mm"),
        )
    except (KeyError, TypeError):
        raise CalibrationError("标定文件格式错误: %s" % path)
