# -*- coding: utf-8 -*-
"""
demo_detect.py — detect 服务命令行 demo(在 Atlas 200I DK A2 上运行)

用法:
  # 单张图片:打印完整契约 JSON
  python demo_detect.py --model ../model_convert/om/xxx.om --image test.jpg

  # 摄像头实时:循环检测,打印一行摘要(每帧完整 JSON 太刷屏)
  python demo_detect.py --model ../model_convert/om/xxx.om --camera 0

  # 摄像头 + 500ms 间隔 + 保存标注图
  python demo_detect.py --model ../model_convert/om/xxx.om --camera 0 \\
         --interval 500 --save-dir out

按键: 摄像头模式下 ESC 退出;--show 时任意键继续下一帧。
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

from config import load_config
from detector import Detector
from mock_engine import MockEngine

# 画框颜色(BGR)
COLORS = {
    "red": (0, 0, 255),
    "yellow": (0, 255, 255),
    "blue": (255, 0, 0),
    "green": (0, 255, 0),
}


def draw_detections(img, result):
    for d in result["detections"]:
        cu, cv = int(d["center_u_px"]), int(d["center_v_px"])
        bgr = COLORS.get(d["color"], (255, 255, 255))
        cv2.circle(img, (cu, cv), 6, bgr, -1)
        label = f'{d["color"]} {d["confidence"]:.2f}'
        cv2.putText(img, label, (cu + 10, cv - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, bgr, 2)


def brief(result):
    """一行摘要,摄像头模式刷屏友好。"""
    parts = [
        f'{d["color"]}@{d["confidence"]:.2f} ({d["center_u_px"]:.0f},{d["center_v_px"]:.0f})'
        for d in result["detections"]
    ]
    return f'{result["frame_id"]} | ' + (" | ".join(parts) if parts else "(无目标)")


def main():
    ap = argparse.ArgumentParser(description="detect 检测服务 demo")
    ap.add_argument("--model", help=".om 模型路径(默认取 config.json 的 om_path)")
    ap.add_argument("--image", help="单张图片路径")
    ap.add_argument("--camera", type=int, default=None, help="摄像头设备号,如 0")
    ap.add_argument("--interval", type=int, default=0, help="摄像头模式帧间隔 ms")
    ap.add_argument("--show", action="store_true", help="弹窗显示画面(需桌面环境)")
    ap.add_argument("--save-dir", help="保存标注后的图片到该目录")
    ap.add_argument("--mock", action="store_true",
                    help="[模拟] 不用真模型,输出固定检测结果(协作规范 §三 独立演示)")
    args = ap.parse_args()

    cfg = load_config()
    if args.mock:
        engine = MockEngine(cfg["model"]["format"], len(cfg["model"]["classes"]))
        print("[模拟数据] 未使用真实模型,以下为固定检测结果,不得作为实机验收依据")
    else:
        from acl_engine import AclEngine
        model_path = args.model or cfg["model"]["om_path"]
        if not os.path.exists(model_path):
            sys.exit(f"[错误] 模型不存在: {model_path}\n"
                     f"       先执行 model_convert/convert_to_om.sh 转换,或用 --model 指定")
        engine = AclEngine(model_path)
    detector = Detector(engine, cfg)

    if args.image is None and args.camera is None:
        # 仅 --mock 且无输入时: 合成图像演示一遍契约输出
        rng = np.random.default_rng(0)
        img = rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)
        result = detector.detect(img)
        print(detector.result_json(result))
        return

    if args.image:
        img = cv2.imread(args.image)
        if img is None:
            sys.exit(f"[错误] 无法读取图片: {args.image}")
        t0 = time.time()
        result = detector.detect(img)
        cost_ms = (time.time() - t0) * 1000
        print(detector.result_json(result))
        print(f"\n[耗时] {cost_ms:.1f} ms(含预处理+推理+后处理,不含相机采集)")
        if args.show or args.save_dir:
            draw_detections(img, result)
            if args.save_dir:
                os.makedirs(args.save_dir, exist_ok=True)
                out = os.path.join(args.save_dir, f"{result['frame_id']}.jpg")
                cv2.imwrite(out, img)
                print(f"[已保存] {out}")
            if args.show:
                cv2.imshow("detect", img)
                cv2.waitKey(0)
        return

    if args.camera is not None:
        cap = cv2.VideoCapture(args.camera)
        if not cap.isOpened():
            sys.exit(f"[错误] 无法打开摄像头 {args.camera}")
        print(f"[摄像头 {args.camera}] 按 ESC 退出")
        while True:
            ok, img = cap.read()
            if not ok:
                print("[警告] 读帧失败")
                time.sleep(0.1)
                continue
            t0 = time.time()
            result = detector.detect(img)
            cost_ms = (time.time() - t0) * 1000
            print(f"{brief(result)}  [{cost_ms:.0f}ms]")
            if args.show or args.save_dir:
                draw_detections(img, result)
                if args.save_dir:
                    os.makedirs(args.save_dir, exist_ok=True)
                    cv2.imwrite(os.path.join(args.save_dir,
                                             f"{result['frame_id']}.jpg"), img)
                if args.show:
                    cv2.imshow("detect", img)
            key = cv2.waitKey(max(args.interval, 1)) & 0xFF
            if key == 27:
                break
        cap.release()
        return

    ap.print_help()


if __name__ == "__main__":
    main()
