// stats.js — 分类统计页
// KPI 汇总 + 三张图:各颜色分拣结果、任务状态分布、最近任务耗时。
// 图表规范:状态色固定语义(成功/失败等)、标记间留 2px 表面间隙、
// 悬停提示与图例带文字标签,颜色不作为唯一标识。

import { init } from '../core/api.js';
import { getState, subscribe } from '../core/store.js';
import { renderSidebar, fmt } from '../core/ui.js';
import { COLORS, COLOR_META, STATUS_META } from '../core/config.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const INK_2 = '#52514e';
const INK_3 = '#898781';
const GRID = '#e1e0d9';
const BASELINE = '#c3c2b7';
const SURFACE = '#fcfcfb';
const GOOD = '#0ca30c';
const CRITICAL = '#d03b3b';
const BLUE = '#2a78d6';

const TIME_LIMIT_S = 20;           // 单次任务 20s 验收上限
const MAX_DURATION_TASKS = 12;     // 耗时图最多展示最近 12 次任务

const el = {
  range: document.getElementById('time-range'),
  kpi: document.getElementById('kpi-row'),
  colors: document.getElementById('chart-colors'),
  legendColors: document.getElementById('legend-colors'),
  status: document.getElementById('chart-status'),
  legendStatus: document.getElementById('legend-status'),
  duration: document.getElementById('chart-duration'),
};

/* ------------------------------ 工具 ------------------------------ */

