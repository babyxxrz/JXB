# 控制模块运行状态（朱玉贺发布, 供分拣闭环与 Web 看板使用; 对应 7.5 返回 state 语义）
string state   # idle / running / stopping / fault
bool busy      # true = 正在执行运动任务（禁止并行执行两项运动任务）
string mode    # 当前运行模式 real / fallback / simulation
