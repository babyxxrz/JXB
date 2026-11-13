# 任务事件（朱玉贺发布, 严晨越订阅入库; 见技术设计文档 7.4）
# 约定: 相同 event_id 不重复入库; 未知值用 null 表示——ROS2 消息无 null 类型,
# 以 has_position / has_times 布尔标志区分, error_code 为空串表示无错误。
string event_id          # 事件唯一标识（幂等）
string task_id           # 任务唯一标识（相同 task_id 不重复执行）
int64 occurred_at_ms     # 事件发生时间戳, ms
string status            # queued / running / succeeded / failed / skipped / stopped
string color             # red / yellow / blue / green; 空串 = 非分拣事件（如演示动作组）
float64 x_mm             # 机械臂基坐标系抓取坐标, mm
float64 y_mm
float64 z_mm
bool has_position        # false = 坐标未知（null）, x/y/z 字段无效
int64 started_at_ms      # 任务开始时间, ms
int64 finished_at_ms     # 任务结束时间, ms
bool has_times           # false = 起止时间未知（null）
string error_code        # 空串 = 无错误; 最低错误码: LOW_CONFIDENCE / OUT_OF_WORKSPACE / CONTROL_TIMEOUT / STOP_REQUESTED
string mode              # real / fallback / simulation
string result_basis      # operator_confirmed / controller_only / none
