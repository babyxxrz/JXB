# -*- coding: utf-8 -*-
"""
perf_test.py — 端侧单帧推理耗时 P95 测试(验收 F1 / TDD §4.7,交付物之一)

验收口径: 预热后连测 100 帧,覆盖 预处理+推理+后处理,**不含相机采集**;
P95 ≤ 150ms。测试记录(模型版本、输入分辨率、逐帧耗时、汇总统计)写入 CSV。

板子上真实测试(需先完成模型转换,见 model_convert/README.md):
  python tests/perf_test.py --model ../model_convert/om/yolov5s_bs1.om --image 测试图.jpg

开发机自检(假引擎,验证脚本与 CSV 生成逻辑):
  python tests/perf_test.py --fake

计时三段与 detector.Detector.detect 内部调用链完全一致:
  preprocess(letterbox+RGB+CHW+/255) -> engine.infer -> decode+nms
"""

import argparse
import csv
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "detect_service"))
from config import load_config  # noqa: E402
from processing import decode, nms, preprocess  # noqa: E402

BUDGET_MS = 150.0   # PRD F1 / TDD §4.7 验收上限


class FakeEngine:
    """开发机自检用: 按 config 格式生成假输出,模拟 1~3ms 推理延迟。"""

    def __init__(self, nc, model_format):
        self.nc = nc
        self.model_format = model_format

    def infer(self, inputs):
        time.sleep(random.uniform(0.001, 0.003))
        if self.model_format == "v8":
            return [np.full((1, 4 + self.nc, 8400), -10.0, dtype=np.float32)]
        return [np.full((1, 8400, 5 + self.nc), 0.01, dtype=np.float32)]


def build_engine(model_path, config):
    """板子上加载 AclEngine(依赖 PyACL,本地无 acl 时给出明确报错)。"""
    if model_path is None:
        raise SystemExit("必须指定 --model(板子上测试)或 --fake(开发机自检)")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "detect_service"))
    from acl_engine import AclEngine  # noqa: E402
    return AclEngine(model_path)


def measure_once(engine, config, img):
    """测一帧的 预处理/推理/后处理 三段耗时,与 Detector.detect 同口径。"""
    nc = len(config["model"]["classes"])
    input_size = (config["model"]["input_width"],
                  config["model"]["input_height"])
    conf_thresh = config["detect"]["conf_threshold"]
    iou_thresh = config["detect"]["iou_threshold"]

    t0 = time.perf_counter()
    blob, _, _ = preprocess(img, input_size)
    t1 = time.perf_counter()
    outputs = engine.infer([blob])
    t2 = time.perf_counter()
    dets = decode(
        outputs, nc, conf_thresh,
        model_format=config["model"]["format"],
        apply_sigmoid=config["detect"].get("apply_sigmoid", True),
    )
    if len(dets) > 0:
        dets = dets[nms(dets, iou_thresh)]
    t3 = time.perf_counter()
    return (t1 - t0) * 1000.0, (t2 - t1) * 1000.0, (t3 - t2) * 1000.0


def write_csv(out_path, config, model_label, frames, totals):
    """CSV 测试记录: # 元信息 + 逐帧数据 + 汇总统计(交付物格式)。"""
    p95 = float(np.percentile(totals, 95))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# P95 单帧推理耗时测试记录(PRD F1 / TDD §4.7)"])
        w.writerow(["# 测试时间", time.strftime("%Y-%m-%d %H:%M:%S")])
        w.writerow(["# 设备", model_label])
        w.writerow(["# 模型文件", config["model"]["om_path"]])
        w.writerow(["# 输入分辨率", f"{config['model']['input_width']}x{config['model']['input_height']}"])
        w.writerow(["# 输出格式/类别", config["model"]["format"], "/".join(config["model"]["classes"])])
        w.writerow(["# 统计口径", "预处理+推理+后处理,不含相机采集;预热10帧后连测100帧"])
        w.writerow([])
        w.writerow(["frame_idx", "pre_ms", "infer_ms", "post_ms", "total_ms"])
        for i, (pre, inf, post) in enumerate(frames, 1):
            w.writerow([i, f"{pre:.3f}", f"{inf:.3f}", f"{post:.3f}", f"{pre + inf + post:.3f}"])
        w.writerow([])
        w.writerow(["metric", "value_ms"])
        a = np.array(totals)
        for name, v in [("count", len(a)), ("mean", a.mean()),
                        ("p50", np.percentile(a, 50)), ("p90", np.percentile(a, 90)),
                        ("p95", p95), ("p99", np.percentile(a, 99)),
                        ("max", a.max()), ("min", a.min()),
                        ("budget", BUDGET_MS)]:
            w.writerow([name, f"{v:.3f}"])
        w.writerow(["result", "PASS" if p95 <= BUDGET_MS else "FAIL"])
    return p95


def main():
    ap = argparse.ArgumentParser(description="端侧单帧推理 P95 测试")
    ap.add_argument("--model", help=".om 模型路径(板子上测试用)")
    ap.add_argument("--fake", action="store_true", help="用假引擎自检脚本(开发机)")
    ap.add_argument("--image", help="测试图(不指定则用随机噪声图 640x480)")
    ap.add_argument("--frames", type=int, default=100, help="连测帧数(默认100)")
    ap.add_argument("--warmup", type=int, default=10, help="预热帧数(默认10)")
    ap.add_argument("--out", help="CSV 输出路径(默认 tests/perf_result_时间戳.csv)")
    args = ap.parse_args()

    config = load_config()
    if args.fake:
        engine = FakeEngine(len(config["model"]["classes"]),
                            config["model"]["format"])
        model_label = "开发机(假引擎,仅验证测试逻辑)"
    else:
        engine = build_engine(args.model, config)
        model_label = "Atlas 200I DK A2"

    if args.image:
        img = __import__("cv2").imread(args.image)
        if img is None:
            raise SystemExit(f"读不到图像: {args.image}")
    else:
        rng = np.random.default_rng(0)
        img = rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)

    print(f"[预热 {args.warmup} 帧]")
    for _ in range(args.warmup):
        measure_once(engine, config, img)

    print(f"[连测 {args.frames} 帧]")
    frames = []
    for _ in range(args.frames):
        frames.append(measure_once(engine, config, img))
    totals = [sum(f_) for f_ in frames]

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        time.strftime("perf_result_%Y%m%d_%H%M%S.csv"))
    p95 = write_csv(out_path, config, model_label, frames, totals)

    print(f"\n设备: {model_label}")
    print(f"帧数: {len(frames)} | 平均 {np.mean(totals):.1f}ms | "
          f"P50 {np.percentile(totals, 50):.1f}ms | "
          f"P90 {np.percentile(totals, 90):.1f}ms | "
          f"P95 {p95:.1f}ms | 最大 {max(totals):.1f}ms")
    print(f"预算: ≤{BUDGET_MS:.0f}ms -> {'PASS' if p95 <= BUDGET_MS else 'FAIL'}")
    print(f"记录: {out_path}")


if __name__ == "__main__":
    main()
