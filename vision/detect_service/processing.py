# -*- coding: utf-8 -*-
"""
processing.py — 预处理与后处理(纯 numpy + OpenCV,不依赖 ACL)

开发机上可直接单测(见 tests/test_processing.py),
板子上与 acl_engine.py 一起使用。

预处理: BGR 图 → letterbox 等比缩放灰边填充 → RGB → CHW → /255 float32
后处理: 支持 YOLOv8 / YOLOv5 两种导出格式的原始输出解码 + NMS
        (检测模型选型 T6 待定,两种都实现,config.json 里切换)
"""

import cv2
import numpy as np

PAD_COLOR = (114, 114, 114)


# ---------------------------------------------------------------
# 预处理
# ---------------------------------------------------------------
def letterbox(img_bgr, new_shape=(640, 640), color=PAD_COLOR):
    """等比缩放 + 灰边填充。
    返回 (填充图, scale, (dw, dh)),dw/dh 为左右/上下填充宽度(可能带小数)。"""
    h, w = img_bgr.shape[:2]
    tw, th = new_shape
    scale = min(tw / w, th / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    # 注意: 仅当缩放后尺寸与目标完全一致才免填充;
    # "无需缩放"≠"无需填充"(如 480x640 -> 640x640 仍需上下补灰边)
    if (nw, nh) == (tw, th):
        return img_bgr.copy(), 1.0, (0.0, 0.0)
    resized = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dw = (tw - nw) / 2.0
    dh = (th - nh) / 2.0
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right,
                                cv2.BORDER_CONSTANT, value=color)
    return padded, scale, (dw, dh)


def preprocess(img_bgr, input_size=(640, 640)):
    """返回 (输入 blob (1,3,H,W) float32 连续内存, scale, (dw, dh))。
    后两者用于把检测框坐标映射回原图。"""
    padded, scale, (dw, dh) = letterbox(img_bgr, input_size)
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    blob = rgb.transpose(2, 0, 1)[None, ...].astype(np.float32) / 255.0
    return np.ascontiguousarray(blob), scale, (dw, dh)


# ---------------------------------------------------------------
# 后处理
# ---------------------------------------------------------------
def sigmoid(x):
    """数值稳定的 sigmoid(logits 极负时 np.exp(-x) 会溢出)。

    注意不能用 np.where(x>=0, a, b): 它会先算完两个分支再选取,
    x=±1000 时其中一个分支必溢出。按掩码只计算需要的分支。"""
    x = np.asarray(x, dtype=np.float32)
    out = np.empty_like(x)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    neg = ~pos
    out[neg] = np.exp(x[neg]) / (1.0 + np.exp(x[neg]))
    return out


def _boxes_from_xywh(xywh):
    """cx,cy,w,h → x1,y1,x2,y2(不裁剪,交给 map_to_original)。"""
    out = np.empty_like(xywh, dtype=np.float32)
    out[:, 0] = xywh[:, 0] - xywh[:, 2] / 2.0
    out[:, 1] = xywh[:, 1] - xywh[:, 3] / 2.0
    out[:, 2] = xywh[:, 0] + xywh[:, 2] / 2.0
    out[:, 3] = xywh[:, 1] + xywh[:, 3] / 2.0
    return out


def _filter(boxes, scores, cls_ids, conf_thresh):
    """按阈值过滤并按置信度降序,返回 (N,6) [x1,y1,x2,y2,score,cls]"""
    mask = scores >= conf_thresh
    if not mask.any():
        return np.empty((0, 6), dtype=np.float32)
    out = np.concatenate(
        [boxes[mask], scores[mask, None], cls_ids[mask, None].astype(np.float32)],
        axis=1,
    )
    return out[out[:, 4].argsort()[::-1]]


def decode_v8(raw, nc, conf_thresh, apply_sigmoid=True):
    """YOLOv8 导出(不含 NMS): 输出 (1, 4+nc, N),框已解码为 cx,cy,w,h,
    类别分数是 logits(默认需要 sigmoid)。"""
    raw = np.asarray(raw, dtype=np.float32)
    pred = raw[0].T if raw.ndim == 3 else raw      # (N, 4+nc)
    boxes = _boxes_from_xywh(pred[:, :4])
    cls = pred[:, 4:]
    if apply_sigmoid:
        cls = sigmoid(cls)
    scores = cls.max(axis=1)
    cls_ids = cls.argmax(axis=1)
    return _filter(boxes, scores, cls_ids, conf_thresh)


def decode_v5(raw, nc, conf_thresh):
    """YOLOv5 导出: 输出 (1, N, 5+nc),obj 与 cls 已在导出图中做过 sigmoid。
    最终置信度 = obj × cls。"""
    raw = np.asarray(raw, dtype=np.float32)
    pred = raw[0] if raw.ndim == 3 else raw        # (N, 5+nc)
    boxes = _boxes_from_xywh(pred[:, :4])
    obj = pred[:, 4]
    cls = pred[:, 5:]
    scores = obj * cls.max(axis=1)
    cls_ids = cls.argmax(axis=1)
    return _filter(boxes, scores, cls_ids, conf_thresh)


def decode(outputs, num_classes, conf_thresh, model_format="v8", apply_sigmoid=True):
    """统一入口: outputs 为 AclEngine.infer 的返回值(list,取第一个)。
    返回 (N,6) [x1,y1,x2,y2,score,cls_id],按置信度降序。"""
    if model_format == "v8":
        return decode_v8(outputs[0], num_classes, conf_thresh, apply_sigmoid)
    if model_format == "v5":
        return decode_v5(outputs[0], num_classes, conf_thresh)
    raise ValueError(f"未知 model_format: {model_format}(支持 v8 / v5)")


def nms(dets, iou_thresh):
    """类别感知 NMS。dets: (N,6) [x1,y1,x2,y2,score,cls],返回保留行下标列表。
    不同类别的框不互相抑制(四色积木可能叠放)。"""
    if len(dets) == 0:
        return []
    x1, y1 = dets[:, 0], dets[:, 1]
    x2, y2 = dets[:, 2], dets[:, 3]
    scores, classes = dets[:, 4], dets[:, 5]
    areas = np.maximum(x2 - x1, 0.0) * np.maximum(y2 - y1, 0.0)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(xx2 - xx1, 0.0) * np.maximum(yy2 - yy1, 0.0)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-6)
        same_cls = classes[rest] == classes[i]
        order = rest[(iou <= iou_thresh) | ~same_cls]
    return keep


def map_to_original(xyxy, scale, dw, dh, img_w, img_h):
    """letterbox 坐标 → 原图像素坐标,裁剪到图像范围内。"""
    xyxy = np.asarray(xyxy, dtype=np.float32).copy()
    xyxy[0] = np.clip((xyxy[0] - dw) / scale, 0, img_w)
    xyxy[2] = np.clip((xyxy[2] - dw) / scale, 0, img_w)
    xyxy[1] = np.clip((xyxy[1] - dh) / scale, 0, img_h)
    xyxy[3] = np.clip((xyxy[3] - dh) / scale, 0, img_h)
    return xyxy
