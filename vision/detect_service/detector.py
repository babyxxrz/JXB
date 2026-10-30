# -*- coding: utf-8 -*-
"""
detector.py — 检测服务核心(PRD §四 detect 接口 / TDD §4.4)

对外契约输出:
{
  "frame_id": str,            # 帧唯一标识 f-<采集时间ms>-<自增序号>
  "captured_at_ms": int,      # Unix 时间戳 ms(与朱玉贺统一时钟源,T12)
  "image_width_px": int,
  "image_height_px": int,
  "detections": [             # 无目标返回空数组(PRD §四硬性约定)
    {
      "detection_id": str,    # d-<frame_id>-<序号>
      "color": "red|yellow|blue|green",
      "confidence": float,    # 0~1
      "center_u_px": float,   # 中心坐标: 图像原点左上角,u 向右,v 向下
      "center_v_px": float
    }
  ]
}

其他硬性约定(均已实现):
  - 默认置信度阈值 0.5(config.json 可调)
  - 帧超过 1s 未用于生成任务必须重采 → fresh_result() 返回 None
  - 任务完成后禁止复用旧帧连续抓取 → 调用 invalidate_cache()
"""

import json
import time

import numpy as np

from processing import decode, map_to_original, nms, preprocess


class Detector:
    def __init__(self, engine, config: dict):
        """
        engine: 具备 infer([np.ndarray]) -> list[np.ndarray] 的对象。
                板子上传 AclEngine;开发机单测传 FakeEngine(见 tests/)。
        config: config.load_config() 返回的 dict。
        """
        self.engine = engine
        self.cfg = config
        self.classes = config["model"]["classes"]
        self.conf_thresh = config["detect"]["conf_threshold"]
        self.iou_thresh = config["detect"]["iou_threshold"]
        self.max_age_ms = config["detect"]["frame_max_age_ms"]
        self._seq = 0
        self._cached = None        # 最近一次的契约 dict
        self._cached_at_ms = None  # 该结果对应帧的采集时间

    # -----------------------------------------------------------
    # 主入口: 输入一帧 BGR 图像,输出契约 dict
    # -----------------------------------------------------------
    def detect(self, img_bgr, captured_at_ms: int = None) -> dict:
        h, w = img_bgr.shape[:2]
        if captured_at_ms is None:
            captured_at_ms = self._now_ms()
        input_size = (self.cfg["model"]["input_width"],
                      self.cfg["model"]["input_height"])
        blob, scale, (dw, dh) = preprocess(img_bgr, input_size)

        outputs = self.engine.infer([blob])
        dets = decode(
            outputs, len(self.classes), self.conf_thresh,
            model_format=self.cfg["model"]["format"],
            apply_sigmoid=self.cfg["detect"].get("apply_sigmoid", True),
        )
        if len(dets) > 0:
            dets = dets[nms(dets, self.iou_thresh)]

        result = self._build_result(dets, scale, dw, dh, w, h, captured_at_ms)
        self._cache(result, captured_at_ms)
        return result

    # -----------------------------------------------------------
    # 帧新鲜度管理(PRD §四)
    # -----------------------------------------------------------
    def fresh_result(self, max_age_ms: int = None):
        """返回缓存的检测结果;若缓存帧超过 max_age_ms(默认配置 1s)
        则返回 None —— 调用方必须重新采集图像并调用 detect()。"""
        max_age_ms = max_age_ms if max_age_ms is not None else self.max_age_ms
        if self._cached is None or self._cached_at_ms is None:
            return None
        if self._now_ms() - self._cached_at_ms > max_age_ms:
            return None
        return self._cached

    def invalidate_cache(self):
        """任务完成后调用:强制下一轮重新检测,禁止复用旧帧连续抓取。"""
        self._cached = None
        self._cached_at_ms = None

    def result_json(self, result: dict = None) -> str:
        """契约 dict → JSON 字符串(交给朱玉贺/严晨越的传输格式示例)。"""
        result = result if result is not None else self._cached
        return json.dumps(result, ensure_ascii=False)

    # -----------------------------------------------------------
    # 内部实现
    # -----------------------------------------------------------
    def _build_result(self, dets, scale, dw, dh, img_w, img_h, captured_at_ms):
        frame_id = self._frame_id(captured_at_ms)
        detections = []
        for i, d in enumerate(dets):
            x1, y1, x2, y2, conf, cls_id = d[:6]
            ox1, oy1, ox2, oy2 = map_to_original(
                np.array([x1, y1, x2, y2]), scale, dw, dh, img_w, img_h)
            detections.append({
                "detection_id": f"d-{frame_id}-{i}",
                "color": self.classes[int(cls_id)],
                "confidence": round(float(conf), 4),
                "center_u_px": round(float((ox1 + ox2) / 2.0), 2),
                "center_v_px": round(float((oy1 + oy2) / 2.0), 2),
            })
        return {
            "frame_id": frame_id,
            "captured_at_ms": captured_at_ms,
            "image_width_px": int(img_w),
            "image_height_px": int(img_h),
            "detections": detections,
        }

    def _cache(self, result, captured_at_ms):
        self._cached = result
        self._cached_at_ms = captured_at_ms

    def _frame_id(self, captured_at_ms):
        self._seq += 1
        return f"f-{captured_at_ms}-{self._seq:06d}"

    @staticmethod
    def _now_ms():
        return int(time.time() * 1000)
