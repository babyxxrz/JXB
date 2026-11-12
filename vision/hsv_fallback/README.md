# hsv_fallback — HSV 颜色分割兜底通道(PRD §四 / TDD §4.5)

低置信度时,深度学习检测失败后由 `fallback_chain.resolve_target` 自动降级到
本模块:用 OpenCV 颜色阈值分割独立定位积木,输出契约与 detect **完全同格式**,
控制层(朱玉贺)按 `mode=fallback` 记入 task_event。**兜底结果不计入检测模型 mAP**。

## 文件

| 文件 | 说明 | 运行位置 |
|---|---|---|
| hsv_config.json | 四色 HSV 阈值、最小面积比、形态学核大小 | — |
| color_locator.py | ColorLocator:色块定位,输出契约 dict | 板子(也可本地) |
| fallback_chain.py | resolve_target:detect → 补采2帧 → HSV → 跳过 | 板子 |
| hsv_tuner.py | Trackbar 滑条实时标定阈值工具 | 板子(带屏幕) |

## 关键设计

- **红色 hue 跨 0/180 两端**:配置里给两段阈值,`_mask_for` 做 OR 合并,
  纯红(H=0)和偏紫的深红(H≈176)都能检出
- **伪置信度**:confidence = 轮廓面积/包围盒面积(fill_ratio, 0~1),
  仅为保持契约格式统一,**不代表模型置信度**,文档与代码中均已注明
- **最小面积过滤**:`min_area_ratio × 图像面积`,滤掉噪点小块
- **形态学**:开运算(open_kernel=5)去噪点,闭运算(close_kernel=7)填空洞
- **多目标时按面积降序**,单目标分拣场景控制层取第一个即可

## 用法

```python
from color_locator import ColorLocator, load_hsv_config
locator = ColorLocator(load_hsv_config("hsv_config.json"))
result = locator.locate(img_bgr, captured_at_ms=None)   # 返回契约 dict
```

完整的降级链(与 detector 组合):

```python
from fallback_chain import resolve_target
result, mode = resolve_target(detector, locator, lambda: cap.read()[1])
# mode: "real" 深度学习命中 / "fallback" HSV 兜底命中 / None 跳过本轮
# 调用方: result 为 None 时记录错误码 LOW_CONFIDENCE 并跳过
```

## 实机标定(必须做!)

**配置文件里的阈值只是初始值,必须与朱玉贺一起在实机光照下用 hsv_tuner 重新标定**,
否则兜底通道形同虚设(TDD §4.5):

```bash
python hsv_tuner.py --camera 0          # 实时调,1-4 切颜色、p 切阈值段、s 保存、q 退出
python hsv_tuner.py --image 积木照片.jpg # 或用已采集的照片离线调
```

标定目标:掩码中只有目标积木为白色、背景为黑、轮廓完整。

## 单测(开发机即可)

```bash
python tests/test_color_locator.py
```

覆盖:四色识别+质心精度、红色两段 hue、契约格式同构、空背景返回空数组、
最小面积过滤、降级链 4 条路径(立即命中/补采命中/HSV 兜底/全部失败跳过)。
