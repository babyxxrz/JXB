# -*- coding: utf-8 -*-
"""
test_gesture_classifier.py — 手势分类单测(合成关键点,开发机即可运行)

用构造的 21 点手势(腕部在 (0,0)、中指根部在 (0,1),scale=1)验证:
  - 四类标准手势各判对
  - 得分低于 MIN_CONF 判 unknown
  - 关键点不足 21 个 / scale≈0 的退化输入不崩溃

注意: 阈值是几何规则起始值,真实 HRNet 关键点上板后需再调,
本测试锁定的是"规则逻辑正确",不是板上精度。

运行: python tests/test_gesture_classifier.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "gesture"))
from gesture_classifier import classify  # noqa: E402


def make_hand(overrides):
    """默认: 腕部(0,0)、四指根在 (0,1) 附近、所有指尖蜷在掌心。
    overrides: {关键点索引: (u,v)} 覆盖。"""
    pts = np.zeros((21, 2), dtype=np.float32)
    # 指根: 食指/中指/无名指/小指 MCP 在 y=1 横向排开
    pts[5], pts[9], pts[13], pts[17] = (-0.6, 0.9), (0.0, 1.0), (0.6, 0.9), (1.1, 0.8)
    # 拇指: 从腕部斜向上(默认蜷缩状态,靠内)
    pts[1], pts[2], pts[3], pts[4] = (-0.3, 0.3), (-0.45, 0.2), (-0.55, 0.05), (-0.6, -0.1)
    # 其余指尖默认蜷在掌心(距腕 < T_CURLED=1.2)
    pts[8], pts[12], pts[16], pts[20] = (-0.5, 0.6), (0.1, 0.5), (0.55, 0.6), (0.9, 0.7)
    for idx, (u, v) in overrides.items():
        pts[idx] = (u, v)
    return pts


def test_fist():
    g, conf = classify(make_hand({}))
    assert g == "fist", (g, conf)
    assert conf >= 0.6


def test_like():
    # 拇指向上伸出,四指蜷
    g, conf = classify(make_hand({
        4: (0.5, -1.7),          # 拇指尖: 距腕 1.77, 高出腕部 1.7
    }))
    assert g == "like", (g, conf)


def test_ok():
    # 拇指尖与食指尖捏圈,中指/无名指/小指全伸
    g, conf = classify(make_hand({
        4: (-0.5, -0.4),         # 拇指尖
        8: (-0.42, -0.5),        # 食指尖(与拇指尖相距 ~0.13)
        12: (0.05, -1.75),       # 中指伸出(距腕 1.75)
        16: (0.55, -1.7),        # 无名指伸出
        20: (0.95, -1.5),        # 小指伸出
    }))
    assert g == "ok", (g, conf)


def test_palm():
    # 四指全伸(距腕 > T_EXTENDED=1.6)
    g, conf = classify(make_hand({
        8: (-0.5, -1.7), 12: (0.1, -1.8), 16: (0.6, -1.7), 20: (1.0, -1.5),
    }))
    assert g == "palm", (g, conf)


def test_unknown_low_conf():
    # 半伸不蜷的"中间态"(指尖距腕 1.3~1.5,四类得分都低) -> unknown
    g, conf = classify(make_hand({
        8: (-0.6, -1.2), 12: (0.1, -1.3), 16: (0.6, -1.2), 20: (1.0, -1.1),
    }))
    assert g == "unknown", g
    assert conf < 0.6


def test_degenerate_inputs():
    assert classify(np.zeros((10, 2)))[0] == "unknown"   # 关键点不足
    assert classify(np.zeros((21, 2)))[0] == "unknown"   # scale≈0
    g, _ = classify(make_hand({4: (0.5, -1.7)}).tolist())  # list 输入也可
    assert g == "like"


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
