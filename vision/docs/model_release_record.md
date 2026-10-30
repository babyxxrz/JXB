# 模型版本记录(model_release 台账)

> 点验交付物:"模型版本与输入分辨率说明"。
> 每次接收杨泽的 model_release 或重新转换,新增一行/一节。
> model_release 契约字段(PRD §四):model_id、model_file、
> input_width_px/input_height_px、classes、trained_at_ms、val_map50。

## 当前生效版本

| 项 | 值 |
|---|---|
| model_id | *(待杨泽交付后填写)* |
| model_file(ONNX) | |
| model_file(OM) | |
| input_width_px × input_height_px | |
| classes | red / yellow / blue / green |
| trained_at_ms | |
| val_map50(训练机) | |
| 转换命令(ATC) | 见 model_convert/README.md,命令快照: |
| CANN / ATC 版本 | |
| 量化方式 | FP16 / INT8 / 不量化 |
| 端侧测试集 mAP@0.5 | ≥ 0.75 方可通过 |
| 转换日期 / 操作人 | |

## 历史版本

| model_id | ONNX | OM | 分辨率 | 量化 | 训练机 mAP | 端侧 mAP | 备注 |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## 转换前后 mAP 对照记录

| model_id | 训练机 mAP@0.5 | 端侧 FP32/FP16 mAP@0.5 | 损失 | 测试集规模 | 日期 |
|---|---|---|---|---|---|
| | | | | | |
