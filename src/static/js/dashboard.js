// ===== STATE =====
let allSessions = [];
let runningPids = {};  // {session_id: process_info}
let currentTab = 'active';
let activeTimer = null;
let previousTimer = null;
let expandedSessionIds = new Set();  // persist across re-renders
let collapsedGroups = new Set();     // persist across re-renders
let loadedDetails = {};              // cache detail HTML by session id
let currentView = localStorage.getItem('dash-view') || 'tile';
let starredSessions = new Set(JSON.parse(localStorage.getItem('dash-starred') || '[]'));

// ===== DISCONNECT DETECTION =====
let consecutiveFailures = 0;
const DISCONNECT_THRESHOLD = 2;  // show overlay after N consecutive failures
let retryCountdown = null;
let retrySecondsLeft = 0;

function showDisconnect(errorMsg) {
  const overlay = document.getElementById('disconnect-overlay');
  if (!overlay) return;
  document.getElementById('disconnect-detail').innerHTML =
    `<strong>What was detected:</strong> The dashboard could not reach the server.<br>` +
    `<strong>Error:</strong> ${esc(errorMsg)}`;
  overlay.style.display = 'flex';
  startRetryCountdown();
}

function hideDisconnect() {
  const overlay = document.getElementById('disconnect-overlay');
  if (overlay) overlay.style.display = 'none';
  if (retryCountdown) { clearInterval(retryCountdown); retryCountdown = null; }
  document.getElementById('disconnect-retry').textContent = '';
}

function startRetryCountdown() {
  if (retryCountdown) clearInterval(retryCountdown);
  retrySecondsLeft = 5;
  updateRetryMsg();
  retryCountdown = setInterval(() => {
    retrySecondsLeft--;
    if (retrySecondsLeft <= 0) {
      clearInterval(retryCountdown);
      retryCountdown = null;
      document.getElementById('disconnect-retry').textContent = 'Retrying now\u2026';
    } else {
      updateRetryMsg();
    }
  }, 1000);
}

function updateRetryMsg() {
  const el = document.getElementById('disconnect-retry');
  if (el) el.textContent = `\u21BB Retrying in ${retrySecondsLeft}s\u2026`;
}

function recordFetchSuccess() {
  if (consecutiveFailures >= DISCONNECT_THRESHOLD) hideDisconnect();
  consecutiveFailures = 0;
}

function recordFetchFailure(err) {
  consecutiveFailures++;
  if (consecutiveFailures >= DISCONNECT_THRESHOLD) {
    const msg = err instanceof TypeError ? err.message : String(err);
    showDisconnect(msg);
  }
}

// ===== VIEW TOGGLE =====
function setView(view) {
  currentView = view;
  localStorage.setItem('dash-view', view);
  document.getElementById('view-list').classList.toggle('active', view === 'list');
  document.getElementById('view-tile').classList.toggle('active', view === 'tile');
  render();
}
function initView() {
  document.getElementById('view-list').classList.toggle('active', currentView === 'list');
  document.getElementById('view-tile').classList.toggle('active', currentView === 'tile');
}

// ===== THEME =====
function applyTheme() {
  const mode = localStorage.getItem('dash-mode') || 'dark';
  const palette = localStorage.getItem('dash-palette') || 'default';
  document.documentElement.setAttribute('data-mode', mode);
  document.documentElement.setAttribute('data-palette', palette);
  document.getElementById('mode-toggle').innerHTML = mode === 'dark' ? '&#x1F319; Dark' : '&#x2600;&#xFE0F; Light';
  document.getElementById('palette-select').value = palette;
}
document.getElementById('mode-toggle').onclick = () => {
  const cur = localStorage.getItem('dash-mode') || 'dark';
  localStorage.setItem('dash-mode', cur === 'dark' ? 'light' : 'dark');
  applyTheme();
};
document.getElementById('palette-select').onchange = (e) => {
  localStorage.setItem('dash-palette', e.target.value);
  applyTheme();
};
applyTheme();

// ===== TABS =====
function switchTab(tab) {
  currentTab = tab;
  history.replaceState(null, '', '#' + tab);
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + tab));
  if (tab === 'files') renderFilesTab();
  if (tab === 'timeline') renderTimelineTab();
}

