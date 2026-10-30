# detect_service — 检测服务(张鹏源核心交付物)

对应 PRD §四 `detect` 接口契约、TDD §4.4。

## 文件

| 文件 | 说明 | 运行位置 |
|---|---|---|
| config.json | 模型路径/输入分辨率/格式/类别/阈值/帧新鲜度 | — |
| config.py | 配置加载(零依赖) | 任意 |
| processing.py | 预处理(letterbox)+ 后处理(v8/v5 解码 + 类别感知 NMS) | 任意(可单测) |
| detector.py | Detector 类:契约输出、帧新鲜度、缓存失效 | 任意(可单测) |
| acl_engine.py | PyACL 封装:加载 .om、infer | 仅 Atlas 200I DK A2 |
| demo_detect.py | 命令行 demo:单图 / 摄像头 | 板子 |

## 在板子上的使用顺序

```bash
# 1. 转换模型(在 vision/ 目录下)
bash model_convert/convert_to_om.sh

# 2. 单图自测(会打印完整契约 JSON)
cd detect_service
python demo_detect.py --model ../model_convert/om/xxx.om --image 测试图.jpg

# 3. 摄像头实时(ESC 退出)
python demo_detect.py --model ../model_convert/om/xxx.om --camera 0 --show
```

无模型独立演示(协作规范 §三,固定检测结果,输出明确标记"模拟"):

```bash
python demo_detect.py --mock                 # 合成图上输出一遍契约 JSON
python demo_detect.py --mock --image 测试图.jpg
```

## 契约输出示例

```json
{
  "frame_id": "f-1760000000000-000001",
  "captured_at_ms": 1760000000000,
  "image_width_px": 640,
  "image_height_px": 480,
  "detections": [
    {"detection_id": "d-f-1760000000000-000001-0", "color": "red",
     "confidence": 0.934, "center_u_px": 320.5, "center_v_px": 240.1}
  ]
}
```

## 与朱玉贺联调时的 API(核心 3 个方法)

```python
result = detector.detect(img_bgr)      # 输入一帧,返回契约 dict
fresh  = detector.fresh_result()       # 帧超 1s 未用 -> None(必须重采)
detector.invalidate_cache()            # 任务完成后调用:禁复用旧帧
```

## 两个易错开关(config.json)

- `model.format`: `v8` / `v5`,选型(T6)确定后改
- `detect.apply_sigmoid`: v8 导出类别分数是 logits → `true`;
  v5 导出已含 sigmoid → `false`。**实测置信度普遍 ≈0.5 时,先怀疑它**

## 开发机单测(不需要板子)

```bash
python tests/test_processing.py          # 预处理/后处理数学
python tests/test_detector_pipeline.py   # 契约字段/坐标映射/帧新鲜度
```
