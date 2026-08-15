// ================= 点金 AI 页面逻辑 =================
const $ = (sel) => document.querySelector(sel);
let sessions = [];            // [{id, title, updated}]
let currentId = null;
let streaming = false;
let toolsEnabled = true;
let currentRaw = [];          // 当前会话的 [{role, text}]，供导出

// ---------- 通用 ----------
function showToast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 2000);
}
function showBanner(msg) {
  const b = $('#banner');
  b.textContent = '⚠ ' + msg;
  b.classList.remove('hidden');
}
function hideBanner() { $('#banner').classList.add('hidden'); }
function fmtTime(ts) {
  const d = new Date(ts);
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}

// ---------- 隐私 / 摸鱼（与看板同步） ----------
function applyDJMode() {
  const privacy = localStorage.getItem('tzzb_privacy') === '1';
  const stealth = localStorage.getItem('tzzb_stealth') === '1';
  document.body.classList.toggle('privacy', privacy);
  document.body.classList.toggle('stealth', stealth);
  document.title = stealth ? '数据概览 · Overview' : '点金 · 投资 AI 助手';
}
function toggleDJPrivacy() {
  const on = !document.body.classList.contains('privacy');
  document.body.classList.toggle('privacy', on);
  localStorage.setItem('tzzb_privacy', on ? '1' : '0');
}
function toggleDJStealth() {
  const on = !document.body.classList.contains('stealth');
  document.body.classList.toggle('stealth', on);
  localStorage.setItem('tzzb_stealth', on ? '1' : '0');
  document.title = on ? '数据概览 · Overview' : '点金 · 投资 AI 助手';
}
// 双开标签页实时同步：任一页切换，另一页立即生效
window.addEventListener('storage', (e) => {
  if (e.key === 'tzzb_privacy' || e.key === 'tzzb_stealth') applyDJMode();
});
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------- Markdown 管道 ----------
const renderer = new marked.Renderer();
renderer.code = function (code, infostring) {
  const lang = (infostring || '').trim().split(/\s+/)[0];
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  return `<div class="code-block"><div class="code-header"><span>${esc(lang || 'text')}</span><button class="code-copy" onclick="copyCode(this)">复制</button></div><pre><code class="${lang ? 'language-' + esc(lang) : ''}">${esc(code)}</code></pre></div>`;
};
marked.use({ renderer, gfm: true, breaks: true });

function renderMarkdown(text) {
  const html = marked.parse(text || '');
  return DOMPurify.sanitize(html);
}
function highlightCode(container) {
  container.querySelectorAll('pre code').forEach((b) => { try { hljs.highlightElement(b); } catch (e) { /* 未知语言忽略 */ } });
}
function copyCode(btn) {
  const text = btn.closest('.code-block').querySelector('pre').innerText;
  navigator.clipboard.writeText(text).then(() => showToast('已复制代码'));
}

// ---------- 会话列表 ----------
async function loadSessions() {
  hideBanner();
  try {
    const r = await fetch('/api/agent/sessions');
    if (!r.ok) {
      showBanner(r.status === 401 ? '未配置 Cookie（~/.tzzb_cookies），会话功能不可用' : '会话列表加载失败（HTTP ' + r.status + '）');
      return;
    }
    const data = await r.json();
    sessions = data.sessions || [];
    renderSessionList();
    if (sessions.length && !currentId) openSession(sessions[0].id);
    if (!sessions.length) showEmptyState();
  } catch (e) { showBanner('网络错误：' + e.message); }
}

function groupOf(ts) {
  const now = Date.now(), day = 86400000;
  if (now - ts < day) return 'today';
  if (now - ts < 7 * day) return 'week';
  return 'older';
}

const CHAT_ICON = '<svg class="si-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M21 12a8 8 0 0 1-8 8H5l2.5-3A8 8 0 1 1 21 12z"/></svg>';
const PEN_ICON = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>';
const X_ICON = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';