async function renderFilesTab() {
  const panel = document.getElementById('panel-files');
  panel.innerHTML = '<div class="loading">Loading files...</div>';
  try {
    const resp = await fetch('/api/files');
    const files = await resp.json();
    if (!files.length) { panel.innerHTML = '<div class="empty">No file data available.</div>'; return; }
    const maxCount = files[0].session_count;
    let html = '<table style="width:100%;border-collapse:collapse;font-size:13px">';
    html += '<thead><tr><th style="text-align:left;padding:6px 8px;color:var(--text2);border-bottom:1px solid var(--border)">File path</th><th style="text-align:left;padding:6px 8px;color:var(--text2);border-bottom:1px solid var(--border)">Sessions</th><th style="width:200px;padding:6px 8px;color:var(--text2);border-bottom:1px solid var(--border)">Frequency</th></tr></thead><tbody>';
    files.forEach(f => {
      const pct = Math.round((f.session_count / maxCount) * 100);
      const shortPath = f.file_path.length > 80 ? '...' + f.file_path.slice(-77) : f.file_path;
      html += `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 8px;font-family:monospace;color:var(--text2)">${esc(shortPath)}</td>
        <td style="padding:6px 8px;color:var(--text)">${f.session_count}</td>
        <td style="padding:6px 8px"><div style="height:8px;background:var(--surface2);border-radius:4px"><div style="width:${pct}%;height:100%;background:var(--accent);border-radius:4px"></div></div></td>
      </tr>`;
    });
    html += '</tbody></table>';
    panel.innerHTML = html;
  } catch(e) {
    panel.innerHTML = '<div class="empty">Error loading files.</div>';
  }
}

function renderTimelineTab() {
  const panel = document.getElementById('panel-timeline');
  if (!allSessions.length) { panel.innerHTML = '<div class="empty">No sessions to display.</div>'; return; }

  const fiveDaysAgo = Date.now() - 5 * 24 * 60 * 60 * 1000;
  const sessions = [...allSessions].filter(s => s.created_at && s.updated_at && new Date(s.updated_at).getTime() >= fiveDaysAgo)
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  if (!sessions.length) { panel.innerHTML = '<div class="empty">No sessions with timestamps.</div>'; return; }

  const minTime = new Date(sessions[0].created_at).getTime();
  const maxTime = Math.max(Date.now(), ...sessions.map(s => new Date(s.updated_at).getTime()));
  const totalMs = maxTime - minTime || 1;

  // Header time labels
  const labelCount = 5;
  let labelHtml = '<div style="display:flex;margin-left:220px;margin-bottom:4px;font-size:11px;color:var(--text2)">';
  for (let i = 0; i <= labelCount; i++) {
    const t = new Date(minTime + (totalMs * i / labelCount));
    labelHtml += `<div style="flex:1;${i === labelCount ? 'text-align:right' : ''}">${t.toLocaleDateString()} ${t.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</div>`;
  }
  labelHtml += '</div>';

  const stateColors = { working:'var(--green)', thinking:'var(--green)', waiting:'var(--yellow)', idle:'var(--accent)' };
  let rowsHtml = '';
  for (const s of sessions) {
    const start = new Date(s.created_at).getTime();
    const end = runningPids[s.id] ? Date.now() : new Date(s.updated_at).getTime();
    const left = ((start - minTime) / totalMs * 100).toFixed(2);
    const width = Math.max(0.3, ((end - start) / totalMs * 100)).toFixed(2);
    const pinfo = runningPids[s.id] || {};
    const state = pinfo.state || (runningPids[s.id] ? 'working' : 'previous');
    const color = stateColors[state] || 'var(--border)';
    const label = (s.summary || '(Untitled)').substring(0, 30);
    rowsHtml += `<div style="display:flex;align-items:center;margin-bottom:4px;gap:8px">
      <div style="width:212px;min-width:212px;font-size:12px;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:right;padding-right:8px" title="${esc(s.summary || '')}">${esc(label)}</div>
      <div style="flex:1;position:relative;height:20px;background:var(--surface2);border-radius:4px;cursor:pointer" onclick="openTileDetail('${s.id}', '${esc(s.summary || '(Untitled)')}')">
        <div style="position:absolute;left:${left}%;width:${width}%;height:100%;background:${color};border-radius:4px;min-width:4px;opacity:0.85" title="${esc(s.summary || '')} — ${esc(s.created_ago)}"></div>
      </div>
    </div>`;
  }

  panel.innerHTML = `<div style="padding:8px 0">${labelHtml}${rowsHtml}</div>`;
}

// ===== DATA FETCH =====
async function fetchSessions() {
  try {
    const [sessResp, procResp] = await Promise.all([
      fetch('/api/sessions'), fetch('/api/processes')
    ]);
    allSessions = await sessResp.json();
    runningPids = await procResp.json();
    recordFetchSuccess();
  } catch(e) { console.error('Fetch error:', e); recordFetchFailure(e); }
  render();
  document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
}

async function fetchProcesses() {
  try {
    const resp = await fetch('/api/processes');
    const newPids = await resp.json();
    checkForWaitingTransitions(runningPids, newPids);
    runningPids = newPids;
    recordFetchSuccess();
  } catch(e) { recordFetchFailure(e); }
  render();
}

