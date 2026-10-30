# -*- coding: utf-8 -*-
"""
test_color_locator.py — HSV 兜底定位 + 降级链单测(开发机上即可运行)

用合成色块图像验证(TDD §4.5 / PRD §四 降级路径):
  - 四色积木各自被正确识别,质心与真实中心一致
  - 红色跨 hue 0/180 两端(两段阈值 OR 合并)都能检出
  - 输出契约与 detect 完全同格式
  - 灰色背景(无彩色目标)返回空数组
  - fallback_chain: detect 命中 / 补采后命中 / HSV 兜底 / 全部失败 四种路径

运行: python tests/test_color_locator.py
"""

import json
import os
import re
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "hsv_fallback"))
from color_locator import ColorLocator, load_hsv_config  # noqa: E402
from fallback_chain import resolve_target  # noqa: E402

# 与 hsv_config.json 一致的合成色 BGR 值
COLOR_BGR = {
    "red": (0, 0, 255),      # H=0   -> 红色第 1 段
    "red_dark": (30, 0, 255),  # H≈176 -> 红色第 2 段(跨 hue 包络的另一端)
    "yellow": (0, 255, 255),   # H=30
    "green": (0, 255, 0),      # H=60
    "blue": (255, 0, 0),       # H=120
}


def make_locator():
    cfg = load_hsv_config()
    return ColorLocator(cfg)


def draw_block(img, color, x, y, size=40):
    """在灰色背景图上画一个 size x size 的实心色块,返回真实中心。"""
    cv2.rectangle(img, (x, y), (x + size, y + size), COLOR_BGR[color], -1)
    return (x + size / 2.0, y + size / 2.0)


def gray_img(h=240, w=320):
    # 灰色 S=0,不落在任何颜色阈值内,保证无彩色背景
    return np.full((h, w, 3), (60, 60, 60), dtype=np.uint8)


def test_red_hue_wrap_both_segments():
    # 纯红 (H=0, 第1段) 与暗红偏紫 (H≈176, 第2段) 都必须是 "red"
    loc = make_locator()
    for key in ("red", "red_dark"):
        img = gray_img()
        cx, cy = draw_block(img, key, 140, 100)
        result = loc.locate(img)
        assert len(result["detections"]) == 1, (key, result["detections"])
        d = result["detections"][0]
        assert d["color"] == "red", (key, d["color"])
        assert abs(d["center_u_px"] - cx) < 3.0, (key, d)
        assert abs(d["center_v_px"] - cy) < 3.0, (key, d)


def test_four_colors_centroids():
    img = gray_img()
    expected = {
        "red": draw_block(img, "red", 20, 20),
        "yellow": draw_block(img, "yellow", 140, 20),
        "green": draw_block(img, "green", 20, 140),
        "blue": draw_block(img, "blue", 140, 140),
    }
    result = make_locator().locate(img)
    assert len(result["detections"]) == 4, result
    # 每个颜色只出现一次(色块之间不得互相误检)
    colors = [d["color"] for d in result["detections"]]
    assert len(set(colors)) == 4, colors
    for d in result["detections"]:
        cx, cy = expected[d["color"]]
        assert abs(d["center_u_px"] - cx) < 3.0, d
        assert abs(d["center_v_px"] - cy) < 3.0, d


def test_contract_format_same_as_detect():
    # 与 detector.Detector 输出完全同构(PRD §四 detect 契约)
    img = gray_img()
    draw_block(img, "blue", 140, 100)
    result = make_locator().locate(img)
    assert set(result.keys()) == {
        "frame_id", "captured_at_ms", "image_width_px", "image_height_px", "detections"}
    assert result["image_width_px"] == 320 and result["image_height_px"] == 240
    assert isinstance(result["captured_at_ms"], int)
    assert re.fullmatch(r"f-\d+-\d{6}", result["frame_id"]), result["frame_id"]

    d = result["detections"][0]
    assert d["detection_id"] == f"d-{result['frame_id']}-0"
    assert d["color"] in ("red", "yellow", "blue", "green")
    assert 0.0 <= d["confidence"] <= 1.0     # fill_ratio 伪置信度
    # JSON 可序列化(与控制层传输格式一致)
    assert json.loads(json.dumps(result))["frame_id"] == result["frame_id"]


def test_empty_background_returns_empty_array():
    result = make_locator().locate(gray_img())
    assert result["detections"] == []        # 空数组,不是 null


def test_too_small_block_filtered_by_min_area():
    # 10x10=100px² 约等于 min_area_ratio 下限附近的小块,应被 min_area 过滤
    # (min_area = 0.001 * 240 * 320 = 76.8,故用 5x5=25px² 必然被滤掉)
    img = gray_img()
    draw_block(img, "red", 10, 10, size=5)
    assert make_locator().locate(img)["detections"] == []


# ---------------------------------------------------------------
# fallback_chain 降级链(PRD §四 / TDD §3.4:补采2帧 -> HSV -> 跳过)
# ---------------------------------------------------------------
class FakeDetector:
    """按预设结果队列依次返回 detect 结果,并计数。"""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def detect(self, img):
        self.calls += 1
        return self.outputs.pop(0) if self.outputs else {"detections": []}


class FakeLocator:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def locate(self, img):
        self.calls += 1
        return self.result


def hit(color="red"):
    return {"detections": [{"color": color}]}


def miss():
    return {"detections": []}


def make_capture():
    state = {"n": 0}

    def capture_fn():
        state["n"] += 1
        return np.zeros((10, 10, 3), np.uint8)
    return capture_fn, state


def test_chain_hit_immediately():
    cap, st = make_capture()
    det = FakeDetector([hit()])
    loc = FakeLocator(hit())
    result, mode = resolve_target(det, loc, cap, retry_delay_ms=0)
    assert mode == "real" and result["detections"][0]["color"] == "red"
    assert det.calls == 1 and loc.calls == 0 and st["n"] == 1


def test_chain_hit_after_retries():
    # 前 2 次空 -> 第 3 次(1 初始 + 2 补采)命中,不进入 HSV
    cap, st = make_capture()
    det = FakeDetector([miss(), miss(), hit()])
    loc = FakeLocator(hit())
    result, mode = resolve_target(det, loc, cap, retry_delay_ms=0)
    assert mode == "real"
    assert det.calls == 3 and loc.calls == 0 and st["n"] == 3


def test_chain_fallback_to_hsv():
    # 3 次检测全空 -> HSV 兜底命中,标记 fallback
    cap, st = make_capture()
    det = FakeDetector([miss(), miss(), miss()])
    loc = FakeLocator(hit())
    result, mode = resolve_target(det, loc, cap, retry_delay_ms=0)
    assert mode == "fallback" and result["detections"][0]["color"] == "red"
    assert det.calls == 3 and loc.calls == 1 and st["n"] == 4


def test_chain_all_fail_skip():
    # 检测 + HSV 全部失败 -> (None, None),调用方跳过本轮(LOW_CONFIDENCE)
    cap, st = make_capture()
    det = FakeDetector([miss(), miss(), miss()])
    loc = FakeLocator(miss())
    result, mode = resolve_target(det, loc, cap, retry_delay_ms=0)
    assert result is None and mode is None
    assert det.calls == 3 and loc.calls == 1 and st["n"] == 4


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
