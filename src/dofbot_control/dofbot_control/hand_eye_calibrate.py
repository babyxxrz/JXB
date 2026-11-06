# -*- coding: utf-8 -*-
"""手眼标定工具（技术设计文档 5.1 / 待定项 T11）: 由标定点对生成标定文件。

标定原理: 在桌面工作区内选 9 个分散点(推荐), 记录每个点的图像坐标(u,v,px)与
机械臂基坐标系平面坐标(x,y,mm), 用最小二乘求解平面单应矩阵 H,
使 [x,y,1]^T ~ H * [u,v,1]^T。验收: 9 点平面定位误差 <= 10mm(validate_calibration)。

输入 CSV 格式(u_px,v_px,x_mm,y_mm, 可带表头):
  u_px,v_px,x_mm,y_mm
  320,240,0.0,0.0
  ...

用法:
  ros2 run dofbot_control hand_eye_calibrate --points points.csv --out calibration.yaml
"""
import argparse
import csv
import os
import sys
import time

import yaml


def solve_homography(points):
    """DLT 最小二乘求解 3x3 单应矩阵（至少 4 个点对）。"""
    try:
        import numpy as np
    except ImportError:
        raise SystemExit("[ERROR] 需要 numpy: pip install numpy")
    n = len(points)
    if n < 4:
        raise SystemExit("[ERROR] 标定点不足 4 个, 建议 9 个分散点(验收要求)")
    a = np.zeros((2 * n, 9))
    for i, (u, v, x, y) in enumerate(points):
        a[2 * i] = [u, v, 1, 0, 0, 0, -x * u, -x * v, -x]
        a[2 * i + 1] = [0, 0, 0, u, v, 1, -y * u, -y * v, -y]
    _, _, vt = np.linalg.svd(a)
    h = vt[-1].reshape(3, 3)
    h = h / h[2, 2]
    return h


def apply_h(h, u, v):
    w = h[2, 0] * u + h[2, 1] * v + h[2, 2]
    return ((h[0, 0] * u + h[0, 1] * v + h[0, 2]) / w,
            (h[1, 0] * u + h[1, 1] * v + h[1, 2]) / w)


def main(args=None):
    parser = argparse.ArgumentParser(description="手眼标定: 由标定点对生成标定 YAML")
    parser.add_argument("--points", required=True, help="标定点 CSV: u_px,v_px,x_mm,y_mm")
    parser.add_argument("--out", default="calibration_%s.yaml" % time.strftime("%Y%m%d_%H%M%S"),
                        help="输出标定文件路径")
    parser.add_argument("--id", default="cal-%s" % time.strftime("%Y%m%d-%H%M%S"),
                        help="标定版本号 calibration_id")
    argv = parser.parse_args(args[1:] if args else sys.argv[1:])

    points = []
    with open(argv.points, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip() or not row[0].strip()[0].isdigit() and row[0][0] != "-":
                continue  # 跳过表头/空行
            points.append(tuple(float(v) for v in row[:4]))

    h = solve_homography(points)
    residuals = []
    for u, v, x, y in points:
        xp, yp = apply_h(h, u, v)
        residuals.append(round(((x - xp) ** 2 + (y - yp) ** 2) ** 0.5, 2))

    print("标定点数: %d, 标定版本: %s" % (len(points), argv.id))
    print("单应矩阵 H (px -> mm):")
    for row in h.tolist():
        print("  [%s]" % ", ".join("%10.6f" % v for v in row))
    print("各点残差(mm): %s" % residuals)
    print("最大残差: %.2f mm %s" % (max(residuals), "(>10mm, 需重新标定!)" if max(residuals) > 10 else "(<=10mm 合格)"))

    data = {
        "calibration_id": argv.id,
        "created_at_ms": int(time.time() * 1000),
        "num_points": len(points),
        "h": [[float(v) for v in row] for row in h.tolist()],
        "max_residual_mm": float(max(residuals)),
        "note": "图像原点左上角, u 向右、v 向下; 输出为机械臂基坐标系平面坐标(mm)。实机坐标系定义见 docs/标定与坐标说明.md",
    }
    with open(argv.out, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    print("标定文件已保存: %s" % os.path.abspath(argv.out))
    print("提示: 运行 validate_calibration 校验 9 点误差, 并将文件路径填入 dofbot_config.yaml 的 calibration.file")


if __name__ == "__main__":
    main()
