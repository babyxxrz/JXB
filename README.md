# JXB — 基于计算机视觉的智能机械臂垃圾分拣与管理系统

课程项目(软件开发与测试综合实践)。四种颜色积木模拟垃圾分类对象,Atlas 200I DK A2 视觉推理 + ROS2 / Arm_Lib 机械臂控制,完成「检测 → 定位 → 抓取 → 分类放置 → 记录」闭环。操作人员通过 Web 看板启停任务、查看状态与分拣记录。

**协作约定见 [docs/协作规范.md](docs/协作规范.md),接口样例消息见 [docs/接口样例.md](docs/接口样例.md)。**

## 目录结构

```
JXB/
├── docs/          # 公共文档:协作规范、接口样例、演示流程、延迟测试记录
├── web/           # Web 看板前端(严晨越):4 个页面,零依赖零构建
├── server/        # 记录服务后端(严晨越):FastAPI + SQLite
├── vision/        # 视觉:数据采集标注、模型训练与端侧部署(杨泽 / 张鹏源)
└── control/       # 控制:标定与机械臂控制(朱玉贺)
```

## 快速启动(记录服务 + Web 看板,三步)

```bash
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

浏览器打开 http://127.0.0.1:8000 —— 默认模拟控制模式,点「启动任务」即可看到完整分拣事件流,无需硬件。

- 仅看前端:`web/start.bat`(静态服务器)
- 前端数据源:`web/assets/js/core/config.js` 中 `api.mode`(`mock` 本地模拟 / `real` 对接后端)
- 详细说明与 API 一览:[server/README.md](server/README.md)
- 演示脚本:[docs/Web看板演示流程.md](docs/Web看板演示流程.md)

## 验收对照

- F3(严晨越):4 个页面、事件写入至展示 ≤1s、20 条记录完整率 100% —— 测试:`cd server && python -m unittest tests.test_events tests.test_stats tests.test_flow -v` 与 `python tests/latency_report.py`
- F1 / F2 见《技术设计文档》附录 A。
