# U+平台模型转换与板载部署操作手册(任务4 第 4 步)

> 用途:拿到杨泽的 `infer_project.tar.gz` 后,按本清单逐步执行。
> 来源:课程《任务4:训练积木检测模型》文档,张鹏源负责执行。
> 备用:若 U+平台不可用,退回 model_convert/convert_to_om.sh 的板载 ATC 方案。

## 前提

- [ ] 杨泽交付 `infer_project.tar.gz`(模型适配工具"一键迁移"产物)
- [ ] 有 U+平台账号和 200DK 的 SSH 访问
- [ ] 板载环境自检通过:`python detect_service/check_env.py`

## 第 1 步:U+平台转换

- [ ] 上传 `infer_project.tar.gz` 到 U+平台 `/home/` 目录
- [ ] 终端解压:`tar -xzf infer_project.tar.gz`
- [ ] 进入目录,把 Windows 格式文件转 Unix 格式(dos2unix,按课程文档执行)
- [ ] 进入解压目录执行模型转换命令(按文档/README 里的命令)
- [ ] 确认回显"转换成功",产物在 `infer_project/output/` 下,
      名称为 **`yolov5s_bs1.om`**
- [ ] 压缩整个目录:`zip -r infer_project.zip infer_project/`,下载到本地

## 第 2 步:部署到 200DK

- [ ] 上传 `infer_project.zip` 到板子 `/home/HwHiAiUser/RobotArm/`,解压
- [ ] 跑课程自带推理验证:
      `python3 om_infer.py --model=output/yolov5s_bs1.om --eval --visible`
      (带测试集标注时 `--eval` 同时给出端侧精度,对应 F1 的 mAP@0.5)
- [ ] 记录 `--eval` 输出的 mAP 数值 → 填 docs/model_release_record.md

## 第 3 步:接入我们的 detect_service

- [ ] 把 `yolov5s_bs1.om` 复制/软链到 `vision/model_convert/om/`
- [ ] 改 `detect_service/config.json`:
      - `om_path` 指向该 .om
      - `format` 改为 `"v5"`(yolov5s 导出格式,类别分已含 sigmoid)
      - `apply_sigmoid` 改为 `false`
      - `input_width/input_height` 以 .om 实际输入为准(转换配置里确认)
- [ ] 实测输出格式:课程 om_infer.py 的输出头(是否 (1,N,5+nc)、是否已 sigmoid)
      与 decode_v5 预期不符时,以实测为准改 decode,别硬套
- [ ] 单图自测:`python demo_detect.py --image 测试图.jpg` 核对契约 JSON

## 第 4 步:性能测试(F1)

- [ ] `python tests/perf_test.py --model ../model_convert/om/yolov5s_bs1.om --image 测试图.jpg`
- [ ] 确认 P95 ≤ 150ms,CSV 测试记录归档(交付物之一)

## 易错点(课程文档 + 转换经验)

1. **全英文路径**:PC 侧数据集与工具目录必须全英文,中文路径会导致工具/转换失败
2. **dos2unix 别漏**:Windows 生成的脚本文件直接上 Linux 会 `\r` 报错
3. **bs1**:转换产物带 bs1 表示 batch size=1,端侧引擎按单帧调用,与我们的
   detect 流程一致(别按多 batch 组织输入)
4. **val_map50 记录**:model_release 的 val_map50 由杨泽训练侧提供;
   端侧 `--eval` 是独立验证,两者都记进 model_release_record.md
