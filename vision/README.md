# vision — 模型端侧部署与视觉检测(张鹏源)

对应《技术设计文档》§4.3–4.7:模型转换、检测服务(detect)、HSV 兜底、HRNet 手势识别。

## 目录结构

```
vision/
├── docs/                     # 交付文档与待确认清单
│   ├── tbd_questions.md      # 阶段0:发给队友的确认问题清单(待答复)
│   ├── model_release_record.md  # 模型版本记录模板(点验交付物之一)
│   ├── 接口样例.md           # detect/model_release 样例消息(协作规范 §二,待移入 JXB/docs/)
│   └── uplus_convert_guide.md   # 任务4:U+平台转换+板载部署操作清单(拿到模型后照做)
├── model_convert/            # 阶段1:转换链路(备用;任务4 指定走 U+平台转换)
│   ├── verify_onnx.py        #   ONNX 合法性检查(输入/输出/算子清单)
│   ├── convert_to_om.sh      #   ATC 转换脚本(U+平台不可用时在板子上执行)
│   ├── models/               #   杨泽交付的模型文件放这里(git 不跟踪大文件)
│   └── om/                   #   转换产物 .om(课程产物 yolov5s_bs1.om)
├── detect_service/           # 阶段2:检测服务(核心交付物,含 check_env.py/mock_engine.py)
├── hsv_fallback/             # 阶段4:HSV 颜色分割兜底通道
├── gesture/                  # 阶段6:HRNet 手势识别(分类器就绪,模型接入待 T5)
├── vision_loop.py            # 视觉侧闭环 demo(mock 对 mock 联调,协作规范 §四)
└── tests/                    # 单测 + 性能测试(tests/perf_test.py 生成 CSV 测试记录)
```

## 进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 对齐待定项、确认硬件环境 | 进行中:待确认清单已列于 docs/tbd_questions.md |
| 1 | 打通转换链路 | 代码就绪;课程任务4 指定走 U+平台转换(产出 yolov5s_bs1.om),ATC 脚本留作备用 |
| 2 | detect 检测服务 | 代码就绪,**13 个单测全部通过**;待板子上接真模型验证 |
| 3 | 接入正式模型、端侧 mAP 验证 | 操作手册已就绪(docs/uplus_convert_guide.md);执行依赖杨泽交付 infer_project.tar.gz |
| 4 | HSV 兜底通道 | 代码就绪,**9 个单测全部通过**;待与朱玉贺实机标定阈值(hsv_tuner) |
| 5 | 性能测试 P95 ≤ 150ms | 脚本就绪(tests/perf_test.py,假引擎自检通过);待板子上用真模型实测 |
| 6 | HRNet 手势识别 | 分类器就绪(关键点→四类手势,6 单测通过);模型接入阻塞 T5,接口提案见 docs/接口样例.md §6 |
| 7 | 联调、异常注入、交付物整理 | 未开始 |

## 环境

- 目标硬件:Atlas 200I DK A2(昇腾 310B 系列),CANN 工具链 + PyACL
- 板载环境(任务1 文档):Ubuntu 22.04 + ROS2 **Humble**,虚拟环境 `ros-arm-env`
- 课程任务4 工具链:模型适配工具(PC 标注+一键迁移)→ U+平台转换 → 200DK 推理;
  转换产物为 `yolov5s_bs1.om`,推理入口 `om_infer.py`(拿到包后以实测输出为准)
- 本目录代码在板子上运行;备用转换脚本需先 `source` CANN 环境变量
- 开发约定(PRD §四):图像原点左上角(u 右 v 下);无目标返回空数组;
  未知值用 null;默认置信度阈值 0.5;帧超 1s 未用必须重采;禁复用旧帧

## 快速验证(装依赖 → 启动,协作规范 §六)

```bash
pip install -r requirements.txt                 # 1. 装依赖(numpy + opencv)
python detect_service/demo_detect.py --mock     # 2. 无模型独立演示(固定结果,标记"模拟")
python vision_loop.py --mock --rounds 3         #    视觉闭环 demo(detect→pick_place 样例)
python tests/test_processing.py                 # 3. 开发机单测(28 个,无需板子/ACL)
python tests/perf_test.py --fake                # 性能测试脚本自检(假引擎)
```

板子上真模型路径见 detect_service/README.md。

## 协作约定(协作规范.md)

- Git:只写 vision/ 目录;分支 zpy(张鹏源),提交前缀 `feat(vision): …`;
  不直接向 main 提交;不提交临时文件与模型大文件
- 接口:detect 样例消息见 docs/接口样例.md,联调前与朱玉贺对同一份样例验证
- 模拟数据必须明确标记"模拟"(demo_detect.py --mock 会在输出前打印标记),
  不冒充实机验收结果
- 验收数字(F1):mAP@0.5 ≥ 0.75、P95 ≤ 150ms、平面定位误差 ≤ 10mm(与朱玉贺标定共同达成)