// ===== DESKTOP NOTIFICATIONS =====
let notificationsEnabled = false;
function notifPopoverContent() {
  if (!('Notification' in window)) {
    return '<div class="pop-title">&#x1F6AB; Not supported</div><div class="pop-step">Your browser does not support desktop notifications.</div>';
  }
  const p = Notification.permission;
  if (p === 'granted') {
    return notificationsEnabled
      ? '<div class="pop-title">&#x1F514; Notifications On</div><div class="pop-step">Click to <span>turn off</span> notifications.</div>'
      : '<div class="pop-title">&#x1F515; Notifications Off</div><div class="pop-step">Click to <span>turn on</span> notifications.</div>';
  }
  if (p === 'denied') {
    return '<div class="pop-title">&#x1F6AB; Notifications blocked</div>'
      + '<div class="pop-step">1. Click the <span>&#x1F512; lock icon</span> in the address bar</div>'
      + '<div class="pop-step">2. Find <span>Notifications</span> &rarr; set to <span>Allow</span></div>'
      + '<div class="pop-step">3. Refresh the page and click here again</div>';
  }
  // default — not yet asked
  return '<div class="pop-title">&#x1F514; Enable notifications</div>'
    + '<div class="pop-step">Click this button, then look for the</div>'
    + '<div class="pop-step"><span>&#x1F514; bell icon</span> in your address bar &rarr; click <span>Allow</span></div>';
}
function showNotifHint() {
  const pop = document.getElementById('notif-popover');
  if (!pop) return;
  pop.innerHTML = notifPopoverContent();
  pop.classList.add('visible');
}
function hideNotifHint() {
  const pop = document.getElementById('notif-popover');
  if (pop) pop.classList.remove('visible');
}
function enableNotifications() {
  if (!('Notification' in window)) { alert('Desktop notifications not supported in this browser'); return; }
  if (Notification.permission === 'granted') {
    notificationsEnabled = !notificationsEnabled;
    updateNotifBtn();
    if (notificationsEnabled) {
      new Notification('Copilot Dashboard', { body: 'Notifications enabled!' });
    }
    hideNotifHint();
    return;
  }
  if (Notification.permission === 'denied') {
    showNotifHint();
    return;
  }
  // default — request permission; Edge may show quiet UI (address bar bell)
  Notification.requestPermission().then((p) => {
    notificationsEnabled = p === 'granted';
    updateNotifBtn();
    if (notificationsEnabled) {
      new Notification('Copilot Dashboard', { body: 'Notifications enabled!' });
      hideNotifHint();
    } else {
      // Still default = quiet UI shown; keep popover visible with instructions
      showNotifHint();
    }
  });
  // Immediately show the "look for bell in address bar" hint after click
  showNotifHint();
}
function updateNotifBtn() {
  const btn = document.getElementById('notif-btn');
  if (!btn) return;
  if (notificationsEnabled) {
    btn.innerHTML = '&#x1F514; Notifications On';
    btn.style.opacity = '1';
  } else {
    btn.innerHTML = '&#x1F515; Notifications Off';
    btn.style.opacity = '0.6';
  }
}
// Auto-enable if already granted (no gesture needed)
if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
  notificationsEnabled = true;
}

function checkForWaitingTransitions(oldPids, newPids) {
  if (!notificationsEnabled) return;
  for (const [sid, info] of Object.entries(newPids)) {
    const oldState = oldPids[sid] ? oldPids[sid].state : null;
    if (!oldState) continue; // skip first poll (no previous state)
    // Notify when state changes to something that needs attention
    if (info.state !== oldState && (info.state === 'waiting' || info.state === 'idle')) {
      const session = allSessions.find(s => s.id === sid);
      const title = session ? (session.intent || session.summary || 'Copilot Session') : 'Copilot Session';
      const body = info.waiting_context || (info.state === 'waiting' ? 'Session is waiting for your input' : 'Session is done and ready for next task');
      new Notification(title, { body: body, tag: 'copilot-' + sid });
    }
  }
}
function toggleStar(id) {
  if (starredSessions.has(id)) starredSessions.delete(id); else starredSessions.add(id);
  localStorage.setItem('dash-starred', JSON.stringify([...starredSessions]));
  render();
}

