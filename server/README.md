# 记录服务(严晨越)

Web 看板的后端:task_event 幂等入库与查询、分类统计、task_command 指令下发、参数配置,并同端口托管前端页面(`../web/`)。

## 三步运行

```bash
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

浏览器打开 http://127.0.0.1:8000 (前端页面与 API 同源同端口)。

- 默认 `JXB_CONTROL=mock`:内置模拟控制适配器,启动任务后自动产生分拣事件流,无硬件即可完整演示。
- 切真实控制:`JXB_CONTROL=real`(待定项 T1/T7 确认后实现 ROS2 桥接,见 `app/control.py`)。
- 数据落盘位置:`server/data/`(可用环境变量 `JXB_DATA_DIR` 重定向,已被 .gitignore 排除)。

## API 一览(字段详见《技术设计文档》第 7 章)

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/events` | task_event 上报(朱玉贺→本服务),event_id 幂等入库 |
| GET | `/api/events` | 查询:支持 `since`(增量)/`color`/`status`/时间范围/分页 |
| GET | `/api/stats` | 分类统计:按颜色、状态汇总 + 成功率 + 平均耗时 |
| GET | `/api/state` | 设备状态(idle/running/stopping/fault) |
| POST | `/api/command` | task_command:start/stop/self_check/demo |
| GET/PUT | `/api/config` | 参数配置(契约 8.2);非待机时 PUT 返回 409 |

## 测试

```bash
cd server
python -m unittest tests.test_events tests.test_stats tests.test_flow -v   # 功能测试
python tests/latency_report.py                                             # 数据延迟测试(F3:≤1s、完整率 100%),生成 docs/数据延迟测试记录.md
```

功能测试覆盖:幂等入库、null 字段保持、筛选分页、增量拉取、20 条完整率、统计口径、启停闭环、运动中锁定配置。
