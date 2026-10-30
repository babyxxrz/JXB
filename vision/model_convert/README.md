# 模型转换链路:PyTorch → ONNX → ATC → OM

对应 TDD §4.3。选型状态:转换链路**已定**(PyTorch→ONNX→ATC→.om),
检测模型具体版本**待定**(T6,以可转 OM + P95≤150ms + mAP≥0.75 为约束)。

## 一、完整流程

```
① 杨泽训练 → ② 导出 ONNX(不含 NMS)→ ③ verify_onnx.py 检查
→ ④ convert_to_om.sh 转 .om → ⑤ 端侧推理对拍 → ⑥ 填入 model_release_record.md
```

| 步骤 | 在哪台机器 | 命令 / 文件 | 通过标准 |
|---|---|---|---|
| ② 导出 ONNX | 训练机(杨泽) | YOLOv8: `model.export(format='onnx')`<br>YOLOv5: `python export.py --weights x.pt --include onnx` | 导出成功 |
| ③ 合法性检查 | 任意 | `python verify_onnx.py models/x.onnx` | checker 通过、无 NMS 算子 |
| ④ ATC 转换 | Atlas 200I DK A2 | `bash convert_to_om.sh` | 生成 .om 无报错 |
| ⑤ 推理对拍 | 板子 | detect_service 的 demo 脚本 | 与 PyTorch 输出一致 |
| ⑥ 记录版本 | — | 填 docs/model_release_record.md | 每字段齐全 |

## 二、常见坑(按遇到频率排序)

1. **NMS 算子在 ONNX 里 → ATC 转换失败。**
   解决:训练侧导出【不含后处理】的 ONNX,YOLOv8 默认导出即是;
   NMS 放在端侧 CPU(本仓库 detect_service 已实现)。
2. **input_name 写错 → 转换失败。**
   解决:转换前必跑 verify_onnx.py,按打印的输入名改 convert_to_om.sh 的
   INPUT_NAME。
3. **动态 shape → 失败。**
   ATC 要求固定 shape,`--input_shape` 写成 `1,3,640,640` 形式。
4. **Resize / 其他算子不支持。**
   先尝试 `onnx-simplifier` 简化;不行则让训练侧换导出参数
   (如 YOLOv5 导出时 `--opset 11`)。
5. **soc_version 不对。**
   在板子上执行 `npu-smi info`,按真实芯片改 SOC_VERSION。
   Atlas 200I DK A2 应为 Ascend310B 系列。
6. **fp16 精度掉点明显。**
   先试 `--precision_mode=allow_fp32_to_fp16`(比默认 force_fp16 稳);
   仍不行,把模型整体换小而非继续降精度。

## 三、量化决策(FP16 / INT8)

| 方案 | 工程成本 | 预期 |
|---|---|---|
| FP16(默认推荐) | 零额外成本 | 精度基本不掉,速度约 2× |
| INT8 | 需标定数据集(杨泽提供未标注图即可)+ 标定脚本 + 精度复测 | 速度更快,但工程量大 |

**决策规则**:FP16 满足 P95 ≤ 150ms 就到此为止,不折腾 INT8。
把结论写进 model_release_record.md。

## 四、AIPP 说明(暂时不用管)

AIPP 可把归一化/BGR2RGB 等预处理下沉到硬件,省 CPU 时间。
第一版**不用 AIPP**(AIPP_CFG 留空),预处理在 CPU 侧做(代码在
detect_service),P95 不达标再考虑下沉。

## 五、目录约定

```
models/   ← 杨泽交付的 ONNX 放这里(git 不跟踪大文件)
om/       ← 转换产物 .om
```
