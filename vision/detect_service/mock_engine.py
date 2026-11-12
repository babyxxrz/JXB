# -*- coding: utf-8 -*-
"""
mock_engine.py — 模拟推理引擎(协作规范 §三:无模型也能独立演示)

提供与 AclEngine 相同的 infer([np.ndarray]) -> list[np.ndarray] 接口,
但返回固定检测结果,不碰 ACL。所有用到它的输出必须明确标记"模拟",
不得冒充实机验收结果。

被 demo_detect.py(--mock)、vision_loop.py(--mock) 共用。
"""

import numpy as np


class MockEngine:
    """固定输出一个高置信"red"目标(输入图像中心附近)。"""

    def __init__(self, model_format="v8", nc=4):
        self.model_format = model_format
        self.nc = nc

    def infer(self, inputs):
        if self.model_format == "v8":
            raw = np.full((1, 4 + self.nc, 8400), -10.0, dtype=np.float32)
            raw[0, 0, 0] = 320.0; raw[0, 1, 0] = 320.0   # 中心
            raw[0, 2, 0] = 100.0; raw[0, 3, 0] = 100.0   # 宽高
            raw[0, 4, 0] = 10.0                          # red logit
            return [raw]
        raw = np.full((1, 8400, 5 + self.nc), 0.01, dtype=np.float32)
        raw[0, 0, 0:4] = [270.0, 270.0, 370.0, 370.0]
        raw[0, 0, 4] = 0.9
        return [raw]
