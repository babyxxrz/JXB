# -*- coding: utf-8 -*-
"""
test_detector_pipeline.py — Detector 全流程单测(开发机上即可运行)

用 FakeEngine 顶替 ACL 推理,验证:
  - detect() 输出的契约字段完整、格式正确(PRD §四 detect 接口)
  - 坐标映射回原图正确
  - 无目标返回空数组
  - 帧新鲜度 fresh_result / invalidate_cache 行为
  - 帧唯一标识 frame_id / detection_id 生成规则

运行: python tests/test_detector_pipeline.py
"""

import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "detect_service"))
from config import load_config  # noqa: E402
from detector import Detector  # noqa: E402


class FakeEngine:
    """顶替 AclEngine: infer 直接返回预设输出。"""

    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = 0

    def infer(self, inputs):
        self.calls += 1
        return self.outputs


def make_v8_output(center=(320, 320), box=(40, 40), cls_id=0, logit=10.0, N=8400):
    """构造一个 v8 格式 (1, 4+4, N) 输出: 一个高置信目标,其余低 logit。"""
    raw = np.full((1, 8, N), -10.0, dtype=np.float32)
    raw[0, 0, 0] = center[0]; raw[0, 1, 0] = center[1]
    raw[0, 2, 0] = box[0];    raw[0, 3, 0] = box[1]
    raw[0, 4 + cls_id, 0] = logit
    return [raw]


def make_detector(outputs):
    cfg = load_config()
    cfg["model"]["format"] = "v8"
    return Detector(FakeEngine(outputs), cfg)


def test_contract_fields_and_mapping():
    # 640x640 图像 -> 无缩放无填充,中心应原样返回 (320, 320)
    img = np.zeros((640, 640, 3), dtype=np.uint8)
    det = make_detector(make_v8_output(center=(320, 320)))
    result = det.detect(img)

    assert set(result.keys()) == {
        "frame_id", "captured_at_ms", "image_width_px", "image_height_px", "detections"}
    assert result["image_width_px"] == 640 and result["image_height_px"] == 640
    assert isinstance(result["captured_at_ms"], int) and result["captured_at_ms"] > 0
    # frame_id 格式: f-<时间戳>-<6位序号>
    import re
    assert re.fullmatch(r"f-\d+-\d{6}", result["frame_id"]), result["frame_id"]

    assert len(result["detections"]) == 1
    d = result["detections"][0]
    assert d["detection_id"] == f"d-{result['frame_id']}-0"
    assert d["color"] == "red"
    assert 0.0 < d["confidence"] <= 1.0
    assert abs(d["center_u_px"] - 320) < 1.0
    assert abs(d["center_v_px"] - 320) < 1.0

    # JSON 可序列化(交给朱玉贺的传输格式)
    s = det.result_json(result)
    assert json.loads(s)["detections"][0]["color"] == "red"


def test_coord_mapping_with_letterbox():
    # 320x240 图像 -> scale=2.0, dh=80;letterbox 中心 (320,320) -> 原图 (160,120)
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    det = make_detector(make_v8_output(center=(320, 320)))
    result = det.detect(img)
    d = result["detections"][0]
    assert abs(d["center_u_px"] - 160) < 1.0, d
    assert abs(d["center_v_px"] - 120) < 1.0, d
    assert result["image_width_px"] == 320 and result["image_height_px"] == 240


def test_no_target_returns_empty_array():
    det = make_detector([np.full((1, 8, 10), -10.0, dtype=np.float32)])
    result = det.detect(np.zeros((640, 640, 3), dtype=np.uint8))
    assert result["detections"] == []          # 空数组,不是 null(PRD §四)


def test_conf_threshold():
    # logit=0 -> sigmoid=0.5 正好卡阈值;logit=-1 -> 0.27 被过滤
    det = make_detector(make_v8_output(logit=0.0))
    assert len(det.detect(np.zeros((640, 640, 3), np.uint8))["detections"]) == 1
    det2 = make_detector(make_v8_output(logit=-1.0))
    assert det2.detect(np.zeros((640, 640, 3), np.uint8))["detections"] == []


def test_freshness_and_invalidate():
    img = np.zeros((640, 640, 3), dtype=np.uint8)
    det = make_detector(make_v8_output())
    det.detect(img)
    # 刚检测过 -> fresh
    assert det.fresh_result() is not None
    # 伪造缓存时间: 2s 前 -> 过期返回 None(PRD §四: 超过 1s 必须重采)
    det._cached_at_ms = det._now_ms() - 2000
    assert det.fresh_result() is None
    # 任务完成后强制失效: 即使时间没过期,也不许复用旧帧
    det.detect(img)
    assert det.fresh_result() is not None
    det.invalidate_cache()
    assert det.fresh_result() is None


def test_frame_id_increments():
    img = np.zeros((640, 640, 3), dtype=np.uint8)
    det = make_detector(make_v8_output())
    r1 = det.detect(img)
    r2 = det.detect(img)
    assert r1["frame_id"] != r2["frame_id"]
    # 相同时间戳下序号也要递增保证唯一
    t = int(time.time() * 1000)
    r3 = det.detect(img, captured_at_ms=t)
    r4 = det.detect(img, captured_at_ms=t)
    assert r3["frame_id"] != r4["frame_id"]
    assert r3["frame_id"].startswith(f"f-{t}-")


def _run_all():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 通过")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
