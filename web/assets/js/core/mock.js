// mock.js — 本地模拟引擎(演示模式)
// 在无真实硬件/后端时,按 task_event / task_command 接口契约模拟:
// 设备状态机、开机自检、串行分拣事件流、停止与异常处理。
// 模拟数据仅在演示模式下使用,页面顶部徽章已明确标注"模拟数据"。

import { COLORS, ERROR_META } from './config.js';
import { getState, update, pushEvent } from './store.js';

const ERRORS = Object.keys(ERROR_META);

let timers = [];

function later(fn, ms) {
  const t = setTimeout(() => {
    timers = timers.filter((x) => x !== t);
    fn();
  }, ms);
  timers.push(t);
}

function randBetween(a, b) {
  return Math.round((a + Math.random() * (b - a)) * 10) / 10;
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

/** 从已持久化的事件中恢复任务序号,保证 task_id 不重复 */
function nextSeq() {
  let max = 0;
  for (const ev of getState().events) {
    const m = /^T(\d+)$/.exec(ev.task_id || '');
    if (m) max = Math.max(max, Number(m[1]));
  }
  return max + 1;
}

export function createMockEngine() {
  let seq = nextSeq();
  let running = false;          // 分拣循环是否进行中
  let selfChecking = false;     // 自检是否进行中
  let currentTask = null;       // 当前在途任务:{ taskId, terminal }

  /** 生成一条事件并入库(最新的在前,event_id 唯一、幂等) */
  function emit(taskId, suffix, fields) {
    pushEvent({
      event_id: `${taskId}-${suffix}`,
      task_id: taskId,
      occurred_at_ms: Date.now(),
      status: 'queued',
      color: 'red',
      x_mm: null, y_mm: null, z_mm: null,
      started_at_ms: null, finished_at_ms: null,
      error_code: null, mode: 'real', result_basis: 'none',
      ...fields,
    });
  }

  /** 停止:立即停止派发新动作,在途任务记为 stopped,≤1s 回到待机 */
  function commandStop() {
    const { device, selfCheck } = getState();
    if (device.state !== 'running' && !selfCheck.running) return false;

    // 自检阶段被停止:直接终止自检
    selfChecking = false;
    if (currentTask && !currentTask.terminal) {
      currentTask.terminal = true;
      const now = Date.now();
      emit(currentTask.taskId, 'stop', {
        status: 'stopped',
        occurred_at_ms: now,
        finished_at_ms: now,
        error_code: 'STOP_REQUESTED',
      });
    }
    running = false;
    currentTask = null;
    update({
      device: { state: 'stopping' },
      selfCheck: { ...selfCheck, running: false },
    });
    later(() => {
      update({ device: { state: 'idle' } });
    }, 700);   // ≤1s,对应验收指标"停止请求 ≤1s"
    return true;
  }

  /** 开机自检:舵机位置 / RGB 灯 / 蜂鸣器 三项依次通过 */
  function commandSelfCheck() {
    const { device, selfCheck } = getState();
    if (selfCheck.running || device.state !== 'idle') return false;

    selfChecking = true;
    update({
      selfCheck: { running: true, items: [], checkedAt: null },
    });
    const items = ['舵机位置', 'RGB 灯', '蜂鸣器'];
    items.forEach((name, i) => {
      later(() => {
        if (!selfChecking) return;
        const s = getState().selfCheck;
        const next = [...s.items, { name, status: 'ok' }];
        update({
          selfCheck: {
            ...s,
            items: next,
            running: i < items.length - 1,
            checkedAt: i === items.length - 1 ? Date.now() : null,
          },
        });
        if (i === items.length - 1) selfChecking = false;
      }, 450 * (i + 1));
    });
    return true;
  }

  /** 启动任务:自检通过后进入 running,再开始串行分拣 */
  function commandStart() {
    const { device, selfCheck } = getState();
    if (device.state !== 'idle' || selfCheck.running) return false;

    selfChecking = true;
    update({ selfCheck: { running: true, items: [], checkedAt: null } });
    const items = ['舵机位置', 'RGB 灯', '蜂鸣器'];
    items.forEach((name, i) => {
      later(() => {
        if (!selfChecking) return;
        const s = getState().selfCheck;
        update({
          selfCheck: {
            ...s,
            items: [...s.items, { name, status: 'ok' }],
            running: i < items.length - 1,
            checkedAt: i === items.length - 1 ? Date.now() : null,
          },
        });
        if (i === items.length - 1) {
          selfChecking = false;
          running = true;
          update({ device: { state: 'running' } });
          later(nextPick, 800);   // 自检通过后开始派发
        }
      }, 450 * (i + 1));
    });
    return true;
  }

  /** 单次分拣闭环:排队 → 执行 → 终态(串行,任务完成后才派发下一次) */
  function nextPick() {
    if (!running) return;
    const { config } = getState();
    const color = pick(COLORS);
    const taskId = `T${String(seq++).padStart(3, '0')}`;
    const { x_min, x_max, y_min, y_max } = config.workspace;
    const x_mm = randBetween(x_min, x_max);
    const y_mm = randBetween(y_min, y_max);
    const z_mm = config.grab_height_mm;
    currentTask = { taskId, terminal: false };

    emit(taskId, 'queued', {
      status: 'queued', color, x_mm, y_mm, z_mm,
    });

    later(() => {
      if (!running || !currentTask || currentTask.taskId !== taskId) return;
      const startedAt = Date.now();
      emit(taskId, 'run', {
        status: 'running', color, x_mm, y_mm, z_mm,
        occurred_at_ms: startedAt, started_at_ms: startedAt,
      });

      later(() => {
        if (!running || !currentTask || currentTask.taskId !== taskId) return;
        currentTask.terminal = true;
        const r = Math.random();
        let status, mode = 'real', error_code = null;
        if (r < 0.78) {
          status = 'succeeded';
        } else if (r < 0.88) {
          status = 'failed';
          error_code = pick(ERRORS);
        } else if (r < 0.95) {
          status = 'skipped';         // 低置信度 → HSV 兜底仍失败
          mode = 'fallback';
          error_code = 'LOW_CONFIDENCE';
        } else {
          status = 'succeeded';       // HSV 兜底定位成功
          mode = 'fallback';
        }
        // 控制超时任务耗时 >20s,与验收指标"单次 ≤20s 完成或报告失败"一致
        const durationMs = error_code === 'CONTROL_TIMEOUT'
          ? 20500 + Math.random() * 4000
          : 900 + Math.random() * 1200;
        const finishedAt = Date.now();
        const startedForRecord = error_code === 'CONTROL_TIMEOUT'
          ? finishedAt - durationMs
          : startedAt;
        emit(taskId, 'end', {
          status, color, x_mm, y_mm, z_mm,
          occurred_at_ms: finishedAt, finished_at_ms: finishedAt,
          started_at_ms: startedForRecord, error_code, mode,
          result_basis: status === 'succeeded' ? 'controller_only' : 'none',
        });
        currentTask = null;
        if (running) later(nextPick, 600 + Math.random() * 900);
      }, 900 + Math.random() * 1200);
    }, 700 + Math.random() * 900);
  }

  /** 演示动作(挥手/舞蹈):仅演示,不产生分拣任务事件 */
  function commandDemo(action) {
    const { device, demo } = getState();
    if (device.state !== 'idle' || demo) return false;
    update({ demo: { action, until_ms: Date.now() + 1800 } });
    later(() => {
      update({ demo: null });
    }, 1800);
    return true;
  }

  return {
    commandStart,
    commandStop,
    commandSelfCheck,
    commandDemo,
    destroy() {
      running = false;
      selfChecking = false;
      currentTask = null;
      timers.forEach(clearTimeout);
      timers = [];
    },
  };
}
