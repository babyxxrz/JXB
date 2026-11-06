# ros2_dofbot_ws — 基于计算机视觉的智能机械臂垃圾分拣与管理系统

小组课程实训项目工作区（ROS 2 Humble，运行于 Atlas 200I DK A2 板卡）。
设计依据：《产品需求文档 V0.1》《技术设计文档 V0.1》（本组）。

## 分工与模块

| 成员 | 模块 | 代码位置 |
|---|---|---|
| 杨泽 | 数据采集标注与模型训练 | （模型产物, 不在本工作区） |
| 张鹏源 | 模型端侧部署与视觉检测（detect 接口） | （Atlas 推理侧） |
| **朱玉贺** | **标定与机械臂控制** | `src/dofbot_info`、`src/dofbot_moveit`、`src/dofbot_control`、`docs/` |
| 严晨越 | 记录服务与 Web 看板 | （看板工程） |

## 工作区结构

```
ros2_dofbot_ws/
├── src/
│   ├── dofbot_info/      # 接口功能包: 任务2 正逆解服务 + 分拣业务消息/服务定义
│   ├── dofbot_moveit/    # 任务2 功能包: 正逆解服务器(dofbot_server) + URDF + RViz 仿真
│   └── dofbot_control/   # 控制模块(朱玉贺): 控制服务/分拣闭环/标定工具/验收测试
├── docs/                 # 标定与坐标说明、联调说明、实机分拣记录模板
├── build/ install/ log/  # colcon 产物(gitignore)
└── setenv.h              # 板卡环境初始化(conda + ROS + 依赖路径)
```

## 控制模块快速上手（朱玉贺）

### 1. 在板卡上编译

```bash
cd /home/HwHiAiUser/RobotArm/ros2_dofbot_ws
colcon build --symlink-install
source install/setup.bash
```

### 2. 仿真联调（不接硬件, 默认驱动模式 auto 会自动降级仿真）

```bash
# 终端 A: 启动 正逆解服务 + 控制服务 + 分拣闭环
# 联调严晨越记录服务时加 with_event_bridge:=true(先改 config 的 server.url)
ros2 launch dofbot_control dofbot_control.launch.py

# 终端 B: 启动任务(含开机自检)
ros2 run dofbot_control task_command_client start

# 终端 C: 发布仿真检测帧, 观察分拣闭环
ros2 run dofbot_control fake_detect --points "red,320,240;blue,260,240;green,380,200"

# 终端 D: 查看事件(ROS2 话题) / 事件桥接上报到记录服务 /api/events
ros2 topic echo /task_event
```

### 3. F2 验收测试（10 次分拣记录 + F4 故障注入）

```bash
ros2 run dofbot_control task_command_client start   # 或由 f2_test 自动 start
ros2 run dofbot_control f2_test --runs 10 --random  # 10 次分拣, 输出 CSV 判定 F2
ros2 run dofbot_control f2_test --inject low_conf   # F4 注入: 低置信度 x3
ros2 run dofbot_control f2_test --inject out_ws     # F4 注入: 越界坐标 x3
ros2 run dofbot_control f2_test --inject stop       # F4 注入: 运动中停止 x3
```

记录输出到 `./f2_records/`（UTF-8 CSV, 可直接粘贴到实机分拣记录表）。

### 4. 演示动作组（5.4）

```bash
# 方式一: task_command demo 指令(接口样例, 看板同款; 需 idle 状态)
ros2 run dofbot_control task_command_client self_check          # 仅自检
ros2 run dofbot_control task_command_client demo --demo-action wave
ros2 run dofbot_control task_command_client demo --demo-action dance

# 方式二: 直接调 play_action_group 服务(固定点位搬运/堆叠联调用)
ros2 run dofbot_control task_command_client start               # 动作组允许在 idle/running 状态执行
ros2 service call /play_action_group dofbot_info/srv/PlayActionGroup "{group_name: 'nature_transport', repeat: 0}"
ros2 service call /play_action_group dofbot_info/srv/PlayActionGroup "{group_name: 'stack_blocks', repeat: 0}"
```

### 5. 实机模式（Arm_Lib）

1. 把 `dofbot_config.yaml` 中 `driver.mode` 设为 `auto`（缺省）或 `arm_lib`，
   `driver.port` 改为实际串口。
2. 完成手眼标定（见 [docs/标定与坐标说明.md](docs/标定与坐标说明.md)），
   将 `calibration.file` 指向实测标定文件。
3. 实机确认 `workspace` 边界、`bins` 容器位置与抓取高度、`robot` 夹爪角度。
4. 实机运行时用 `f2_test --listen --duration 600` 记录事件（检测帧由张鹏源的
   检测接口发布）。

## 详细文档

- [docs/控制模块联调说明.md](docs/控制模块联调说明.md) — 话题/服务契约、状态机、错误码（给张鹏源/严晨越）
- [docs/标定与坐标说明.md](docs/标定与坐标说明.md) — 坐标系定义与标定流程
- [docs/实机分拣记录模板.md](docs/实机分拣记录模板.md) — 10 次实机分拣记录表与 F2/F4 验收方法

## 待定项（回填技术设计文档第 11 章后同步更新）

- T2 detect 接口手势字段扩展（张鹏源/朱玉贺）
- T3 手势-颜色映射（配置 `gesture_color_map` 已预留）
- T11 标定方法（当前实现: 9 点平面单应, 见标定文档）
- T12 跨模块时钟源（当前使用系统时钟）
