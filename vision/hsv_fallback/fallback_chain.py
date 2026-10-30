# -*- coding: utf-8 -*-
"""
fallback_chain.py — 低置信度降级链(PRD §四 / TDD §3.4 / 错误码 LOW_CONFIDENCE)

把 detect 与 HSV 兜底串成 PRD 规定的降级路径:
  1. 检测当前帧,有目标 → (result, "real")
  2. 补采最多 max_retries 帧(默认 2)仍无目标 → 转 HSV 兜底
  3. HSV 定位成功 → (result, "fallback")
  4. 仍失败 → (None, None),调用方跳过该轮并记录(错误码 LOW_CONFIDENCE)

对应验收 F4: 异常注入时该路径必须 3 次注入 3 次进入规定路径。
"""

import time


def resolve_target(detector, locator, capture_fn, max_retries: int = 2,
                   retry_delay_ms: int = 100):
    """
    一轮分拣的目标解析。detector / locator 分别具备
    detect(img)/locate(img) -> 契约 dict。

    capture_fn: () -> BGR 图像(如 lambda: cap.read()[1])

    返回 (契约 dict, mode):
      mode = "real"     深度学习检测命中
      mode = "fallback" HSV 兜底命中
      mode = None       全部失败(跳过本轮)
    """
    result = detector.detect(capture_fn())
    if result["detections"]:
        return result, "real"

    for _ in range(max_retries):
        if retry_delay_ms > 0:
            time.sleep(retry_delay_ms / 1000.0)
        result = detector.detect(capture_fn())
        if result["detections"]:
            return result, "real"

    result = locator.locate(capture_fn())
    if result["detections"]:
        return result, "fallback"
    return None, None
