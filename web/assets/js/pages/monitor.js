// monitor.js — 运行监控页
// 展示设备状态与自检结果,提供任务启停 / 自检 / 演示动作控制,实时刷新事件流。

import { init, commands } from '../core/api.js';
import { getState, subscribe } from '../core/store.js';
import { renderSidebar, badge, fmt } from '../core/ui.js';
import {
  DEVICE_STATE_META, STATUS_META, COLOR_META, ERROR_META, DEMO_ACTIONS,
} from '../core/config.js';

const el = {
  hero: document.getElementById('hero'),
  checkList: document.getElementById('check-list'),
  checkHint: document.getElementById('check-hint'),
  btnStart: document.getElementById('btn-start'),
  btnStop: document.getElementById('btn-stop'),
  btnCheck: document.getElementById('btn-check'),
  btnDemo: document.getElementById('btn-demo'),
  demoSelect: document.getElementById('demo-select'),
  demoHint: document.getElementById('demo-hint'),
  feed: document.getElementById('feed'),
};

/* ------------------------------ 初始化 ------------------------------ */

renderSidebar('monitor');
for (const a of DEMO_ACTIONS) {
  const opt = document.createElement('option');
  opt.value = a.value;
  opt.textContent = a.label;
  el.demoSelect.appendChild(opt);
}

el.btnStart.addEventListener('click', () => commands.start());
el.btnStop.addEventListener('click', () => commands.stop());
el.btnCheck.addEventListener('click', () => commands.selfCheck());
el.btnDemo.addEventListener('click', () => {
  const action = el.demoSelect.value;
  if (action) commands.demo(action);
});

init();
render(getState());
subscribe(render);

/* ------------------------------ 渲染 ------------------------------ */

function render(state) {
  renderHero(state);
  renderSelfCheck(state);
  renderControls(state);
  renderFeed(state);
}

function renderHero(state) {
  const meta = DEVICE_STATE_META[state.device.state] || DEVICE_STATE_META.idle;
  el.hero.textContent = '';

  const left = document.createElement('div');
  left.className = 'hero-state';
  const dot = document.createElement('span');
  dot.className = 'state-dot';
  dot.style.setProperty('--dot', meta.hex);
  const name = document.createElement('span');
  name.className = 'state-name';
  name.textContent = meta.label;
  left.append(dot, name);

  const right = document.createElement('div');
  right.className = 'hero-meta';

  // 当前在途任务(最近的 queued/running 事件)
  const task = state.events.find(
    (e) => e.status === 'queued' || e.status === 'running',
  );
  if (task) {
    const cm = COLOR_META[task.color];
    const sm = STATUS_META[task.status];
    const line = document.createElement('span');
    line.className = 'hero-task';
    line.append(
      badge(`${cm.label}色积木 · ${sm.label}`, cm.hex),
      document.createTextNode(`坐标 (${fmt.coord(task)}) mm`),
    );
    right.appendChild(line);
  }

  const mode = document.createElement('span');
  mode.textContent = '演示环境 · 模拟数据(非实机验收)';
  right.appendChild(mode);
  el.hero.append(left, right);
}

function renderSelfCheck(state) {
  const { selfCheck } = state;
  el.checkList.textContent = '';

  if (selfCheck.items.length === 0) {
    const li = document.createElement('li');
    li.textContent = selfCheck.running ? '自检进行中…' : '尚未自检,启动任务或点击「开机自检」';
    el.checkList.appendChild(li);
  } else {
    for (const item of selfCheck.items) {
      const li = document.createElement('li');
      const icon = document.createElement('span');
      icon.className = `check-icon ${item.status}`;
      icon.textContent = item.status === 'ok' ? '✓' : '✕';
      const name = document.createElement('span');
      name.textContent = item.name;
      li.append(icon, name);
      el.checkList.appendChild(li);
    }
  }

  el.checkHint.textContent = selfCheck.checkedAt
    ? `最近一次自检:${fmt.timeFull(selfCheck.checkedAt)}`
    : '启动任务时自动执行自检,任一异常将禁止启动。';
}

function renderControls(state) {
  const { device, selfCheck, demo } = state;
  const busy = device.state === 'running'
    || device.state === 'stopping'
    || selfCheck.running;

  el.btnStart.disabled = busy;
  el.btnStop.disabled = !(device.state === 'running' || selfCheck.running);
  el.btnCheck.disabled = busy;
  el.btnDemo.disabled = busy || !!demo;

  if (demo) {
    el.demoHint.textContent = '演示动作执行中…';
  } else {
    el.demoHint.textContent = '演示动作仅用于联调展示(挥手 / 舞蹈),不产生分拣任务事件。';
  }
}

function renderFeed(state) {
  el.feed.textContent = '';
  const recent = state.events.slice(0, 8);
  if (recent.length === 0) {
    const li = document.createElement('li');
    li.textContent = '暂无事件,启动任务后事件将在此实时刷新。';
    li.style.color = 'var(--ink-3)';
    el.feed.appendChild(li);
    return;
  }
  for (const ev of recent) {
    const li = document.createElement('li');
    const time = document.createElement('span');
    time.className = 'feed-time';
    time.textContent = fmt.time(ev.occurred_at_ms);
    const color = document.createElement('span');
    color.className = 'feed-color';
    color.appendChild(badge(COLOR_META[ev.color]?.label || ev.color, COLOR_META[ev.color]?.hex || '#898781'));
    const task = document.createElement('span');
    task.className = 'feed-task';
    task.textContent = ev.task_id;
    const status = document.createElement('span');
    const sm = STATUS_META[ev.status] || { label: ev.status, hex: '#898781' };
    status.appendChild(badge(sm.label, sm.hex));
    const coord = document.createElement('span');
    coord.className = 'feed-coord';
    coord.textContent = `(${fmt.coord(ev)}) mm`;
    li.append(time, color, task, status, coord);
    if (ev.error_code) {
      const err = document.createElement('span');
      err.className = 'feed-err';
      err.textContent = ERROR_META[ev.error_code]?.label || ev.error_code;
      li.appendChild(err);
    }
    el.feed.appendChild(li);
  }
}
