// records.js — 任务记录页
// task_event 明细列表:按颜色 / 状态筛选,分页展示,数据实时更新。

import { init } from '../core/api.js';
import { getState, subscribe } from '../core/store.js';
import { renderSidebar, badge, fmt } from '../core/ui.js';
import { COLORS, COLOR_META, STATUS_META, ERROR_META } from '../core/config.js';

const PAGE_SIZE = 20;
const MODE_LABEL = { real: '实机', fallback: 'HSV 兜底', simulation: '模拟' };

const ui = {
  color: document.getElementById('filter-color'),
  status: document.getElementById('filter-status'),
  body: document.getElementById('records-body'),
  count: document.getElementById('record-count'),
  pageInfo: document.getElementById('page-info'),
  prev: document.getElementById('btn-prev'),
  next: document.getElementById('btn-next'),
};

let page = 1;

/* ------------------------------ 初始化 ------------------------------ */

renderSidebar('records');

// 筛选下拉
{
  const all = document.createElement('option');
  all.value = 'all';
  all.textContent = '全部';
  ui.color.appendChild(all);
  for (const c of COLORS) {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = COLOR_META[c].label;
    ui.color.appendChild(opt);
  }
  const allS = document.createElement('option');
  allS.value = 'all';
  allS.textContent = '全部';
  ui.status.appendChild(allS);
  for (const [key, meta] of Object.entries(STATUS_META)) {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = meta.label;
    ui.status.appendChild(opt);
  }
}

ui.color.addEventListener('change', () => { page = 1; render(); });
ui.status.addEventListener('change', () => { page = 1; render(); });
ui.prev.addEventListener('click', () => { page = Math.max(1, page - 1); render(); });
ui.next.addEventListener('click', () => {
  const total = filterEvents().length;
  page = Math.min(Math.ceil(total / PAGE_SIZE), page + 1);
  render();
});

init();
render();
subscribe(render);

/* ------------------------------ 渲染 ------------------------------ */

function filterEvents() {
  return getState().events.filter((ev) => {
    if (ui.color.value !== 'all' && ev.color !== ui.color.value) return false;
    if (ui.status.value !== 'all' && ev.status !== ui.status.value) return false;
    return true;
  });
}

function render() {
  const list = filterEvents();
  const total = list.length;
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  page = Math.min(page, maxPage);
  const slice = list.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  ui.body.textContent = '';

  if (slice.length === 0) {
    const tr = document.createElement('tr');
    tr.className = 'table-empty';
    const td = document.createElement('td');
    td.colSpan = 8;
    td.textContent = '暂无符合条件的记录';
    tr.appendChild(td);
    ui.body.appendChild(tr);
  } else {
    for (const ev of slice) {
      ui.body.appendChild(renderRow(ev));
    }
  }

  ui.count.textContent = `共 ${total} 条记录`;
  ui.pageInfo.textContent = `${page} / ${maxPage}`;
  ui.prev.disabled = page <= 1;
  ui.next.disabled = page >= maxPage;
}

function renderRow(ev) {
  const tr = document.createElement('tr');
  const cm = COLOR_META[ev.color] || { label: ev.color, hex: '#898781' };
  const sm = STATUS_META[ev.status] || { label: ev.status, hex: '#898781' };

  const texts = [
    fmt.time(ev.occurred_at_ms),
    ev.task_id,
    '',   // 颜色列(徽章)
    '',   // 状态列(徽章)
    `(${fmt.coord(ev)})`,
    fmt.duration(ev.started_at_ms, ev.finished_at_ms),
    MODE_LABEL[ev.mode] || ev.mode,
    ev.error_code ? (ERROR_META[ev.error_code]?.label || ev.error_code) : '—',
  ];
  texts.forEach((text, i) => {
    const td = document.createElement('td');
    if (i !== 2 && i !== 3) td.textContent = text;
    tr.appendChild(td);
  });

  // 颜色与状态用带色点徽章展示(颜色不单独承载语义)
  tr.children[2].appendChild(badge(cm.label, cm.hex));
  tr.children[3].appendChild(badge(sm.label, sm.hex));

  // 数字列使用等宽数字,纵向对齐
  for (const i of [0, 1, 4, 5]) tr.children[i].className = 'num';
  return tr;
}
