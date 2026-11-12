# -*- coding: utf-8 -*-
"""
gesture_classifier.py — 关键点 → 四类手势分类(纯几何,模型无关)

TDD §4.6: HRNet 输出 21 个手部关键点,本模块把关键点判成
fist(握拳)/ like(点赞)/ ok / palm(张开手掌) 四类。

设计要点:
  - 与模型解耦: 输入只要 21 个关键点的 (u,v) 坐标(左上原点,u 右 v 下),
    来自 HRNet / MediaPipe 等任何关键点模型的输出都能用(T5 待定不受影响)
  - 尺度归一: 所有距离除以 scale = 腕部(0)到中指根部(9)的长度,
    与相机距离/图像分辨率无关
  - 规则打分: 四类各算一个 0~1 得分取最高,confidence = 该得分;
    得分 < MIN_CONF 判 unknown —— 阈值只是起点,拿到真实 HRNet
    输出后需要在板子上按实测关键点再调
  - 假定正对相机的单手、手大致朝上(like 的"拇指向上"按图像 v 轴判断),
    侧向/倒置手势不在本期范围
"""

import numpy as np

# MediaPipe 21 点索引约定(HRNet 手势关键点模型通常沿用)
WRIST = 0
THUMB = [1, 2, 3, 4]        # 拇指 CMC/MCP/IP/TIP, TIP=4
INDEX = [5, 6, 7, 8]        # 食指, TIP=8
MIDDLE = [9, 10, 11, 12]    # 中指, TIP=12
RING = [13, 14, 15, 16]     # 无名指, TIP=16
PINKY = [17, 18, 19, 20]    # 小指, TIP=20
FINGER_TIPS = [8, 12, 16, 20]

# 距离阈值(×scale),起始值,板上按实测调
T_EXTENDED = 1.6     # 指尖-腕距 > 此值视为"伸出"
T_CURLED = 1.2       # 指尖-腕距 < 此值视为"蜷起"
T_CIRCLE = 0.35      # 拇指尖-食指尖 < 此值视为"捏圈"(ok)
T_THUMB_UP = 0.5     # 拇指尖高出腕部 > 此值×scale 视为"向上"(like)
MIN_CONF = 0.6       # 低于此置信度判 unknown

GESTURES = ("fist", "like", "ok", "palm")


def classify(kpts):
    """kpts: (21,2) float 数组 [u,v] 或 (N,2) 不足 21 点。

    返回 (gesture, confidence):
      gesture ∈ {"fist","like","ok","palm","unknown"}
      confidence = 该手势规则得分 0~1(规则几何的伪置信度,非模型置信度)
    """
    k = np.asarray(kpts, dtype=np.float32).reshape(-1, 2)
    if k.shape[0] < 21:
        return "unknown", 0.0

    wrist = k[WRIST]
    scale = np.linalg.norm(k[MIDDLE[0]] - wrist)
    if scale < 1e-3:
        return "unknown", 0.0

    def d(i, j):
        return np.linalg.norm(k[i] - k[j]) / scale

    tip_dists = [d(WRIST, t) for t in FINGER_TIPS]          # 四指伸蜷
    thumb_tip = d(WRIST, THUMB[3])
    thumb_up = (wrist[1] - k[THUMB[3]][1]) / scale           # >0 即高于腕部
    circle = d(THUMB[3], INDEX[3])                          # ok 捏圈

    def clamped(x, lo, hi):
        return float(min(max(x, lo), hi))

    # 各手势规则得分: 线性伸缩到 0~1
    scores = {}
    # fist: 四指全蜷,且拇指不伸(乘法: 任一条件不满足即大幅扣分,
    # 否则 ok/like 这类"拇指离开掌心"的手势会误判成握拳)
    curled = [clamped((T_EXTENDED - x) / (T_EXTENDED - T_CURLED), 0, 1)
              for x in tip_dists]
    thumb_ext = clamped((thumb_tip - T_CURLED) / (T_EXTENDED - T_CURLED), 0, 1)
    scores["fist"] = float(np.mean(curled)) * (1.0 - thumb_ext)
    # like: 拇指向上伸出 + 四指蜷
    up = clamped((thumb_up - 0.2 * T_THUMB_UP) / T_THUMB_UP, 0, 1)
    scores["like"] = 0.5 * thumb_ext * up + 0.5 * float(np.mean(curled))
    # ok: 拇指食指捏圈 + 中指/无名指/小指伸出(至少两根)
    ring_ext = [clamped((tip_dists[i] - T_CURLED) / (T_EXTENDED - T_CURLED), 0, 1)
                for i in (1, 2, 3)]
    circle_s = clamped(1.0 - (circle / T_CIRCLE) ** 2, 0, 1)
    scores["ok"] = 0.7 * circle_s + 0.3 * float(np.mean(ring_ext))
    # palm: 四指全伸
    ext = [clamped((x - T_CURLED) / (T_EXTENDED - T_CURLED), 0, 1)
           for x in tip_dists]
    scores["palm"] = float(np.mean(ext))

    best = max(scores, key=scores.get)
    conf = round(scores[best], 4)
    return (best, conf) if conf >= MIN_CONF else ("unknown", conf)
