// api.js — 统一数据层
// mock 模式:由本地模拟引擎驱动(mock.js),页面无需感知数据来源;
// real 模式:轮询后端 HTTP 接口(周期 ≤1s),后端就绪后将 APP.api.mode 改为 'real' 即可。

import { APP } from './config.js';
import { getState, update, pushEvent } from './store.js';
import { createMockEngine } from './mock.js';
import { showToast } from './ui.js';

let engine = null;

/** 页面加载时调用一次,建立数据通道 */
export function init() {
  if (APP.api.mode === 'mock') {
    engine = createMockEngine();
    return;
  }
  pollReal();
  setInterval(pollReal, APP.api.pollMs);
}

/** 控制指令(task_command 契约:start / stop,返回 accepted) */
export const commands = {
  start() {
    if (APP.api.mode === 'mock') {
      if (engine.commandStart()) showToast('任务已启动');
      return;
    }
    sendCommand({ action: 'start' });
  },
  stop() {
    if (APP.api.mode === 'mock') {
      if (engine.commandStop()) showToast('已下发停止,机械臂 ≤1s 内停止派发');
      return;
    }
    sendCommand({ action: 'stop' });
  },
  selfCheck() {
    if (APP.api.mode === 'mock') {
      if (engine.commandSelfCheck()) showToast('开始开机自检');
      return;
    }
    sendCommand({ action: 'self_check' });
  },
  demo(action) {
    if (APP.api.mode === 'mock') {
      if (engine.commandDemo(action)) showToast(`已触发演示动作:${action === 'wave' ? '挥手' : '舞蹈'}`);
      return;
    }
    sendCommand({ action: 'demo', demo_action: action });
  },
};

/** 参数配置:real 模式读写后端 /api/config;mock 模式由 store 与 localStorage 管理 */
export const configApi = {
  async load() {
    const res = await fetch(`${APP.api.baseUrl}/config`);
    if (!res.ok) throw new Error(`config load failed: ${res.status}`);
    return res.json();
  },
  async save(cfg) {
    const res = await fetch(`${APP.api.baseUrl}/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail || `config save failed: ${res.status}`);
    }
  },
};

/* ------------------------------ real 模式 ------------------------------ */

async function sendCommand(body) {
  try {
    const res = await fetch(`${APP.api.baseUrl}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: crypto.randomUUID(), ...body }),
    });
    const data = await res.json();
    if (!data.accepted) showToast(`指令未接受:${data.error_code || '未知错误'}`, 'error');
  } catch {
    showToast('无法连接后端服务', 'error');
  }
}

async function pollReal() {
  try {
    const [stateRes, eventsRes] = await Promise.all([
      fetch(`${APP.api.baseUrl}/state`),
      fetch(`${APP.api.baseUrl}/events?since=${getState().events[0]?.event_id || ''}`),
    ]);
    const device = await stateRes.json();
    const events = await eventsRes.json();
    update({ device });
    // 后端按 event_id 去重,前端再兜底一次(幂等入库)
    const known = new Set(getState().events.map((e) => e.event_id));
    for (const ev of (events || []).reverse()) {
      if (!known.has(ev.event_id)) pushEvent(ev);
    }
  } catch {
    /* 轮询失败保持上一帧数据,不打扰页面 */
  }
}