// ===== RENDER =====
function render() {
  const filter = (document.getElementById('search').value || '').toLowerCase();

  // Split active vs previous
  const active = [], previous = [];
  allSessions.forEach(s => {
    const hay = [s.summary, s.repository, s.branch, s.cwd, s.group, s.intent, ...(s.mcp_servers || [])].filter(Boolean).join(' ').toLowerCase();
    if (filter && !hay.includes(filter)) return;
    const fiveDaysAgo = Date.now() - 5 * 24 * 60 * 60 * 1000;
    if (runningPids[s.id]) { active.push(s); } else if (new Date(s.updated_at).getTime() >= fiveDaysAgo) { previous.push(s); }
  });

  document.getElementById('active-count').textContent = active.length;
  document.getElementById('previous-count').textContent = previous.length;
  // Update waiting badge
  const waitingCount = allSessions.filter(s => runningPids[s.id] && runningPids[s.id].state === 'waiting').length;
  const wbadge = document.getElementById('waiting-badge');
  if (wbadge) { wbadge.textContent = `⏳ ${waitingCount} waiting`; wbadge.style.display = waitingCount > 0 ? '' : 'none'; }
  renderStats(active, previous);
  if (currentTab === 'timeline') renderTimelineTab();
  if (currentView === 'tile') {
    renderTilePanel('panel-active', active, true);
    renderTilePanel('panel-previous', previous, false);
  } else {
    renderPanel('panel-active', active, true);
    renderPanel('panel-previous', previous, false);
  }
}

function renderStats(active, previous) {
  if (!active.length) { document.getElementById('stats-row').innerHTML = ''; return; }
  const activeTurns = active.reduce((a, s) => a + (s.turn_count || 0), 0);
  const activeToolCalls = active.reduce((a, s) => a + (s.tool_calls || 0), 0);
  const activeSubagents = active.reduce((a, s) => a + (s.subagent_runs || 0), 0);
  const activeBgTasks = active.reduce((a, s) => a + ((runningPids[s.id] || {}).bg_tasks || 0), 0);
  const sub = '<div style="font-size:9px;opacity:0.6;margin-top:1px">IN RUNNING SESSIONS</div>';
  document.getElementById('stats-row').innerHTML = `
    <div class="stat-card"><div class="num">${active.length}</div><div class="label">Running Now</div></div>
    <div class="stat-card"><div class="num">${activeTurns.toLocaleString()}</div><div class="label">Conversations${sub}</div></div>
    <div class="stat-card"><div class="num">${activeToolCalls.toLocaleString()}</div><div class="label">Tool Calls${sub}</div></div>
    <div class="stat-card"><div class="num">${activeSubagents.toLocaleString()}</div><div class="label">Sub-agents${sub}</div></div>
    <div class="stat-card"><div class="num">${activeBgTasks.toLocaleString()}</div><div class="label">Background Tasks${sub}</div></div>
  `;
}

