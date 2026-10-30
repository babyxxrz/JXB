# -*- coding: utf-8 -*-
"""
hsv_tuner.py — HSV 阈值实机标定工具(TDD §4.5,与朱玉贺一起在实机光照下用)

用法:
  # 用摄像头实时调
  python hsv_tuner.py --camera 0
  # 用已采集的四色积木照片调
  python hsv_tuner.py --image 积木照片.jpg

操作:
  1/2/3/4  切换颜色(红/黄/绿/蓝)
  p        切换当前颜色的阈值段(红色有两段,跨 hue 0/180 两端)
  s        保存到 hsv_config.json
  q/ESC    退出
  拖动 Hmin/Hmax/Smin/Smax/Vmin/Vmax 滑条实时看效果

窗口: 左侧原图+检出轮廓(绿框红心),右侧当前颜色掩码黑白图。
标定目标: 掩码里只有目标积木是白的、背景是黑的,且轮廓完整。
"""

import argparse
import json
import os
import time

import cv2
import numpy as np

from color_locator import load_hsv_config

WINDOW = "hsv_tuner"
TRACKS = ["Hmin", "Hmax", "Smin", "Smax", "Vmin", "Vmax"]
MAXV = [179, 179, 255, 255, 255, 255]


def pair_to_vals(pair):
    """配置格式 [[hmin,smin,vmin],[hmax,smax,vmax]] -> 滑条顺序"""
    lo, up = pair
    return [lo[0], up[0], lo[1], up[1], lo[2], up[2]]


def vals_to_pair(vals):
    return [[vals[0], vals[2], vals[4]], [vals[1], vals[3], vals[5]]]


def dummy(_):
    pass


def main():
    ap = argparse.ArgumentParser(description="HSV 阈值实机标定工具")
    ap.add_argument("--camera", type=int, default=None, help="摄像头设备号")
    ap.add_argument("--image", help="用一张照片标定(不带 --camera 时必须给)")
    ap.add_argument("--config", default=None, help="配置文件路径(默认 hsv_config.json)")
    args = ap.parse_args()

    config_path = args.config or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "hsv_config.json")
    cfg = load_hsv_config(config_path)
    names = list(cfg["colors"].keys())
    state = {"ci": 0, "pi": 0}

    cv2.namedWindow(WINDOW)
    for i, name in enumerate(TRACKS):
        cv2.createTrackbar(name, WINDOW, 0, MAXV[i], dummy)

    def load_trackbars():
        color = names[state["ci"]]
        vals = pair_to_vals(cfg["colors"][color][state["pi"]])
        for i, name in enumerate(TRACKS):
            cv2.setTrackbarPos(name, WINDOW, int(vals[i]))

    def save():
        color = names[state["ci"]]
        vals = [cv2.getTrackbarPos(n, WINDOW) for n in TRACKS]
        cfg["colors"][color][state["pi"]] = vals_to_pair(vals)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"[已保存] {color} 第{state['pi']}段 -> {config_path}")

    load_trackbars()

    cap = cv2.VideoCapture(args.camera) if args.camera is not None else None
    img_file = cv2.imread(args.image) if args.image else None
    if cap is None and img_file is None:
        ap.error("必须指定 --camera 或 --image")

    print(f"颜色: {'/'.join(names)} | 按键 1-{len(names)} 切换, p 切换阈值段, "
          f"s 保存, q 退出")

    while True:
        if cap is not None:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                continue
        else:
            frame = img_file.copy()

        color = names[state["ci"]]
        vals = [cv2.getTrackbarPos(n, WINDOW) for n in TRACKS]
        lo, up = vals_to_pair(vals)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(up, np.uint8))

        vis = frame.copy()
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            c = max(contours, key=cv2.contourArea)
            if cv2.contourArea(c) > 50:
                x, y, w, h = cv2.boundingRect(c)
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
                m = cv2.moments(c)
                if m["m00"] > 0:
                    cx, cy = int(m["m10"] / m["m00"]), int(m["m01"] / m["m00"])
                    cv2.circle(vis, (cx, cy), 5, (0, 0, 255), -1)
        cv2.putText(vis, f"{color} seg{state['pi']}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow(WINDOW, np.hstack([vis, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)]))

        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), 27):
            break
        elif ord("1") <= key <= ord("4"):
            idx = key - ord("1")
            if idx < len(names):
                state["ci"], state["pi"] = idx, 0
                load_trackbars()
                print(f"[切换] {names[state['ci']]}")
        elif key == ord("p"):
            state["pi"] = (state["pi"] + 1) % len(cfg["colors"][color])
            load_trackbars()
            print(f"[切换段] {color} 第{state['pi']}段")
        elif key == ord("s"):
            save()

    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
