// ui.js — 通用 UI:侧边导航、轻提示、徽章与格式化工具
// 动态文案一律使用 textContent 写入,不拼接 innerHTML。

import { APP } from './config.js';

const NAV = [
  { id: 'monitor',  label: '运行监控', href: 'index.html',          icon: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M9 20h6"/>' },
  { id: 'records',  label: '任务记录', href: 'pages/records.html',  icon: '<path d="M8 6h11M8 12h11M8 18h11"/><circle cx="4.5" cy="6" r="1.2" fill="currentColor" stroke="none"/><circle cx="4.5" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="4.5" cy="18" r="1.2" fill="currentColor" stroke="none"/>' },
  { id: 'stats',    label: '分类统计', href: 'pages/stats.html',    icon: '<path d="M5 20V12M12 20V5M19 20V9"/>' },
  { id: 'settings', label: '参数配置', href: 'pages/settings.html', icon: '<circle cx="12" cy="12" r="3.2"/><path d="M12 3v2.2M12 18.8V21M21 12h-2.2M5.2 12H3M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6M18.4 18.4l-1.6-1.6M7.2 7.2L5.6 5.6"/>' },
];

/** 渲染左侧导航,activeId 为当前页 id */
export function renderSidebar(activeId) {
  const root = document.getElementById('sidebar');
  if (!root) return;
  const inPages = location.pathname.split('/').includes('pages');
  const base = inPages ? '../' : '';

  root.textContent = '';
  root.className = 'sidebar';

  const title = document.createElement('div');
  title.className = 'side-title';
  const h1 = document.createElement('div');
  h1.className = 'side-title-main';
  h1.textContent = '机械臂垃圾分拣';
  const sub = document.createElement('div');
  sub.className = 'side-title-sub';
  sub.textContent = '记录服务 · Web 看板';
  title.append(h1, sub);
  root.appendChild(title);

  const nav = document.createElement('nav');
  nav.className = 'side-nav';
  for (const item of NAV) {
    const a = document.createElement('a');
    a.className = 'nav-item' + (item.id === activeId ? ' active' : '');
    a.href = base + item.href;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = item.icon;   // 静态内置图标,非外部数据
    const span = document.createElement('span');
    span.textContent = item.label;
    a.append(svg, span);
    nav.appendChild(a);
  }
  root.appendChild(nav);

  const foot = document.createElement('div');
  foot.className = 'side-foot';
  const badge = document.createElement('span');
  badge.className = 'badge';
  const isMock = APP.api.mode === 'mock';
  badge.style.setProperty('--dot', isMock ? '#fab219' : '#0ca30c');
  badge.textContent = isMock ? '演示模式 · 模拟数据' : '实机联调';
  foot.appendChild(badge);
  root.appendChild(foot);
}

/** 轻提示 */
export function showToast(message, type = 'ok') {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.dataset.type = type;
  el.hidden = false;
  el.classList.remove('toast-in');
  void el.offsetWidth;               // 重置动画
  el.classList.add('toast-in');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    el.classList.remove('toast-in');
    el.hidden = true;
  }, 2600);
}

/** 彩色圆点徽章(dot 传色值,文字始终为文本色,颜色不单独承载语义) */
export function badge(text, hex) {
  const span = document.createElement('span');
  span.className = 'badge';
  span.style.setProperty('--dot', hex);
  span.textContent = text;
  return span;
}

/** 时间与数值格式化 */
export const fmt = {
  time(ms) {
    return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false });
  },
  timeFull(ms) {
    return new Date(ms).toLocaleString('zh-CN', { hour12: false });
  },
  /** 起止时间差(秒),任一端为 null 时显示 — */
  duration(startMs, endMs) {
    if (startMs == null || endMs == null) return '—';
    return ((endMs - startMs) / 1000).toFixed(1) + ' s';
  },
  /** 抓取坐标(x,y,z),未知坐标用 — (契约约定 null 不用 0 代替) */
  coord(ev) {
    return [ev.x_mm, ev.y_mm, ev.z_mm].map((v) => (v == null ? '—' : v)).join(', ');
  },
  shortId(id) {
    return id && id.length > 10 ? id.slice(0, 6) + '…' : (id || '—');
  },
};