function renderSessionList() {
  const kw = ($('#session-search').value || '').trim().toLowerCase();
  const groups = { today: [], week: [], older: [] };
  sessions.filter((s) => !kw || (s.title || '').toLowerCase().includes(kw))
    .forEach((s) => groups[groupOf(s.updated)].push(s));
  for (const key of ['today', 'week', 'older']) {
    const group = document.querySelector(`.session-group[data-group="${key}"]`);
    const box = group.querySelector('.group-items');
    box.innerHTML = '';
    group.style.display = groups[key].length ? '' : 'none';
    groups[key].forEach((s) => {
      const div = document.createElement('div');
      div.className = 'session-item' + (s.id === currentId ? ' active' : '');
      div.innerHTML = CHAT_ICON + '<span class="si-title"></span><button class="si-ren" title="重命名"></button><button class="si-del" title="删除"></button>';
      div.querySelector('.si-title').textContent = s.title || '新对话';
      div.querySelector('.si-ren').innerHTML = PEN_ICON;
      div.querySelector('.si-del').innerHTML = X_ICON;
      div.onclick = (e) => { if (e.target.closest('.si-ren, .si-del')) return; openSession(s.id); };
      div.querySelector('.si-ren').onclick = (e) => { e.stopPropagation(); renameInline(div, s); };
      div.querySelector('.si-del').onclick = (e) => { e.stopPropagation(); deleteSession(s.id); };
      box.appendChild(div);
    });
  }
}

async function openSession(id) {
  if (streaming) return;
  currentId = id;
  currentRaw = [];
  renderSessionList();
  updateHeaderTitle();
  const box = $('#messages');
  box.innerHTML = '<div class="msg msg-ai"><div class="typing-dots"><span></span><span></span><span></span></div></div>';
  try {
    const r = await fetch('/api/agent/history?sessionId=' + encodeURIComponent(id));
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    box.innerHTML = '';
    (data.messages || []).forEach((m) => {
      const role = m.role === 'assistant' ? 'ai' : 'user';
      currentRaw.push({ role, text: m.text });
      appendMessage(role, m.text, { animate: false });
    });
    if (!data.messages?.length) showEmptyState(false);
  } catch (e) {
    box.innerHTML = '';
    showBanner('历史加载失败：' + e.message);
  }
}

function newChat() {
  if (streaming) return;
  currentId = crypto.randomUUID();
  sessions.unshift({ id: currentId, title: '新对话', updated: Date.now() });
  currentRaw = [];
  renderSessionList();
  updateHeaderTitle();
  showEmptyState();
}

function updateHeaderTitle() {
  const cur = sessions.find((s) => s.id === currentId);
  $('#chat-title').textContent = cur ? (cur.title || '新对话') : '新对话';
}

function showEmptyState(withTitle = true) {
  const box = $('#messages');
  box.innerHTML = `
    <div class="empty-state">
      <div class="empty-title">${withTitle ? '今日盘面，想问点什么？' : '暂无对话'}</div>
      <div class="empty-sub">点金 · 数据实时同步 · 由同花顺/腾讯/新浪提供</div>
      <div class="empty-cards">
        <div class="empty-card" data-q="生成本日投资简报">
          <div class="ec-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg></div>
          <div class="ec-title">生成本日投资简报</div>
          <div class="ec-desc">今日盈亏、持仓异动与资金流向汇总</div>
        </div>
        <div class="empty-card" data-q="分析持仓集中度">
          <div class="ec-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M2 12h20"/></svg></div>
          <div class="ec-title">分析持仓集中度</div>
          <div class="ec-desc">行业分布与单一标的风险评估</div>
        </div>
        <div class="empty-card" data-q="本周盈亏回顾">
          <div class="ec-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/></svg></div>
          <div class="ec-title">本周盈亏回顾</div>
          <div class="ec-desc">逐日盈亏序列与回撤分析</div>
        </div>
        <div class="empty-card" data-q="K线技术解读">
          <div class="ec-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg></div>
          <div class="ec-title">K线技术解读</div>
          <div class="ec-desc">均线、量能与关键位分析</div>
        </div>
      </div>
    </div>`;
  box.querySelectorAll('.empty-card').forEach((c) => {
    c.onclick = () => { $('#input').value = c.dataset.q; sendMessage(); };
  });
}