function renderPanel(panelId, sessions, isActive) {
  const panel = document.getElementById(panelId);
  if (!sessions.length) {
    panel.innerHTML = `<div class="empty">${isActive ? 'No active sessions detected.' : 'No previous sessions.'}</div>`;
    return;
  }

  // Group sessions
  const groups = {};
  sessions.forEach(s => {
    const g = s.group || 'General';
    (groups[g] = groups[g] || []).push(s);
  });

  // Sort groups: most sessions first
  const sortedGroups = Object.entries(groups).sort((a,b) => b[1].length - a[1].length);

  let html = '';
  for (const [groupName, items] of sortedGroups) {
    // Sort: starred first
    items.sort((a, b) => (starredSessions.has(b.id) ? 1 : 0) - (starredSessions.has(a.id) ? 1 : 0));
    const gid = (panelId + '-' + groupName).replace(/[^a-zA-Z0-9]/g, '_');
    const isCollapsed = collapsedGroups.has(gid);
    html += `<div class="group">
      <div class="group-header ${isCollapsed ? 'collapsed' : ''}" onclick="toggleGroup(this, '${gid}')">
        <span class="arrow">&#x25BC;</span>
        ${esc(groupName)}
        <span class="group-count">(${items.length})</span>
      </div>
      <div class="group-body">`;

    for (const s of items) {
      const isRunning = !!runningPids[s.id];
      const pinfo = isRunning ? (runningPids[s.id] || {}) : {};
      const isWaiting = isRunning && pinfo.state === 'waiting';
      const isIdle = isRunning && pinfo.state === 'idle';
      const cardClass = isRunning ? (isWaiting ? 'waiting-session' : (isIdle ? 'idle-session' : 'active-session')) : '';
      const isExpanded = expandedSessionIds.has(s.id);
      const state = isRunning ? (pinfo.state || 'unknown') : '';
      const waitCtx = isRunning ? (pinfo.waiting_context || '') : '';
      const stateIcons = { waiting: '&#x23F3; Waiting', working: '&#x2692;&#xFE0F; Working', thinking: '&#x1F914; Thinking', idle: '&#x1F535; Idle', unknown: '&#x2753; Unknown' };
      const stateCls = { waiting: 'badge-waiting', working: 'badge-working', thinking: 'badge-thinking', idle: 'badge-idle', unknown: 'badge-active' };

      html += `
        <div class="session-card ${cardClass} ${isExpanded ? 'expanded' : ''}" data-id="${s.id}">
          <div style="display:flex;gap:10px">
            <div style="flex:1;min-width:0" onclick="toggleDetail('${s.id}')" style="cursor:pointer">
              <div class="session-time" title="${esc(s.updated_at)}">started ${esc(s.created_ago)}${isRunning && pinfo.yolo ? ` <span class="badge badge-yolo">&#x1F525; YOLO</span>` : ''}</div>
              <div class="session-top" onclick="toggleDetail('${s.id}')">
                ${isRunning ? `<span class="live-dot ${isWaiting ? 'waiting' : (isIdle ? 'idle' : '')}" title="${isWaiting ? 'Waiting for input' : (isIdle ? 'Idle' : 'Running')}"></span>` : ''}
                <div class="session-title">${isRunning && s.intent ? '&#x1F916; ' + esc(s.intent) : esc(s.summary || '(Untitled session)')}</div>
              </div>
              ${isRunning && s.intent ? `<div class="cwd-text" style="opacity:0.7">${esc(s.summary || '')}</div>` : ''}
              ${s.cwd ? `<div class="cwd-text">&#x1F4C1; ${esc(s.cwd)}</div>` : ''}
              ${s.recent_activity ? `<div class="cwd-text" style="color:var(--accent)">&#x1F4DD; ${esc(s.recent_activity)}</div>` : ''}
              ${isWaiting && waitCtx ? `<div class="cwd-text" style="color:var(--yellow)">&#x23F3; ${esc(waitCtx)}</div>` : ''}
              ${isIdle && waitCtx ? `<div class="cwd-text" style="color:var(--accent)">&#x1F535; ${esc(waitCtx)}</div>` : ''}
              <div class="session-meta">
                ${isRunning && state ? `<span class="badge ${stateCls[state] || 'badge-active'}">${stateIcons[state] || state}</span>` : ''}
                ${isRunning && pinfo.bg_tasks ? `<span class="badge badge-bg">&#x2699;&#xFE0F; ${pinfo.bg_tasks} bg task${pinfo.bg_tasks > 1 ? 's' : ''}</span>` : ''}
                ${s.branch ? `<span class="branch-badge">&#x2387; ${s.repository ? esc(s.repository) + ' / ' : ''}${esc(s.branch)}</span>` : ''}
                <span class="badge badge-turns">&#x1F4AC; ${s.turn_count} turns</span>
                ${s.checkpoint_count ? `<span class="badge badge-cp">&#x1F3C1; ${s.checkpoint_count} checkpoints</span>` : ''}
                ${s.mcp_servers && s.mcp_servers.length ? s.mcp_servers.map(m => `<span class="badge badge-mcp">&#x1F50C; ${esc(m)}</span>`).join('') : ''}
                <span class="badge badge-focus star-btn"onclick="event.stopPropagation();toggleStar('${s.id}')" title="Pin session">${starredSessions.has(s.id) ? '&#x2B50;' : '&#x2606;'}</span>
              </div>
            </div>
          </div>`;

      html += `
          <div class="restart-row">
            <span class="restart-cmd" title="${esc(s.restart_cmd)}">${esc(s.restart_cmd)}</span>
            <button class="copy-btn" onclick="copyCmd(this, '${esc(s.restart_cmd)}')">&#x1F4CB; Copy</button>
            <button class="copy-btn" onclick="event.stopPropagation();navigator.clipboard.writeText('${s.id}');this.textContent='✓';setTimeout(()=>this.textContent='🪪',1200)" title="Copy session ID">&#x1FA96;</button>
            ${isRunning ? `<button class="focus-btn" onclick="focusSession('${s.id}')">&#x1F4FA; Focus</button>` : ''}
          </div>
          <div class="session-detail" id="detail-${s.id}"></div>
        </div>`;
    }
    html += '</div></div>';
  }
  panel.innerHTML = html;

  // Restore cached detail HTML for expanded sessions
  expandedSessionIds.forEach(id => {
    const detail = document.getElementById('detail-' + id);
    if (detail && loadedDetails[id]) {
      detail.innerHTML = loadedDetails[id];
    } else if (detail && expandedSessionIds.has(id)) {
      // Re-fetch if no cache
      loadDetail(id);
    }
  });
}

function toggleGroup(el, gid) {
  el.classList.toggle('collapsed');
  if (el.classList.contains('collapsed')) {
    collapsedGroups.add(gid);
  } else {
    collapsedGroups.delete(gid);
  }
}

// ===== INTERACTIONS =====
async function toggleDetail(id) {
  const card = document.querySelector(`.session-card[data-id="${id}"]`);
  if (!card) return;
  const wasExpanded = card.classList.contains('expanded');

  // Collapse all in same panel, update tracking
  card.closest('.tab-panel').querySelectorAll('.session-card.expanded').forEach(c => {
    c.classList.remove('expanded');
    expandedSessionIds.delete(c.dataset.id);
  });
  if (wasExpanded) return;

  card.classList.add('expanded');
  expandedSessionIds.add(id);
  await loadDetail(id);
}

async function loadDetail(id) {
  const detail = document.getElementById('detail-' + id);
  if (!detail) return;
  detail.innerHTML = '<div class="loading">Loading...</div>';

  try {
    const resp = await fetch('/api/session/' + id);
    const data = await resp.json();
    let html = '';

    if (data.checkpoints && data.checkpoints.length) {
      html += '<div class="detail-section"><h3>&#x1F3C1; Checkpoints</h3>';
      data.checkpoints.forEach((cp, i) => {
        const did = `cp-list-${id}-${i}`;
        html += `<div class="cp-item" onclick="const d=document.getElementById('${did}');d.style.display=d.style.display==='none'?'':'none'">
          <strong>#${cp.checkpoint_number}: ${esc(cp.title || 'Checkpoint')}</strong>
          <div id="${did}" style="display:none">
            ${cp.overview ? `<div class="cp-body">${esc(cp.overview)}</div>` : ''}
            ${cp.next_steps ? `<div class="cp-body" style="margin-top:4px;color:var(--yellow)"><strong>Next:</strong> ${esc(cp.next_steps)}</div>` : ''}
          </div>
        </div>`;
      });
      html += '</div>';
    }

    if (data.refs && data.refs.length) {
      html += '<div class="detail-section"><h3>&#x1F517; References</h3><div class="file-list">';
      data.refs.forEach(r => { html += `<span class="ref-tag">${esc(r.ref_type)}: ${esc(r.ref_value)}</span>`; });
      html += '</div></div>';
    }

    if (data.recent_output && data.recent_output.length) {
      html += '<div class="detail-section"><h3>&#x1F4DF; Recent Output</h3>';
      html += '<pre style="background:var(--surface2);border-radius:6px;padding:12px;font-size:13px;font-family:\'Cascadia Code\',\'Fira Code\',monospace;color:var(--text2);overflow-x:auto;white-space:pre-wrap;max-height:300px;overflow-y:auto">';
      data.recent_output.forEach(line => { html += esc(line) + '\n'; });
      html += '</pre></div>';
    }

    if (data.turns && data.turns.length) {
      html += '<div class="detail-section"><h3>&#x1F4AC; Conversation (last 10)</h3>';
      data.turns.forEach(t => {
        const u = (t.user_message || '').substring(0, 250);
        const a = (t.assistant_response || '').substring(0, 250);
        html += `<div class="turn-item">
          <div class="turn-user">&#x1F464; ${esc(u)}${t.user_message && t.user_message.length > 250 ? '...' : ''}</div>
          <div class="turn-assistant">&#x1F916; ${esc(a)}${t.assistant_response && t.assistant_response.length > 250 ? '...' : ''}</div>
        </div>`;
      });
      html += '</div>';
    }

    html += buildToolCountsHtml(data);

    if (!html) html = '<div class="empty">No additional details for this session.</div>';
    loadedDetails[id] = html;
    detail.innerHTML = html;
  } catch(e) {
    detail.innerHTML = '<div class="empty">Error loading details.</div>';
  }
}

function buildToolCountsHtml(data) {
  if (!data.tool_counts || !data.tool_counts.length) return '';
  const maxCount = data.tool_counts[0].count;
  let h = '<div class="detail-section"><h3>&#x1F527; Tools used</h3>';
  data.tool_counts.forEach(t => {
    const pct = Math.round((t.count / maxCount) * 100);
    h += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:13px">
      <span style="min-width:160px;font-family:monospace;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(t.name)}</span>
      <div style="flex:1;height:8px;background:var(--surface2);border-radius:4px"><div style="width:${pct}%;height:100%;background:var(--accent);border-radius:4px"></div></div>
      <span style="min-width:30px;text-align:right;color:var(--text)">${t.count}</span>
    </div>`;
  });
  h += '</div>';
  return h;
}

