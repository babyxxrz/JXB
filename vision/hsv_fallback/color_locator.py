# -*- coding: utf-8 -*-
"""
color_locator.py — HSV 颜色分割兜底定位(PRD §四 / TDD §4.5)

与深度学习检测并行: 低置信度时由 fallback_chain.py 调用本模块,
独立输出目标颜色与中心坐标。输出契约与 detector.Detector 完全一致,
控制层(朱玉贺)按 mode=fallback 记入 task_event。

注意:
  - HSV 阈值必须在实机光照下用 hsv_tuner.py 标定(光照一变阈值就变,
    需与朱玉贺一起在实机环境做,TDD §4.5)
  - 兜底结果不计入检测模型 mAP
  - confidence 字段用"轮廓面积 / 包围盒面积"作伪置信度(0~1),
    仅为保持契约格式统一,不代表模型置信度
  - 红色 hue 跨 0/180 两端,配置里给两段阈值,本模块做 OR 合并
"""

import json
import os
import time

import cv2
import numpy as np


def load_hsv_config(path: str = None) -> dict:
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "hsv_config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class ColorLocator:
    def __init__(self, config: dict):
        self.colors = config["colors"]          # {color: [[lo,up], ...]}
        self.min_area_ratio = config.get("min_area_ratio", 0.001)
        self.open_kernel = config.get("open_kernel", 5)
        self.close_kernel = config.get("close_kernel", 7)
        self._seq = 0

    # -----------------------------------------------------------
    # 主入口: 输入一帧 BGR 图像,输出契约 dict(与 detect 同格式)
    # -----------------------------------------------------------
    def locate(self, img_bgr, captured_at_ms: int = None) -> dict:
        h, w = img_bgr.shape[:2]
        if captured_at_ms is None:
            captured_at_ms = int(time.time() * 1000)
        img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        min_area = self.min_area_ratio * h * w
        kernel_o = np.ones((self.open_kernel, self.open_kernel), np.uint8)
        kernel_c = np.ones((self.close_kernel, self.close_kernel), np.uint8)

        candidates = []   # (area, color, info)
        for color in self.colors:
            mask = self._mask_for(img_hsv, color)
            if mask is None or cv2.countNonZero(mask) == 0:
                continue
            # 形态学去噪: 开运算去小噪点,闭运算填小空洞
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_o)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_c)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            best = None
            for c in contours:
                area = cv2.contourArea(c)
                if area < min_area or area <= 0:
                    continue
                if best is not None and area <= best["area"]:
                    continue
                m = cv2.moments(c)
                bx, by, bw, bh = cv2.boundingRect(c)
                best = {
                    "area": area,
                    "center_u": m["m10"] / m["m00"],
                    "center_v": m["m01"] / m["m00"],
                    "fill_ratio": area / max(bw * bh, 1.0),
                }
            if best is not None:
                candidates.append((best["area"], color, best))

        # 面积降序(单目标分拣时控制层取第一个即可)
        candidates.sort(key=lambda t: -t[0])
        frame_id = self._frame_id(captured_at_ms)
        detections = []
        for i, (_, color, b) in enumerate(candidates):
            detections.append({
                "detection_id": f"d-{frame_id}-{i}",
                "color": color,
                "confidence": round(float(min(b["fill_ratio"], 1.0)), 4),
                "center_u_px": round(float(b["center_u"]), 2),
                "center_v_px": round(float(b["center_v"]), 2),
            })
        return {
            "frame_id": frame_id,
            "captured_at_ms": captured_at_ms,
            "image_width_px": int(w),
            "image_height_px": int(h),
            "detections": detections,
        }

    # -----------------------------------------------------------
    # 内部实现
    # -----------------------------------------------------------
    def _mask_for(self, img_hsv, color):
        """多段阈值(红色跨 hue 0/180 两段)OR 合并。"""
        mask = None
        for lo, up in self.colors[color]:
            m = cv2.inRange(img_hsv, np.array(lo, np.uint8),
                            np.array(up, np.uint8))
            mask = m if mask is None else cv2.bitwise_or(mask, m)
        return mask

    def _frame_id(self, captured_at_ms):
        self._seq += 1
        return f"f-{captured_at_ms}-{self._seq:06d}"