// ---------- 消息 ----------
const MARK_SVG = `<svg class="msg-ai-mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round">
<path d="M5 5h14l2.5 3.5L7.5 20H5z"/>
<path d="M8.5 9.5l7 6.5"/>
<circle cx="18.5" cy="4.5" r="1.6" fill="currentColor" stroke="none"/>
</svg>`;

function appendMessage(role, text, opts = {}) {
  const box = $('#messages');
  const empty = box.querySelector('.empty-state');
  if (empty) box.innerHTML = '';
  const div = document.createElement('div');
  if (role === 'user') {
    div.className = 'msg msg-user';
    div.textContent = text;
  } else {
    const isReplay = opts.animate === false;
    div.className = 'msg msg-ai';
    div.innerHTML = `
      <div class="msg-ai-head">${MARK_SVG}<span class="msg-ai-name">点金</span><span class="msg-ai-time">${fmtTime(Date.now())}</span>${isReplay ? '' : '<span class="breath-dot"></span>'}</div>
      <div class="msg-ai-body"></div>
      <div class="msg-actions">
        <button class="act-copy">复制</button>
        ${isReplay ? '' : '<button class="act-regen">重新生成</button>'}
      </div>`;
    div.querySelector('.msg-ai-body').innerHTML = renderMarkdown(text);
    highlightCode(div);
    div.querySelector('.act-copy').onclick = () => {
      navigator.clipboard.writeText(div.querySelector('.msg-ai-body').innerText).then(() => showToast('已复制'));
    };
    const regenBtn = div.querySelector('.act-regen');
    if (regenBtn) regenBtn.onclick = () => regenerate();
  }
  if (opts.animate === false) {
    div.style.animation = 'none';  // 历史回放不需要入场动画
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

function appendUserMessage(text) {
  currentRaw.push({ role: 'user', text });
  return appendMessage('user', text);
}

async function sendMessage() {
  if (streaming) return;
  const input = $('#input');
  const query = input.value.trim();
  if (!query) return;
  input.value = '';
  autoResize(input);
  if (!currentId) { currentId = crypto.randomUUID(); sessions.unshift({ id: currentId, title: '新对话', updated: Date.now() }); renderSessionList(); updateHeaderTitle(); }

  hideBanner();
  appendUserMessage(query);
  const aiDiv = appendMessage('ai', '');
  const bodyEl = aiDiv.querySelector('.msg-ai-body');
  bodyEl.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';

  streaming = true;
  $('#send-btn').disabled = true;
  let raw = '', firstText = true;

  try {
    const response = await fetch('/api/agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: currentId, query, toolsEnabled }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      bodyEl.innerHTML = '<span style="color:#FCA5A5">❌ ' + escapeHtml(err.error || '请求失败（请检查 Cookie / AI Key）') + '</span>';
      streaming = false; $('#send-btn').disabled = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', eventName = '', eventData = '';
    const handleEvent = () => {
      if (!eventName || !eventData) return;
      try {
        const data = JSON.parse(eventData);
        if (eventName === 'status') {
          bodyEl.innerHTML = '<span style="color:var(--text-3)">⏳ ' + escapeHtml(data.content) + '</span>';
        } else if (eventName === 'text') {
          if (firstText) { bodyEl.innerHTML = ''; firstText = false; }
          raw += data.delta;
          bodyEl.innerHTML = renderMarkdown(raw);
          highlightCode(aiDiv);
        } else if (eventName === 'error') {
          bodyEl.innerHTML = '<span style="color:#FCA5A5">❌ ' + escapeHtml(data.message) + '</span>';
        }
      } catch (e) { /* 坏行忽略 */ }
    };
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith(':')) continue;
        if (line.startsWith('event: ')) eventName = line.slice(7).trim();
        else if (line.startsWith('data: ')) eventData += line.slice(6);
        else if (line === '') { handleEvent(); eventName = ''; eventData = ''; }
      }
    }
    if (firstText) { bodyEl.innerHTML = '<span style="color:var(--text-3)">（模型返回为空）</span>'; }
    if (raw) currentRaw.push({ role: 'ai', text: raw });
  } catch (e) {
    bodyEl.innerHTML = '<span style="color:#FCA5A5">❌ 网络错误: ' + e.message + '</span>';
  }

  streaming = false;
  $('#send-btn').disabled = false;
  refreshSessionsAfterSend();
  $('#messages').scrollTop = $('#messages').scrollHeight;
}