function copyCmd(btn, cmd) {
  navigator.clipboard.writeText(cmd).then(() => {
    btn.innerHTML = '&#x2705; Copied';
    btn.classList.add('copied');
    setTimeout(() => { btn.innerHTML = '&#x1F4CB; Copy'; btn.classList.remove('copied'); }, 2000);
  });
}
function copyTileCmd(btn, cmd) {
  navigator.clipboard.writeText(cmd).then(() => {
    const prev = btn.innerHTML;
    btn.innerHTML = '&#x2705;';
    setTimeout(() => { btn.innerHTML = prev; }, 2000);
  });
}

async function focusSession(sid) {
  try {
    const resp = await fetch('/api/focus/' + sid, { method: 'POST' });
    const data = await resp.json();
    if (!data.success) { console.warn('Focus failed:', data.message); }
  } catch(e) { console.error('Focus error:', e); }
}

async function killSession(sid, pid) {
  if (!confirm(`Kill process PID ${pid}?`)) return;
  try {
    const resp = await fetch('/api/kill/' + encodeURIComponent(sid), { method: 'POST' });
    if (!resp.ok && resp.headers.get('content-type')?.indexOf('application/json') === -1) {
      alert(`Failed to kill process: server returned ${resp.status}`); return;
    }
    const data = await resp.json();
    if (!data.success) alert('Failed to kill process: ' + data.message);
  } catch(e) { alert('Error: ' + e.message); }
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ===== TILE RENDERING =====
function renderTilePanel(panelId, sessions, isActive) {
  const panel = document.getElementById(panelId);
  if (!sessions.length) {
    panel.innerHTML = `<div class="empty">${isActive ? 'No active sessions detected.' : 'No previous sessions.'}</div>`;
    return;
  }

  const stateIcons = { waiting: '&#x23F3;', working: '&#x2692;&#xFE0F;', thinking: '&#x1F914;', idle: '&#x1F535;', unknown: '' };
  const stateCls = { waiting: 'waiting-tile', working: 'active-tile', thinking: 'active-tile', idle: 'idle-tile', unknown: '' };

  let html = '<div class="tile-grid">';
  // Sort: starred first
  const sortedSessions = [...sessions].sort((a, b) => (starredSessions.has(b.id) ? 1 : 0) - (starredSessions.has(a.id) ? 1 : 0));
  for (const s of sortedSessions) {
    const isRunning = !!runningPids[s.id];
    const pinfo = isRunning ? (runningPids[s.id] || {}) : {};
    const state = isRunning ? (pinfo.state || 'unknown') : '';
    const isWaiting = isRunning && state === 'waiting';
    const isIdle = isRunning && state === 'idle';
    const tileClass = isRunning ? (stateCls[state] || '') : '';

    html += `
      <div class="tile-card ${tileClass}" onclick="openTileDetail('${s.id}', '${esc(s.summary || '(Untitled)')}')">
        <div class="tile-subtitle" style="font-size:11px;opacity:0.7">started ${esc(s.created_ago)}</div>
        <div class="tile-top">
          ${isRunning ? `<span class="live-dot ${isWaiting ? 'waiting' : (isIdle ? 'idle' : '')}" style="flex-shrink:0"></span>` : ''}
          <div class="tile-title">${isRunning && s.intent ? '&#x1F916; ' + esc(s.intent) : esc(s.summary || '(Untitled session)')}</div>
          ${isRunning && pinfo.yolo ? `<span class="badge badge-yolo" style="flex-shrink:0">&#x1F525;</span>` : ''}
        </div>
        ${isRunning && s.intent ? `<div class="tile-subtitle" style="opacity:0.7">${esc(s.summary || '')}</div>` : ''}
        ${s.branch ? `<div class="tile-subtitle"><span class="branch-badge">&#x2387; ${s.repository ? esc(s.repository) + ' / ' : ''}${esc(s.branch)}</span></div>` : ''}
        ${s.recent_activity ? `<div class="tile-subtitle" style="color:var(--accent)">${esc(s.recent_activity)}</div>` : ''}
        ${isWaiting && pinfo.waiting_context ? `<div class="tile-subtitle" style="color:var(--yellow)">${esc(pinfo.waiting_context.substring(0, 80))}${pinfo.waiting_context.length > 80 ? '...' : ''}</div>` : ''}
        <div class="tile-meta">
          ${isRunning && state ? `<span class="badge ${({'waiting':'badge-waiting','working':'badge-working','thinking':'badge-thinking','idle':'badge-idle'})[state] || 'badge-active'}">${stateIcons[state] || ''} ${state}</span>` : ''}
          ${isRunning && pinfo.bg_tasks ? `<span class="badge badge-bg">&#x2699;&#xFE0F; ${pinfo.bg_tasks} bg</span>` : ''}
          <span class="badge badge-turns">&#x1F4AC; ${s.turn_count}</span>
          ${s.mcp_servers && s.mcp_servers.length ? s.mcp_servers.map(m => `<span class="badge badge-mcp">&#x1F50C; ${esc(m)}</span>`).join('') : ''}
          ${isRunning ? `<span class="badge badge-focus"onclick="event.stopPropagation(); focusSession('${s.id}')" title="Focus terminal window">&#x1F4FA;</span>` : ''}
          <span class="badge badge-focus" onclick="event.stopPropagation(); copyTileCmd(this, '${esc(s.restart_cmd)}')" title="Copy resume command">&#x1F4CB;</span>
          <span class="badge badge-focus" onclick="event.stopPropagation();navigator.clipboard.writeText('${s.id}');this.textContent='✓';setTimeout(()=>this.textContent='🪪',1200)" title="Copy session ID">&#x1FA96;</span>
          <span class="badge badge-focus star-btn" onclick="event.stopPropagation();toggleStar('${s.id}')" title="Pin session">${starredSessions.has(s.id) ? '&#x2B50;' : '&#x2606;'}</span>
        </div>
        ${isRunning && pinfo.pid ? `<div class="tile-pid-kill" onclick="event.stopPropagation()">PID ${pinfo.pid} <span class="tile-kill-x" onclick="killSession('${s.id}', ${pinfo.pid})" title="Kill process">✕</span></div>` : ''}
      </div>`;
  }
  html += '</div>';
  panel.innerHTML = html;
}

async function openTileDetail(id, title) {
  document.getElementById('detail-modal-title').innerHTML = esc(title);
  const body = document.getElementById('detail-modal-body');
  body.innerHTML = '<div class="loading">Loading...</div>';
  document.getElementById('detail-modal').classList.add('open');

  try {
    const resp = await fetch('/api/session/' + id);
    const data = await resp.json();
    let html = '';

    if (data.checkpoints && data.checkpoints.length) {
      html += '<div class="detail-section"><h3>&#x1F3C1; Checkpoints</h3>';
      data.checkpoints.forEach((cp, i) => {
        const did = `cp-tile-${id}-${i}`;
        html += `<div class="cp-item" onclick="const d=document.getElementById('${did}');d.style.display=d.style.display==='none'?'':'none'">
          <strong>#${cp.checkpoint_number}: ${esc(cp.title || 'Checkpoint')}</strong>
          <div id="${did}" style="display:none">
            ${cp.overview ? `<div class="cp-body">${esc(cp.overview)}</div>` : ''}
            ${cp.next_steps ? `<div class="cp-body" style="margin-top:4px;color:var(--yellow)"><strong>Next:</strong> ${esc(cp.next_steps)}</div>` : ''}
          </div>
        </div>`;
      });
      html += '</div>';
    }

    if (data.refs && data.refs.length) {
      html += '<div class="detail-section"><h3>&#x1F517; References</h3><div class="file-list">';
      data.refs.forEach(r => { html += `<span class="ref-tag">${esc(r.ref_type)}: ${esc(r.ref_value)}</span>`; });
      html += '</div></div>';
    }

    if (data.recent_output && data.recent_output.length) {
      html += '<div class="detail-section"><h3>&#x1F4DF; Recent Output</h3>';
      html += '<pre style="background:var(--surface2);border-radius:6px;padding:12px;font-size:13px;font-family:\'Cascadia Code\',\'Fira Code\',monospace;color:var(--text2);overflow-x:auto;white-space:pre-wrap;max-height:300px;overflow-y:auto">';
      data.recent_output.forEach(line => { html += esc(line) + '\n'; });
      html += '</pre></div>';
    }

    if (data.turns && data.turns.length) {
      html += '<div class="detail-section"><h3>&#x1F4AC; Conversation (last 10)</h3>';
      data.turns.forEach(t => {
        const u = (t.user_message || '').substring(0, 250);
        const a = (t.assistant_response || '').substring(0, 250);
        html += `<div class="turn-item">
          <div class="turn-user">&#x1F464; ${esc(u)}${t.user_message && t.user_message.length > 250 ? '...' : ''}</div>
          <div class="turn-assistant">&#x1F916; ${esc(a)}${t.assistant_response && t.assistant_response.length > 250 ? '...' : ''}</div>
        </div>`;
      });
      html += '</div>';
    }

    html += buildToolCountsHtml(data);

    if (!html) html = '<div class="empty">No additional details for this session.</div>';
    body.innerHTML = html;
  } catch(e) {
    body.innerHTML = '<div class="empty">Error loading details.</div>';
  }
}

function closeDetailModal() {
  document.getElementById('detail-modal').classList.remove('open');
}

// ===== SEARCH =====
document.getElementById('search').addEventListener('input', () => render());

// ===== POLLING =====
// Active sessions: refresh process list every 5s
// Full session list: refresh every 30s
fetchSessions();
const validTabs = ['active', 'previous', 'timeline', 'files'];
const hashTab = location.hash.replace('#', '');
if (validTabs.includes(hashTab)) switchTab(hashTab);
initView();
updateNotifBtn();
activeTimer = setInterval(fetchProcesses, 5000);
previousTimer = setInterval(fetchSessions, 30000);

fetch('/api/server-info').then(r => r.json()).then(d => {
  const el = document.getElementById('server-pid');
  if (el) el.textContent = `server PID ${d.pid}`;
});