function svgEl(name, attrs = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

function svgText(x, y, text, { anchor = 'start', size = 12, fill = INK_3, weight = 'normal' } = {}) {
  const t = svgEl('text', {
    x, y, 'text-anchor': anchor,
    'font-size': size, fill, 'font-weight': weight,
    'font-family': 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif',
  });
  t.textContent = text;   // 文案一律 textContent
  return t;
}

/** 为一个标记(rect/circle)挂上悬停提示与键盘焦点提示 */
function attachTip(chartBody, hit, build) {
  const tip = document.createElement('div');
  tip.className = 'chart-tip';
  tip.hidden = true;
  chartBody.appendChild(tip);

  function show(evt) {
    const rows = build();
    tip.textContent = '';
    const value = document.createElement('div');
    value.className = 'tip-value';
    value.textContent = rows.value;
    tip.appendChild(value);
    for (const row of rows.rows) {
      const r = document.createElement('div');
      r.className = 'tip-row';
      const key = document.createElement('span');
      key.className = 'tip-key';
      key.style.background = row.hex;
      const name = document.createElement('span');
      name.className = 'tip-name';
      name.textContent = row.name;
      const text = document.createElement('span');
      text.textContent = row.text;
      r.append(key, name, text);
      tip.appendChild(r);
    }
    tip.hidden = false;
    // 跟随指针,靠近视口边缘时翻转
    const pad = 14;
    const rect = tip.getBoundingClientRect();
    let x = evt.clientX + pad;
    let y = evt.clientY + pad;
    if (x + rect.width > window.innerWidth - 8) x = evt.clientX - rect.width - pad;
    if (y + rect.height > window.innerHeight - 8) y = evt.clientY - rect.height - pad;
    tip.style.left = `${Math.max(4, x)}px`;
    tip.style.top = `${Math.max(4, y)}px`;
  }
  function hide() { tip.hidden = true; }

  hit.addEventListener('pointerenter', show);
  hit.addEventListener('pointermove', show);
  hit.addEventListener('pointerleave', hide);
  hit.addEventListener('focus', (e) => show(e));
  hit.addEventListener('blur', hide);
  hit.setAttribute('tabindex', '0');
  hit.setAttribute('role', 'img');
}

function emptyHint(body, text) {
  const div = document.createElement('div');
  div.className = 'chart-empty';
  div.textContent = text;
  body.appendChild(div);
}

/** 带淡入的图表重绘:先保持上一帧降低透明度,避免闪烁 */
function redraw(body, draw) {
  body.style.opacity = '0.55';
  setTimeout(() => {
    body.textContent = '';
    draw();
    body.style.opacity = '1';
  }, 60);
}

/* ------------------------------ 数据 ------------------------------ */

function inRange() {
  const ms = Number(el.range.value);
  const now = Date.now();
  return (ev) => (ms === 0 || ev.occurred_at_ms >= now - ms);
}

function filteredEvents() {
  const ok = inRange();
  return getState().events.filter(ok);
}

/** 终端状态(任务已结束) */
function isTerminal(ev) {
  return ev.status === 'succeeded' || ev.status === 'failed'
    || ev.status === 'skipped' || ev.status === 'stopped';
}

/* ------------------------------ KPI ------------------------------ */

function renderKpi() {
  const events = filteredEvents();
  const tasks = new Set(events.map((e) => e.task_id)).size;
  const succeeded = events.filter((e) => e.status === 'succeeded').length;
  const failed = events.filter((e) => e.status === 'failed').length;
  const rate = tasks > 0 ? succeeded / tasks : null;

  const durations = events
    .filter(isTerminal)
    .filter((e) => e.started_at_ms != null && e.finished_at_ms != null)
    .map((e) => e.finished_at_ms - e.started_at_ms);
  const avg = durations.length
    ? durations.reduce((a, b) => a + b, 0) / durations.length / 1000
    : null;

  const tiles = [
    { label: '总任务数', value: String(tasks) },
    { label: '成功', value: String(succeeded) },
    { label: '失败', value: String(failed) },
    {
      label: '成功率',
      value: rate == null ? '—' : `${Math.round(rate * 100)}%`,
      cls: rate != null && rate >= 0.8 ? 'good' : '',
      sub: '验收目标 ≥ 80%',
    },
    {
      label: '平均耗时',
      value: avg == null ? '—' : `${avg.toFixed(1)} s`,
      cls: avg != null && avg > TIME_LIMIT_S ? 'bad' : '',
      sub: `验收上限 ${TIME_LIMIT_S}s`,
    },
  ];

  el.kpi.textContent = '';
  for (const t of tiles) {
    const card = document.createElement('div');
    card.className = 'kpi';
    const label = document.createElement('div');
    label.className = 'kpi-label';
    label.textContent = t.label;
    const value = document.createElement('div');
    value.className = 'kpi-value' + (t.cls ? ` ${t.cls}` : '');
    value.textContent = t.value;
    card.append(label, value);
    if (t.sub) {
      const sub = document.createElement('div');
      sub.className = 'kpi-sub';
      sub.textContent = t.sub;
      card.appendChild(sub);
    }
    el.kpi.appendChild(card);
  }
}

/* ------------------------------ 图 1:各颜色分拣结果 ------------------------------ */

function renderColors() {
  const events = filteredEvents();
  const data = COLORS.map((color) => ({
    color,
    meta: COLOR_META[color],
    success: events.filter((e) => e.color === color && e.status === 'succeeded').length,
    fail: events.filter((e) => e.color === color && e.status === 'failed').length,
  }));
  const totals = data.map((d) => d.success + d.fail);
  const maxTotal = Math.max(1, ...totals);

  el.legendColors.textContent = '';
  const totalS = data.reduce((a, d) => a + d.success, 0);
  const totalF = data.reduce((a, d) => a + d.fail, 0);
  for (const [label, hex, count] of [['成功', GOOD, totalS], ['失败', CRITICAL, totalF]]) {
    const item = document.createElement('span');
    item.className = 'legend-item';
    const key = document.createElement('span');
    key.className = 'legend-key';
    key.style.background = hex;
    const name = document.createElement('span');
    name.textContent = label;
    const n = document.createElement('span');
    n.className = 'legend-count';
    n.textContent = String(count);
    item.append(key, name, n);
    el.legendColors.appendChild(item);
  }

  if (totals.every((t) => t === 0)) {
    el.colors.textContent = '';
    emptyHint(el.colors, '当前时间范围内暂无分拣记录');
    return;
  }

  const W = 760, x0 = 100, plotW = 520, barH = 22, rowH = 36, top = 16;
  const H = top + rowH * data.length + 6;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, 'aria-label': '各颜色分拣结果堆积条形图' });
  svg.setAttribute('role', 'img');

  // 网格线(发丝线,一档灰)与基线
  for (const pct of [0.25, 0.5, 0.75, 1]) {
    const x = x0 + plotW * pct;
    svg.appendChild(svgEl('line', { x1: x, y1: top - 8, x2: x, y2: top + rowH * (data.length - 1) + barH, stroke: GRID, 'stroke-width': 1 }));
  }
  svg.appendChild(svgEl('line', { x1: x0, y1: top - 8, x2: x0, y2: top + rowH * (data.length - 1) + barH, stroke: BASELINE, 'stroke-width': 1 }));

  data.forEach((d, i) => {
    const y = top + rowH * i;
    // 行标签:色点图标 + 文字(颜色不单独承载语义)
    svg.appendChild(svgEl('circle', { cx: 12, cy: y + barH / 2, r: 5, fill: d.meta.hex }));
    svg.appendChild(svgText(26, y + barH / 2 + 4, `${d.meta.label}色积木`, { size: 13, fill: INK_2 }));

    const sW = (d.success / maxTotal) * plotW;
    const fW = (d.fail / maxTotal) * plotW;
    const segs = [];
    if (d.success > 0) segs.push({ hex: GOOD, x: x0, w: d.fail > 0 ? sW - 1 : sW, label: '成功', count: d.success });
    if (d.fail > 0) segs.push({ hex: CRITICAL, x: x0 + sW + 1, w: fW - 1, label: '失败', count: d.fail });

    // 2px 表面间隙由相邻段间留白实现;仅最右段做 4px 圆角数据端,基线端为直角
    segs.forEach((seg, j) => {
      const isLast = j === segs.length - 1;
      const rect = svgEl('rect', {
        x: seg.x, y, width: Math.max(0, seg.w), height: barH,
        fill: seg.hex, rx: isLast ? 4 : 0,
      });
      svg.appendChild(rect);
      // 命中区 ≥24px(条高 22 + 上下各 3),悬停与键盘焦点均可读值
      const hit = svgEl('rect', {
        x: seg.x - 1, y: y - 3, width: Math.max(24, seg.w + 2), height: barH + 6,
        fill: 'transparent',
      });
      attachTip(el.colors, hit, () => ({
        value: `${seg.label} ${seg.count} 个`,
        rows: [{ hex: seg.hex, name: d.meta.label + '色积木', text: '' }],
      }));
      svg.appendChild(hit);
    });

    // 数值标签置于条形末端外侧(总数)
    svg.appendChild(svgText(x0 + plotW + 12, y + barH / 2 + 4, String(d.success + d.fail), { size: 13, fill: INK_2, weight: '600' }));
  });

  el.colors.appendChild(svg);
}