async function refreshSessionsAfterSend() {
  try {
    const r = await fetch('/api/agent/sessions');
    if (r.ok) {
      const data = await r.json();
      sessions = data.sessions || [];
      renderSessionList();
      updateHeaderTitle();
    }
  } catch (e) { /* 忽略 */ }
}

async function regenerate() {
  if (streaming || !currentId) return;
  const lastRaw = currentRaw[currentRaw.length - 1];
  if (!lastRaw || lastRaw.role !== 'ai') return;
  currentRaw.pop();
  const box = $('#messages');
  const lastAi = [...box.querySelectorAll('.msg-ai')].pop();
  if (lastAi) lastAi.remove();

  const aiDiv = appendMessage('ai', '');
  const bodyEl = aiDiv.querySelector('.msg-ai-body');
  bodyEl.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  streaming = true;
  $('#send-btn').disabled = true;
  let raw = '', firstText = true;

  try {
    const response = await fetch('/api/agent/regenerate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: currentId, toolsEnabled }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      bodyEl.innerHTML = '<span style="color:#FCA5A5">❌ ' + (err.error || '重新生成失败') + '</span>';
      streaming = false; $('#send-btn').disabled = false;
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', eventName = '', eventData = '';
    const handleEvent = () => {
      if (!eventName || !eventData) return;
      try {
        const data = JSON.parse(eventData);
        if (eventName === 'status') {
          bodyEl.innerHTML = '<span style="color:var(--text-3)">⏳ ' + escapeHtml(data.content) + '</span>';
        } else if (eventName === 'text') {
          if (firstText) { bodyEl.innerHTML = ''; firstText = false; }
          raw += data.delta;
          bodyEl.innerHTML = renderMarkdown(raw);
          highlightCode(aiDiv);
        } else if (eventName === 'error') {
          bodyEl.innerHTML = '<span style="color:#FCA5A5">❌ ' + escapeHtml(data.message) + '</span>';
        }
      } catch (e) { /* 坏行忽略 */ }
    };
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith(':')) continue;
        if (line.startsWith('event: ')) eventName = line.slice(7).trim();
        else if (line.startsWith('data: ')) eventData += line.slice(6);
        else if (line === '') { handleEvent(); eventName = ''; eventData = ''; }
      }
    }
    if (firstText) { bodyEl.innerHTML = '<span style="color:var(--text-3)">（模型返回为空）</span>'; }
    if (raw) currentRaw.push({ role: 'ai', text: raw });
  } catch (e) {
    bodyEl.innerHTML = '<span style="color:#FCA5A5">❌ 网络错误: ' + e.message + '</span>';
  }

  streaming = false;
  $('#send-btn').disabled = false;
  $('#messages').scrollTop = $('#messages').scrollHeight;
}

// ---------- 重命名 / 删除 / 导出 ----------
function renameInline(itemDiv, session) {
  const titleEl = itemDiv.querySelector('.si-title');
  const input = document.createElement('input');
  input.className = 'si-edit';
  input.value = session.title || '';
  titleEl.replaceWith(input);
  input.focus();
  input.select();
  const finish = async (save) => {
    if (save && input.value.trim()) {
      try {
        const r = await fetch('/api/agent/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sessionId: session.id, title: input.value.trim() }),
        });
        if (r.ok) {
          session.title = input.value.trim();
          updateHeaderTitle();
          showToast('已重命名');
        } else {
          const err = await r.json().catch(() => ({}));
          showBanner(err.error || '重命名失败');
        }
      } catch (e) { showBanner('网络错误：' + e.message); }
    }
    renderSessionList();
  };
  input.onkeydown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    else if (e.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(true);
}

