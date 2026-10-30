// settings.js — 参数配置页
// 维护置信度阈值、工作区与容器位置、抓取高度、RGB 灯模式与蜂鸣器开关;
// 设备非待机时禁用运动相关参数(契约:运动中禁止修改运动相关参数)。

import { init, configApi } from '../core/api.js';
import { getState, subscribe, saveConfig } from '../core/store.js';
import { renderSidebar, showToast } from '../core/ui.js';
import { APP, COLORS, RGB_MODES } from '../core/config.js';

const el = {
  confidence: document.getElementById('f-confidence'),
  rgb: document.getElementById('f-rgb'),
  buzzer: document.getElementById('f-buzzer'),
  wxmin: document.getElementById('f-wxmin'),
  wxmax: document.getElementById('f-wxmax'),
  wymin: document.getElementById('f-wymin'),
  wymax: document.getElementById('f-wymax'),
  z: document.getElementById('f-z'),
  bins: Object.fromEntries(COLORS.map((c) => [
    c,
    {
      x: document.getElementById(`f-bin-${c}-x`),
      y: document.getElementById(`f-bin-${c}-y`),
    },
  ])),
  hint: document.getElementById('workspace-hint'),
  save: document.getElementById('btn-save'),
  note: document.getElementById('save-note'),
};

/* ------------------------------ 初始化 ------------------------------ */

renderSidebar('settings');
for (const mode of RGB_MODES) {
  const opt = document.createElement('option');
  opt.value = mode.value;
  opt.textContent = mode.label;
  el.rgb.appendChild(opt);
}
el.save.addEventListener('click', onSave);

init();
if (APP.api.mode === 'real') {
  // real 模式:配置以后端为准,页面打开时拉取
  configApi
    .load()
    .then((cfg) => { fillForm(cfg); updateHint(); })
    .catch(() => showToast('无法加载后端配置', 'error'));
} else {
  loadForm();   // mock 模式:本地存储
}
subscribe((state) => lockMotion(state.device.state));

/* ------------------------------ 表单 ------------------------------ */

function loadForm() {
  fillForm(getState().config);
}

function fillForm(config) {
  el.confidence.value = config.confidence_threshold;
  el.rgb.value = config.rgb_mode;
  el.buzzer.checked = config.buzzer;
  el.wxmin.value = config.workspace.x_min;
  el.wxmax.value = config.workspace.x_max;
  el.wymin.value = config.workspace.y_min;
  el.wymax.value = config.workspace.y_max;
  el.z.value = config.grab_height_mm;
  for (const c of COLORS) {
    el.bins[c].x.value = config.bins[c].x;
    el.bins[c].y.value = config.bins[c].y;
  }
  updateHint();
}

function updateHint() {
  const w = el.wxmax.value - el.wxmin.value;
  const h = el.wymax.value - el.wymin.value;
  if (w < 120 || h < 120) {
    el.hint.textContent = `当前工作区 ${w}×${h} mm,小于验收要求(≥120×120 mm)。`;
    el.hint.className = 'form-hint warn';
  } else {
    el.hint.textContent = `当前工作区 ${w}×${h} mm,符合验收要求(≥120×120 mm)。`;
    el.hint.className = 'form-hint';
  }
}

/** 运动相关参数在设备非待机时锁定 */
function lockMotion(state) {
  const locked = state !== 'idle';
  const motionInputs = document.querySelectorAll('[data-motion] input');
  for (const input of motionInputs) input.disabled = locked;
  el.note.textContent = locked
    ? `设备当前为「${state === 'running' ? '运行中' : '停止中'}」,运动相关参数已锁定,停止任务后可修改。`
    : '';
}

function onSave() {
  const conf = Number(el.confidence.value);
  if (!(conf >= 0.05 && conf <= 1)) {
    showToast('置信度阈值需在 0.05–1 之间', 'error');
    return;
  }
  const next = {
    confidence_threshold: conf,
    rgb_mode: el.rgb.value,
    buzzer: el.buzzer.checked,
    workspace: {
      x_min: Number(el.wxmin.value),
      x_max: Number(el.wxmax.value),
      y_min: Number(el.wymin.value),
      y_max: Number(el.wymax.value),
    },
    grab_height_mm: Number(el.z.value),
    bins: Object.fromEntries(COLORS.map((c) => [
      c,
      { x: Number(el.bins[c].x.value), y: Number(el.bins[c].y.value) },
    ])),
  };
  updateHint();
  if (APP.api.mode === 'real') {
    // real 模式:保存到后端;运动中后端会拒绝(409)
    configApi
      .save(next)
      .then(() => showToast('参数已保存'))
      .catch((err) => showToast(err.message || '保存失败', 'error'));
  } else {
    saveConfig(next);
    showToast('参数已保存');
  }
}
