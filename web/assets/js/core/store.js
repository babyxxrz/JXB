// store.js — 前端内存数据仓库(单例)
// 所有页面共享同一份状态;页面通过 subscribe 订阅变更,数据统一由 api 层写入。

import { DEFAULT_CONFIG } from './config.js';

const LS_EVENTS = 'jxb.web.events.v1';
const LS_CONFIG = 'jxb.web.config.v1';
const MAX_EVENTS = 500;   // 本地保存的事件上限,防止无限增长

function loadConfig() {
  try {
    const raw = localStorage.getItem(LS_CONFIG);
    if (!raw) return structuredClone(DEFAULT_CONFIG);
    // 浅合并:新版本新增的配置项以默认值补齐
    const saved = JSON.parse(raw);
    return {
      ...structuredClone(DEFAULT_CONFIG),
      ...saved,
      workspace: { ...DEFAULT_CONFIG.workspace, ...(saved.workspace || {}) },
      bins: { ...DEFAULT_CONFIG.bins, ...(saved.bins || {}) },
    };
  } catch {
    return structuredClone(DEFAULT_CONFIG);
  }
}

function loadEvents() {
  try {
    const raw = localStorage.getItem(LS_EVENTS);
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list.slice(0, MAX_EVENTS) : [];
  } catch {
    return [];
  }
}

/** 全局状态 */
const state = {
  device: { state: 'idle' },                    // idle / running / stopping / fault
  selfCheck: { running: false, items: [], checkedAt: null },
  config: loadConfig(),                         // 参数配置
  events: loadEvents(),                         // task_event 列表,最新的在前
  demo: null,                                   // 演示动作进行中:{ action, until_ms }
};

const listeners = new Set();

/** 订阅状态变更,返回取消订阅函数 */
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getState() {
  return state;
}

/** 局部更新并通知所有订阅者 */
export function update(patch) {
  Object.assign(state, patch);
  for (const fn of listeners) fn(state);
}

/** 追加一条 task_event(最新的在前),并落盘 */
export function pushEvent(ev) {
  state.events = [ev, ...state.events].slice(0, MAX_EVENTS);
  persistEvents();
  for (const fn of listeners) fn(state);
}

function persistEvents() {
  try {
    localStorage.setItem(LS_EVENTS, JSON.stringify(state.events));
  } catch {
    /* 隐私模式等场景下静默降级为仅内存 */
  }
}

/** 保存参数配置 */
export function saveConfig(config) {
  state.config = config;
  try {
    localStorage.setItem(LS_CONFIG, JSON.stringify(config));
  } catch {
    /* 同上 */
  }
  for (const fn of listeners) fn(state);
}
