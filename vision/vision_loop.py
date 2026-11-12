# -*- coding: utf-8 -*-
"""
vision_loop.py — 视觉侧闭环演示(协作规范 §三/§四:mock 对 mock 联调准备)

把视觉链路的完整流程串起来:
  采帧 → resolve_target(检测 → 补采2帧 → HSV 兜底 → 跳过)
      → 输出 detect 契约 JSON + pick_place 请求样例

用法:
  # 全模拟: 假帧 + 假检测 + 假标定,任何机器都能跑(T-4 周 mock 联调用)
  python vision_loop.py --mock --rounds 5

  # 真摄像头 + 假检测(板子上没模型时)
  python vision_loop.py --camera 0 --mock --rounds 20

  # 板子上全真(转换完成后)
  python vision_loop.py --model ../model_convert/om/yolov5s_bs1.om --camera 0

输出: 每轮一行 JSON,含 detect 结果、mode(real/fallback)、
      pick_place 请求样例。pick_place 的 x_mm/y_mm/z_mm 用的是
      MockCalibration(像素*0.3mm 占位公式),真实标定由朱玉贺提供,
      一切 --mock 输出不得作为实机验收依据。
"""

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "detect_service"))
sys.path.insert(0, os.path.join(HERE, "hsv_fallback"))

from config import load_config  # noqa: E402
from detector import Detector  # noqa: E402
from mock_engine import MockEngine  # noqa: E402
from color_locator import ColorLocator, load_hsv_config  # noqa: E402
from fallback_chain import resolve_target  # noqa: E402


class MockCalibration:
    """模拟标定: 像素 → 基坐标系 mm(占位公式,真实标定由朱玉贺提供)。

    仅用于 mock 联调演示 pick_place 消息格式,不用于任何实机验收。
    """

    PIXEL_TO_MM = 0.3
    Z_MM = 15.0
    CALIBRATION_ID = "mock-001"

    def to_mm(self, u_px, v_px):
        return (round(u_px * self.PIXEL_TO_MM, 2),
                round(v_px * self.PIXEL_TO_MM, 2),
                self.Z_MM)


def make_pick_place(task_id, frame_id, detection, calib):
    """按 TDD §7.3 组装 pick_place 请求样例(字段照抄接口契约)。"""
    x, y, z = calib.to_mm(detection["center_u_px"], detection["center_v_px"])
    return {
        "task_id": task_id,
        "frame_id": frame_id,
        "detection_id": detection["detection_id"],
        "color": detection["color"],
        "x_mm": x,
        "y_mm": y,
        "z_mm": z,
        "bin_id": detection["color"],      # 同色积木放同色桶
        "calibration_id": calib.CALIBRATION_ID,
    }


def main():
    ap = argparse.ArgumentParser(description="视觉侧闭环演示")
    ap.add_argument("--mock", action="store_true", help="假引擎(无模型演示)")
    ap.add_argument("--model", help=".om 模型路径(真模型)")
    ap.add_argument("--camera", type=int, default=None, help="摄像头设备号")
    ap.add_argument("--rounds", type=int, default=5, help="循环轮数")
    args = ap.parse_args()

    cfg = load_config()
    if args.mock:
        engine = MockEngine(cfg["model"]["format"], len(cfg["model"]["classes"]))
        print("[模拟数据] 假引擎 + 假标定,以下输出仅演示消息格式,不作实机验收依据")
    else:
        from acl_engine import AclEngine
        if not args.model:
            sys.exit("非 mock 模式必须指定 --model")
        engine = AclEngine(args.model)

    detector = Detector(engine, cfg)
    locator = ColorLocator(load_hsv_config())
    calib = MockCalibration()

    cap = cv2.VideoCapture(args.camera) if args.camera is not None else None
    if cap is not None and not cap.isOpened():
        sys.exit(f"[错误] 无法打开摄像头 {args.camera}")

    def capture_fn():
        if cap is not None:
            ok, frame = cap.read()
            if ok:
                return frame
        # 模拟帧: 灰色背景 + 随机位置色块(HSV 兜底也能命中它)
        img = np.full((480, 640, 3), (60, 60, 60), dtype=np.uint8)
        rng = np.random.default_rng()
        x, y = int(rng.integers(100, 480)), int(rng.integers(80, 320))
        cv2.rectangle(img, (x, y), (x + 60, y + 60), (0, 0, 255), -1)
        return img

    seq = 0
    for _ in range(args.rounds):
        seq += 1
        task_id = f"t-{int(time.time() * 1000)}-{seq:04d}"
        result, mode = resolve_target(detector, locator, capture_fn,
                                      retry_delay_ms=0)
        record = {"task_id": task_id, "mode": mode, "detect": None,
                  "pick_place": None, "error_code": None}
        if result is None:
            record["error_code"] = "LOW_CONFIDENCE"
        else:
            record["detect"] = result
            if result["detections"]:
                d = result["detections"][0]
                record["pick_place"] = make_pick_place(
                    task_id, result["frame_id"], d, calib)
        print(json.dumps(record, ensure_ascii=False))

    if cap is not None:
        cap.release()


if __name__ == "__main__":
    main()
