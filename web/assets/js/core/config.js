// config.js — 全局配置与常量表(与需求文档接口契约保持一致)
// 四色积木显示色经过色觉无障碍校验(红→黄→蓝→绿相邻对 ΔE ≥ 15),不得随意更换。

export const APP = {
  api: {
    // 'mock':本地模拟引擎驱动(无硬件演示用); 'real':轮询后端 HTTP 接口
    mode: 'mock',
    baseUrl: '/api',   // real 模式下的后端地址
    pollMs: 1000,      // real 模式轮询周期(≤1s,对应"事件写入至展示 ≤1s")
  },
};

/** 四类积木(类别表 red/yellow/blue/green) */
export const COLORS = ['red', 'yellow', 'blue', 'green'];

export const COLOR_META = {
  red:    { label: '红', hex: '#e34948' },
  yellow: { label: '黄', hex: '#eda100' },
  blue:   { label: '蓝', hex: '#2a78d6' },
  green:  { label: '绿', hex: '#008300' },
};

/** task_event.status 展示元数据(状态色带图标+文字,颜色不作为唯一标识) */
export const STATUS_META = {
  queued:    { label: '排队中', hex: '#c3c2b7' },
  running:   { label: '执行中', hex: '#2a78d6' },
  succeeded: { label: '成功',   hex: '#0ca30c' },
  failed:    { label: '失败',   hex: '#d03b3b' },
  skipped:   { label: '跳过',   hex: '#fab219' },
  stopped:   { label: '已停止', hex: '#898781' },
};

/** 设备整体状态(task_command 返回的 state 枚举) */
export const DEVICE_STATE_META = {
  idle:     { label: '待机',   hex: '#898781' },
  running:  { label: '运行中', hex: '#0ca30c' },
  stopping: { label: '停止中', hex: '#fab219' },
  fault:    { label: '故障',   hex: '#d03b3b' },
};

/** 最低错误码集合 */
export const ERROR_META = {
  LOW_CONFIDENCE:   { label: '置信度过低' },
  OUT_OF_WORKSPACE: { label: '超出工作区' },
  CONTROL_TIMEOUT:  { label: '控制超时' },
  STOP_REQUESTED:   { label: '收到停止请求' },
};

/** 参数配置默认值(与需求文档 8.2 配置数据一致) */
export const DEFAULT_CONFIG = {
  confidence_threshold: 0.5,        // 置信度阈值,默认 0.5
  workspace: {                       // 有效工作区,mm(拟定 ≥120×120)
    x_min: -60, x_max: 60,
    y_min: -60, y_max: 60,
  },
  grab_height_mm: 40,               // 抓取高度,mm
  bins: {                            // 四色容器中心坐标(机械臂基坐标系,mm)
    red:    { x: 160, y:  90 },
    yellow: { x: 160, y: -90 },
    blue:   { x: -160, y:  90 },
    green:  { x: -160, y: -90 },
  },
  rgb_mode: 'cycle',                 // RGB 指示灯模式:solid 常亮 / breath 呼吸 / cycle 循环 / off 关闭
  buzzer: true,                      // 蜂鸣器开关
};

export const RGB_MODES = [
  { value: 'cycle',  label: '循环变色' },
  { value: 'solid',  label: '常亮' },
  { value: 'breath', label: '呼吸' },
  { value: 'off',    label: '关闭' },
];

/** 演示动作组(技术设计 5.4) */
export const DEMO_ACTIONS = [
  { value: 'wave', label: '挥手' },
  { value: 'dance', label: '舞蹈' },
];
