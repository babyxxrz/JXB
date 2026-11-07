# 杨泽：四色积木数据与训练交付 v001

状态：联调版本；模型已实机推理，正式验收材料仍有缺口，见 records/验收记录.md。
本目录与张鹏源的 vision/detect_service 并存，不覆盖队友代码。

## 快速复现已成功的板端演示

1. 使用课程开发板已有推理环境（见 requirements-board.md）。将附件 infer_project_om.tar.gz 上传到 `/home/HwHiAiUser/RobotArm/`，确认无同名工程冲突后解压：`tar -xzf infer_project_om.tar.gz`。
2. 进入 infer_project，运行 `python3 om_infer.py --model=output/yolov5s_bs1.om --eval --visible`；图片测试输出在 output/img。包内已包含脚本、依赖源文件、类别配置及21张测试图片。
3. 在该板Jupyter打开 notebooks/live_detection.ipynb；连接USB摄像头，按顺序运行。支持环境变量 JXB_INFER_PROJECT 指定其他解压位置。第二个代码单元格只显示上一轮最后一帧，不用于实时抓取。

## 模型接口

将附件 best.onnx、best.pt、yolov5s_bs1.om 放到本目录 artifacts/，即可按 model_release.json 的相对路径定位；路径以该JSON所在目录为基准，不以调用者当前目录为基准。
classes按模型索引固定为 `[blue, green, red, yellow]`，源标签是Blue/Green/Red/Yellow。不可按文档示例的排列重新排序权重类别。
网络输入是640×640；摄像头实测是640×480，二者不混淆。输入采用letterbox、BGR转RGB、NCHW、除255、FP16；课程转换脚本指定Ascend310B1、batch1。
model_release.json 的 trained_at_ms 仍为null，因此为显式草稿，尚不满足最终int64接口；不得用本次打包时间替代。val_map50=0.995来源是训练CSV，不是OM测试集分数。

## 已有成果

- 206张原始图片及标注、129/56/21划分、逐文件清单和SHA256。
- 100轮训练参数、CSV和完整曲线/TensorBoard附件。
- best.pt、best.onnx、实测OM；PT和ONNX与转换包中的同名模型字节一致。
- 21张图板端结果：map50 0.943、map50:95 0.821（聊天截图观察，原始日志待归档）。
- 连续识别Notebook和原始会话证据附件。

## 联调边界

Notebook阈值0.4是调试值；技术设计正式detect默认0.5。Notebook没有frame_id/captured_at_ms/detection_id、过期帧判断、标定和抓取，不作为正式检测服务替代品。
输出坐标属于原始相机平面。张鹏源和朱玉贺必须先对齐原始/透视校正坐标，不能直接把像素当毫米。
旧arm_line2固定点位脚本、旧模型和环境安装包不属于本交付。

## 训练复现范围

实际训练使用课程Ascend Model Adapter的YOLOv5s流程，不是早期YOLOv8候选脚本。设置100轮、batch12、拆分参数0.3、冻结10层；完整配置见 records/opt.yaml。
课程GUI安装包和Conda环境未复制入Git。本次保留真实数据划分和原始训练记录；未声称已在全新机器完成训练复现。
训练hyp中有色相/饱和度增强，按原始值保存，不伪装成禁用了颜色增强。

## 获取附件

附件通过 GitHub Release 预发布版分发（联调版，正式验收缺口见 records/验收记录.md）：

- 下载页：https://github.com/babyxxrz/JXB/releases/tag/training-v001
- 8 个附件统一前缀：`https://github.com/babyxxrz/JXB/releases/download/training-v001/<文件名>`
- 文件名、大小、SHA256 见 `artifacts_manifest.json`。

使用方式：

1. 模型三件套 `best.pt` / `best.onnx` / `yolov5s_bs1.om` 下载后放入本目录 `artifacts/`（已被 .gitignore 忽略），即可按 `model_release.json` 的相对路径定位。
2. 板端推理包 `infer_project_om.tar.gz` 上传到开发板 `/home/HwHiAiUser/RobotArm/`，确认无同名工程冲突后 `tar -xzf infer_project_om.tar.gz`，再运行 `python3 om_infer.py --model=output/yolov5s_bs1.om --eval --visible`。
3. `blocks_dataset_v001.zip` 为四类积木数据集（206 图 + 标注 + 129/56/21 划分清单）；`training_records_v001.zip` 为训练记录（opt/hyp/results.csv 与曲线）。
4. `infer_project_original.tar.gz` 为原始推理工程，`session_evidence_original.ipynb` 为原始板端会话证据。

仓库只提交本目录的代码、文本记录和 Notebook；模型/数据不进入普通 Git 历史，统一走上述 Release 下载，不能只交付一个没有配套文件的 Notebook。
