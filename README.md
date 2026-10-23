# JXB — 基于计算机视觉的智能机械臂垃圾分拣与管理系统

课程项目(软件开发与测试综合实践)。四种颜色积木模拟垃圾分类对象,Atlas 200I DK A2 视觉推理 + ROS2 / Arm_Lib 机械臂控制,完成「检测 → 定位 → 抓取 → 分类放置 → 记录」闭环。操作人员通过 Web 看板启停任务、查看状态与分拣记录。

## 目录结构

```
JXB/
├── README.md
└── web/                      # Web 看板(记录服务前端,严晨越)
    ├── index.html            # 运行监控(首页)
    ├── start.bat             # 一键启动本地演示
    ├── pages/                # 任务记录 / 分类统计 / 参数配置
    └── assets/
        ├── css/              # base.css(设计令牌与通用组件)+ pages.css(页面样式)
        └── js/
            ├── core/         # config 配置常量 / store 数据仓库 / ui 通用 UI
            │                 # mock 模拟引擎 / api 统一数据层
            └── pages/        # 四个页面的逻辑,与 HTML 一一对应
```

## Web 看板说明

- 技术栈:原生 HTML + CSS + JS(ES Modules),零依赖、零构建。
- 四个页面:运行监控、任务记录、分类统计、参数配置(对应需求文档验收指标 F3)。
- 数据模式:默认 `mock`(`assets/js/core/config.js` 中 `api.mode`),由本地模拟引擎按接口契约
  生成 task_event 事件流与设备状态,便于无硬件演示;后端就绪后改为 `real` 即轮询 HTTP 接口。

## 运行

双击 `web/start.bat`(需要本机装有 Python 3),或手动执行:

```bash
python -m http.server 8000
```

浏览器打开 http://127.0.0.1:8000 。
