# -*- coding: utf-8 -*-
"""
test_processing.py — 预处理/后处理单元测试(开发机上即可运行)

运行: python tests/test_processing.py
"""

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "detect_service"))
from processing import (  # noqa: E402
    decode_v5, decode_v8, letterbox, map_to_original, nms, preprocess, sigmoid)


def test_letterbox_no_resize():
    img = np.zeros((640, 640, 3), dtype=np.uint8)
    out, scale, (dw, dh) = letterbox(img, (640, 640))
    assert out.shape == (640, 640, 3)
    assert scale == 1.0 and dw == 0.0 and dh == 0.0


def test_letterbox_with_pad_and_mapback():
    img = np.zeros((240, 320, 3), dtype=np.uint8)   # 宽320 高240 -> 1:1
    out, scale, (dw, dh) = letterbox(img, (640, 640))
    assert out.shape == (640, 640, 3), out.shape
    assert abs(scale - 2.0) < 1e-6, scale
    assert abs(dw - 0.0) < 1e-6 and abs(dh - 80.0) < 1e-6, (dw, dh)

    # letterbox 中心点 (320, 320) 应映射回原图中心 (160, 120)
    mapped = map_to_original(np.array([300, 300, 340, 340]), scale, dw, dh, 320, 240)
    np.testing.assert_allclose(mapped, [150, 110, 170, 130], atol=0.5)


def test_preprocess_blob():
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    blob, scale, _ = preprocess(img, (640, 640))
    assert blob.dtype == np.float32
    assert blob.shape == (1, 3, 640, 640), blob.shape
    assert abs(blob.max() - 128 / 255.0) < 1e-4


def test_sigmoid_stability():
    x = np.array([-1000.0, 0.0, 1000.0], dtype=np.float32)
    y = sigmoid(x)
    assert y[0] == 0.0 and y[1] == 0.5 and y[2] == 1.0


def test_decode_v8():
    # 构造 (1, 4+4, N): 第 0 号锚点 = 中心 (320,320)、40x40、类别 0 高置信
    # 第 1 号锚点 = 类别 1 低置信(应被阈值过滤)
    N = 8400
    raw = np.full((1, 8, N), -10.0, dtype=np.float32)   # 低 logit -> sigmoid≈0
    raw[0, 0, 0] = 320; raw[0, 1, 0] = 320               # cx, cy
    raw[0, 2, 0] = 40;  raw[0, 3, 0] = 40                # w, h
    raw[0, 4, 0] = 10.0                                  # cls0 logit 高
    raw[0, 4, 1] = 2.0                                   # cls0 logit 中(sig≈0.88 > 0.5)

    dets = decode_v8(raw, nc=4, conf_thresh=0.5)
    assert dets.shape == (2, 6)
    # 按置信度降序
    assert dets[0][4] > dets[1][4]
    np.testing.assert_allclose(dets[0][:4], [300, 300, 340, 340], atol=1e-3)
    assert dets[0][5] == 0

    # 阈值 0.9 -> 只剩高置信目标
    dets2 = decode_v8(raw, nc=4, conf_thresh=0.9)
    assert len(dets2) == 1

    # 全部低 logit -> 空
    dets3 = decode_v8(np.full((1, 8, 10), -10.0, dtype=np.float32), 4, 0.5)
    assert len(dets3) == 0


def test_decode_v5():
    # (1, N, 5+4): obj 与 cls 已含 sigmoid
    raw = np.full((1, 4, 9), 0.0, dtype=np.float32)
    raw[0, 0, :4] = [100, 100, 20, 20]
    raw[0, 0, 4] = 1.0        # obj
    raw[0, 0, 5 + 2] = 0.9    # cls2 高分
    dets = decode_v5(raw, nc=4, conf_thresh=0.5)
    assert len(dets) == 1
    assert dets[0][5] == 2
    assert abs(dets[0][4] - 0.9) < 1e-4   # 1.0 * 0.9

    # obj * cls < 阈值 -> 空
    raw2 = raw.copy()
    raw2[0, 0, 4] = 0.4
    assert len(decode_v5(raw2, 4, 0.5)) == 0


def test_nms_class_aware():
    # 两个几乎重合的框: 同类别 -> 只留一个; 不同类别 -> 都保留
    same_cls = np.array([
        [0, 0, 100, 100, 0.9, 0],
        [5, 5, 105, 105, 0.8, 0],   # 与第一个 IoU 高,同类别
    ], dtype=np.float32)
    assert nms(same_cls, 0.45) == [0]

    diff_cls = np.array([
        [0, 0, 100, 100, 0.9, 0],
        [5, 5, 105, 105, 0.8, 1],   # 同位置,不同类别
    ], dtype=np.float32)
    assert nms(diff_cls, 0.45) == [0, 1]

    far_apart = np.array([
        [0, 0, 100, 100, 0.9, 0],
        [500, 500, 600, 600, 0.8, 0],
    ], dtype=np.float32)
    assert nms(far_apart, 0.45) == [0, 1]


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