async function deleteSession(id) {
  if (!confirm('删除该对话？此操作不可恢复')) return;
  try {
    const r = await fetch('/api/agent/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: id }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    sessions = sessions.filter((s) => s.id !== id);
    if (id === currentId) {
      currentId = null;
      currentRaw = [];
      if (sessions.length) openSession(sessions[0].id);
      else { updateHeaderTitle(); showEmptyState(); }
    }
    renderSessionList();
  } catch (e) { showBanner('删除失败：' + e.message); }
}

function editHeaderTitle() {
  const titleEl = $('#chat-title');
  const input = document.createElement('input');
  input.className = 'chat-title-input';
  input.value = titleEl.textContent;
  titleEl.replaceWith(input);
  input.focus();
  input.select();
  const finish = async () => {
    const v = input.value.trim();
    if (v && currentId) {
      try {
        await fetch('/api/agent/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sessionId: currentId, title: v }),
        });
        const cur = sessions.find((s) => s.id === currentId);
        if (cur) cur.title = v;
      } catch (e) { /* 忽略 */ }
    }
    updateHeaderTitle();
    renderSessionList();
  };
  input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); finish(); } else if (e.key === 'Escape') finish(); };
  input.onblur = finish;
}

function exportMarkdown() {
  if (!currentRaw.length) { showToast('当前没有可导出的对话'); return; }
  const md = currentRaw.map((m) => (m.role === 'user' ? '## 我\n\n' : '## 点金\n\n') + m.text).join('\n\n---\n\n');
  navigator.clipboard.writeText(md).then(() => showToast('已导出 Markdown 到剪贴板'));
}

// ---------- 输入区 ----------
function autoResize(ta) {
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
}

// ---------- 侧栏折叠 / 移动端抽屉 ----------
function toggleSidebar() {
  const sb = $('#sidebar');
  sb.classList.toggle('collapsed');
  localStorage.setItem('dj_sidebar', sb.classList.contains('collapsed') ? '1' : '0');
}

// ---------- 初始化 ----------
document.addEventListener('DOMContentLoaded', () => {
  // 事件绑定
  $('#new-chat').onclick = newChat;
  $('#sidebar-toggle').onclick = toggleSidebar;
  $('#export-btn').onclick = exportMarkdown;
  $('#dj-privacy-btn').onclick = toggleDJPrivacy;
  $('#dj-stealth-btn').onclick = toggleDJStealth;
  applyDJMode();
  $('#settings-btn').onclick = () => showToast('设置页将在下期（能力扩展）提供');
  $('#session-search').oninput = renderSessionList;
  $('#chat-title').onclick = editHeaderTitle;
  $('#tool-toggle').onclick = () => {
    toolsEnabled = !toolsEnabled;
    $('#tool-toggle').classList.toggle('on', toolsEnabled);
    showToast(toolsEnabled ? '数据工具已开启' : '数据工具已关闭（纯对话模式）');
  };
  $('#send-btn').onclick = sendMessage;

  const input = $('#input');
  input.oninput = () => autoResize(input);
  input.onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(); }
  };

  document.querySelectorAll('.chip').forEach((c) => {
    c.onclick = () => { input.value = c.dataset.q; autoResize(input); sendMessage(); };
  });

  // 恢复侧栏状态（移动端默认收起）
  const saved = localStorage.getItem('dj_sidebar');
  if (window.innerWidth > 1024) {
    if (saved === '1') $('#sidebar').classList.add('collapsed');
  } else {
    $('#sidebar').classList.add('collapsed');
  }
  $('#sidebar-overlay').onclick = () => $('#sidebar').classList.add('collapsed');

  // 移动端键盘弹起处理
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
      const bottom = Math.max(0, window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop);
      document.querySelector('.input-area').style.transform = bottom > 0 ? 'translateY(-' + bottom + 'px)' : '';
    });
  }

  loadSessions();
});