/* ------------------------------ 图 2:任务状态分布 ------------------------------ */

function renderStatus() {
  const events = filteredEvents();
  const counts = Object.keys(STATUS_META).map((key) => ({
    key, meta: STATUS_META[key], count: events.filter((e) => e.status === key).length,
  }));
  const total = counts.reduce((a, c) => a + c.count, 0);

  el.legendStatus.textContent = '';
  for (const c of counts) {
    const item = document.createElement('span');
    item.className = 'legend-item';
    const key = document.createElement('span');
    key.className = 'legend-key';
    key.style.background = c.meta.hex;
    const name = document.createElement('span');
    name.textContent = c.meta.label;
    const n = document.createElement('span');
    n.className = 'legend-count';
    n.textContent = String(c.count);
    item.append(key, name, n);
    el.legendStatus.appendChild(item);
  }

  if (total === 0) {
    el.status.textContent = '';
    emptyHint(el.status, '当前时间范围内暂无任务事件');
    return;
  }

  const W = 760, x0 = 100, plotW = 560, barH = 22, y = 24;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} 96`, 'aria-label': '任务状态分布堆积条形图' });
  svg.setAttribute('role', 'img');

  svg.appendChild(svgEl('line', { x1: x0, y1: y - 8, x2: x0, y2: y + barH + 8, stroke: BASELINE, 'stroke-width': 1 }));

  let cursor = x0;
  const nonZero = counts.filter((c) => c.count > 0);
  nonZero.forEach((c, j) => {
    const w = (c.count / total) * plotW - (j < nonZero.length - 1 ? 1 : 0);
    const rect = svgEl('rect', {
      x: cursor, y, width: Math.max(0, w), height: barH,
      fill: c.meta.hex, rx: j === nonZero.length - 1 ? 4 : 0,
    });
    svg.appendChild(rect);
    const hit = svgEl('rect', {
      x: cursor - 1, y: y - 3, width: Math.max(24, w + 2), height: barH + 6,
      fill: 'transparent',
    });
    const share = ((c.count / total) * 100).toFixed(1);
    attachTip(el.status, hit, () => ({
      value: `${c.meta.label} ${c.count} 次`,
      rows: [{ hex: c.meta.hex, name: `占比 ${share}%`, text: '' }],
    }));
    svg.appendChild(hit);
    cursor += w + 1;   // 2px 表面间隙
  });

  // 末端总数标签
  svg.appendChild(svgText(cursor + 12, y + barH / 2 + 4, String(total), { size: 13, fill: INK_2, weight: '600' }));

  el.status.appendChild(svg);
}

/* ------------------------------ 图 3:最近任务耗时 ------------------------------ */

function renderDuration() {
  const events = filteredEvents()
    .filter(isTerminal)
    .filter((e) => e.started_at_ms != null && e.finished_at_ms != null)
    .slice(0, MAX_DURATION_TASKS)
    .reverse();   // 按时间正序绘制

  if (events.length < 1) {
    el.duration.textContent = '';
    emptyHint(el.duration, '当前时间范围内暂无已完成任务');
    return;
  }

  const durations = events.map((e) => (e.finished_at_ms - e.started_at_ms) / 1000);
  const maxY = Math.max(TIME_LIMIT_S + 5, Math.ceil(Math.max(...durations) / 5) * 5);
  const W = 760, left = 46, right = 724, top = 12, plotH = 180;
  const bottom = top + plotH;
  const xAt = (i) => (events.length === 1 ? (left + right) / 2 : left + (i / (events.length - 1)) * (right - left));
  const yAt = (v) => bottom - (v / maxY) * plotH;

  const svg = svgEl('svg', { viewBox: `0 0 ${W} 252`, 'aria-label': '最近任务单次耗时折线图' });
  svg.setAttribute('role', 'img');

  // Y 轴刻度与网格线
  for (let v = 0; v <= maxY; v += 5) {
    const y = yAt(v);
    svg.appendChild(svgEl('line', { x1: left, y1: y, x2: right, y2: y, stroke: GRID, 'stroke-width': 1 }));
    svg.appendChild(svgText(left - 8, y + 4, `${v}s`, { anchor: 'end', size: 12 }));
  }
  svg.appendChild(svgEl('line', { x1: left, y1: top, x2: left, y2: bottom, stroke: BASELINE, 'stroke-width': 1 }));

  // 20s 验收上限参考线(实线发丝,状态色只用于"上限"这一语义)
  const limitY = yAt(TIME_LIMIT_S);
  svg.appendChild(svgEl('line', { x1: left, y1: limitY, x2: right, y2: limitY, stroke: CRITICAL, 'stroke-width': 1 }));
  svg.appendChild(svgText(right, limitY - 5, `${TIME_LIMIT_S}s 上限`, { anchor: 'end', size: 11 }));

  // 折线:单序列,蓝色 2px,圆角连接
  const points = events.map((e, i) => [xAt(i), yAt(durations[i])]);
  const polyline = svgEl('polyline', {
    points: points.map((p) => p.join(',')).join(' '),
    fill: 'none', stroke: BLUE, 'stroke-width': 2,
    'stroke-linecap': 'round', 'stroke-linejoin': 'round',
  });
  svg.appendChild(polyline);

  // 数据点:8px 圆点 + 2px 表面色圆环(跨线/重叠时保持可辨)
  const statusHex = (st) => STATUS_META[st]?.hex || '#898781';
  points.forEach(([x, y], i) => {
    const ev = events[i];
    const hex = statusHex(ev.status);
    svg.appendChild(svgEl('circle', { cx: x, cy: y, r: 4, fill: hex, stroke: SURFACE, 'stroke-width': 2 }));
    // 命中区 24px 透明圆,比标记大得多
    const hit = svgEl('circle', { cx: x, cy: y, r: 12, fill: 'transparent' });
    const cm = COLOR_META[ev.color];
    const sm = STATUS_META[ev.status];
    attachTip(el.duration, hit, () => ({
      value: `${durations[i].toFixed(1)} s`,
      rows: [
        { hex, name: `${sm.label} · ${cm.label}色`, text: '' },
        { hex, name: ev.task_id, text: fmt.time(ev.occurred_at_ms) },
      ],
    }));
    svg.appendChild(hit);
  });

  // 末端数值标签(仅最后一个点)
  const [lx, ly] = points[points.length - 1];
  svg.appendChild(svgText(lx + 8, ly - 8, `${durations[durations.length - 1].toFixed(1)}s`, { size: 12, fill: INK_2, weight: '600' }));

  // X 轴首尾时间标签
  svg.appendChild(svgText(left, bottom + 22, fmt.time(events[0].occurred_at_ms), { size: 12 }));
  svg.appendChild(svgText(right, bottom + 22, fmt.time(events[events.length - 1].occurred_at_ms), { anchor: 'end', size: 12 }));

  // 十字准线:悬停绘图区时吸附最近数据点
  const crosshair = svgEl('line', { x1: 0, y1: top, x2: 0, y2: bottom, stroke: BASELINE, 'stroke-width': 1, visibility: 'hidden' });
  svg.appendChild(crosshair);
  const plotHit = svgEl('rect', { x: left, y: top, width: right - left, height: plotH, fill: 'transparent' });
  plotHit.addEventListener('pointermove', (evt) => {
    const rect = svg.getBoundingClientRect();
    const px = ((evt.clientX - rect.left) / rect.width) * W;
    let best = 0;
    for (let i = 1; i < points.length; i++) {
      if (Math.abs(points[i][0] - px) < Math.abs(points[best][0] - px)) best = i;
    }
    crosshair.setAttribute('x1', points[best][0]);
    crosshair.setAttribute('x2', points[best][0]);
    crosshair.setAttribute('visibility', 'visible');
  });
  plotHit.addEventListener('pointerleave', () => crosshair.setAttribute('visibility', 'hidden'));
  svg.appendChild(plotHit);

  el.duration.appendChild(svg);
}

/* ------------------------------ 汇总渲染 ------------------------------ */

function render() {
  renderKpi();
  redraw(el.colors, renderColors);
  redraw(el.status, renderStatus);
  redraw(el.duration, renderDuration);
}

renderSidebar('stats');
el.range.addEventListener('change', render);
init();
render();
subscribe(render);
