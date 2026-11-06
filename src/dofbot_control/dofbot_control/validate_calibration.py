# -*- coding: utf-8 -*-
"""标定验收工具（技术设计文档 5.1）: 工作区内 9 个分散点, 平面定位误差 <= 10mm。

用法:
  ros2 run dofbot_control validate_calibration --calibration calibration.yaml --points test.csv
"""
import argparse
import csv
import sys

import yaml

from .calibration import load_calibration


def main(args=None):
    parser = argparse.ArgumentParser(description="标定验收: 校验定位误差 <= 10mm")
    parser.add_argument("--calibration", required=True, help="标定 YAML 文件")
    parser.add_argument("--points", required=True, help="测试点 CSV: u_px,v_px,x_mm,y_mm")
    argv = parser.parse_args(args[1:] if args else sys.argv[1:])

    calib = load_calibration(argv.calibration)
    print("标定版本: %s, 标定点数: %d" % (calib.calibration_id, calib.num_points))

    points = []
    with open(argv.points, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip() or not row[0].strip()[0].isdigit() and row[0][0] != "-":
                continue
            points.append(tuple(float(v) for v in row[:4]))

    errors = []
    print("%-8s %-8s %-10s %-10s %-10s %-10s %-8s" %
          ("u_px", "v_px", "x_期望mm", "y_期望mm", "x_计算mm", "y_计算mm", "误差mm"))
    for u, v, x, y in points:
        xp, yp = calib.to_mm(u, v)
        err = ((x - xp) ** 2 + (y - yp) ** 2) ** 0.5
        errors.append(err)
        print("%-8.1f %-8.1f %-10.1f %-10.1f %-10.1f %-10.1f %-8.2f" %
              (u, v, x, y, xp, yp, err))
    max_err = max(errors)
    passed = max_err <= 10.0
    print("\n测试点数: %d, 最大误差: %.2f mm -> 验收(<=10mm): %s" %
          (len(points), max_err, "PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
