# -*- coding: utf-8 -*-
"""
config.py — 配置文件加载(零依赖,stdlib json)

config.json 字段说明:
  model.om_path        转换产物 .om 路径(demo 里可用 --model 覆盖)
  model.input_width/height  必须与训练输入分辨率、ATC --input_shape 一致
  model.format         "v8" 或 "v5" —— 检测模型选型(T6)确定后改这里
  model.classes        类别表,顺序必须与杨泽训练时的 classes 一致
  detect.conf_threshold   PRD §四:默认 0.5
  detect.apply_sigmoid   v8 导出 ONNX 的类别分数是 logits → true;
                         v5 导出已含 sigmoid → false。
                         若实测置信度普遍异常(全部≈0.5),先怀疑这个开关。
  detect.frame_max_age_ms  帧新鲜度:超过该时长未用必须重采(PRD §四,1s)
"""

import json
import os


def load_config(path: str = None) -> dict:
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
