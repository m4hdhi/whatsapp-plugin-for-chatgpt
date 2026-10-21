'use strict';

// The local dashboard token is passed only in the URL fragment on first launch.
// It never goes into query strings, rendered markup, or localStorage.
const TOKEN_KEY = 'groupbrief.session';
const HOSTED = document.body.dataset.hosted === 'true';
const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';
const app = document.getElementById('app');
const toastNode = document.getElementById('toast');
let token = HOSTED ? 'cookie-session' : sessionStorage.getItem(TOKEN_KEY) || '';
const fragment = new URLSearchParams(window.location.hash.slice(1));
if (!HOSTED && fragment.has('token')) {
  token = fragment.get('token') || '';
  sessionStorage.setItem(TOKEN_KEY, token);
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
}
let state = null;
let activeView = 'overview';
let taskFilter = 'open';
let errorMessage = '';
let chatsCache = null;
let chatQuery = '';
let chatDraft = null;
let chatsDirty = false;
let chatsError = '';
let chatsInFlight = false;
let chatsFetchPromise = null;
let settingsDirty = false;
let refreshInProgress = false;
let qrRequested = false;
let qrImage = null;
let qrError = '';
let qrInFlight = false;
let qrRequestVersion = 0;
let toastTimer = null;
let connectInProgress = false;
const busyActions = new Set();

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function icon(name) {
  const shapes = {
    document: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8.5 8h7M8.5 12h7M8.5 16h3"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="m7.5 12 3 3 6-6"/>',
    group: '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v2"/>',
    alert: '<path d="m10.2 4.3-8 14A1.7 1.7 0 0 0 3.7 21h16.6a1.7 1.7 0 0 0 1.5-2.7l-8-14a2 2 0 0 0-3.6 0Z"/><path d="M12 9v4m0 4h.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/>',
  };
  const wrap = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  wrap.setAttribute('viewBox', '0 0 24 24');
  wrap.setAttribute('aria-hidden', 'true');
  wrap.setAttribute('class', 'icon');
  // Icon paths are fixed application code, never API content.
  wrap.innerHTML = shapes[name] || shapes.document;
  return wrap;
}

function button(text, handler, kind = '', extraClass = '') {
  const node = el('button', `button ${kind} ${extraClass}`.trim(), text);
  node.type = 'button';
  if (handler) node.addEventListener('click', () => handler(node));
  return node;
}

function textButton(text, handler) {
  const node = el('button', 'text-button', text);
  node.type = 'button';
  node.addEventListener('click', () => handler(node));
  return node;
}

function externalLink(label, href) {
  const node = el('a', '', label);
  node.href = href;
  node.target = '_blank';
  node.rel = 'noopener noreferrer';
  return node;
}

function showToast(message) {
  clearTimeout(toastTimer);
  toastNode.textContent = message;
  toastNode.hidden = false;
  toastTimer = setTimeout(() => { toastNode.hidden = true; }, 8000);
}

function readableError(error) {
  return error instanceof Error ? error.message : String(error || 'Something went wrong. Please try again.');
}

async function api(path, options = {}) {
  const headers = { ...(HOSTED ? { 'X-CSRF-Token': CSRF } : { Authorization: `Bearer ${token}` }), ...options.headers };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { ...options, headers, cache: 'no-store' });
  if (response.status === 401 || response.status === 403) {
    if (HOSTED) {
      if (response.status === 401) window.location.assign('/login');
      throw new Error('Your session expired or permission was denied. Refresh this page and sign in again.');
    }
    token = '';
    sessionStorage.removeItem(TOKEN_KEY);
    showLogin('The dashboard token was not accepted. Use the access link from your launcher.');
    throw new Error('The dashboard token was not accepted.');
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}). Please try again.`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch (_) { /* Keep the useful HTTP fallback for non-JSON failures. */ }
    throw new Error(message);
  }
  if (response.status === 204) return {};
  if (options.asText) return response.text();
  return response.json();
}

async function action(key, node, workingLabel, operation) {
  if (busyActions.has(key)) return;
  busyActions.add(key);
  const original = node ? node.textContent : '';
  if (node) { node.disabled = true; node.textContent = workingLabel; }
  try {
    await operation();
  } catch (error) {
    if (token) {
      errorMessage = readableError(error);
      updateAlerts();
      document.getElementById('alerts')?.scrollIntoView({ block: 'nearest' });
    }
  } finally {
    busyActions.delete(key);
    if (node?.isConnected) { node.disabled = false; node.textContent = original; }
    if (key === 'connect') syncConnectButton();
    if (['save-chats', 'pause-monitoring'].includes(key)) syncChatControls();
  }
}

function isConnected() {
  const status = String(state?.connection?.status || '').toLowerCase();
  return ['working', 'connected', 'authenticated', 'ready'].includes(status);
}

function connectionState() {
  return String(state?.connection?.status || '').toLowerCase();
}

function connectButtonLabel() {
  return qrRequested || connectionState() === 'failed' ? 'Refresh QR code' : 'Connect WhatsApp';
}

function syncConnectButton() {
  const node = document.getElementById('connect-whatsapp');
  if (!node) return;
  node.disabled = busyActions.has('connect') || connectInProgress;
  node.textContent = node.disabled ? 'Connecting…' : connectButtonLabel();
}

function applyConnectionResponse(result) {
  if (!state || typeof result.status !== 'string') return;
  const wasConnected = isConnected();
  state.connection = { ...state.connection, status: result.status };
  if (typeof result.last_seen === 'string') state.connection.last_seen = result.last_seen;
  if (Object.hasOwn(result, 'error')) state.connection.error = result.error || null;
  else if (isConnected() || ['starting', 'scan_qr_code'].includes(connectionState())) state.connection.error = null;
  if (isConnected()) {
    qrImage = null;
    qrRequested = false;
    qrError = '';
  }
  updateHeader();
  const panel = document.querySelector('.connection-panel');
  if (panel && activeView === 'overview') panel.replaceWith(connectionPanel());
  refreshChatsOnConnection(wasConnected);
}

function connectionLabel() {
  if (isConnected()) return 'WhatsApp connected';
  const status = String(state?.connection?.status || '').toLowerCase();
  if (status.includes('scan') || status.includes('qr')) return 'Ready to scan';
  if (['starting', 'connecting', 'opening'].includes(status)) return 'Connecting';
  if (status.includes('fail') || status.includes('error')) return 'Connection needs attention';
  return 'Not connected';
}

function dateText(value, includeTime = true) {
  if (!value) return 'No deadline given';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const options = { month: 'short', day: 'numeric', ...(includeTime ? { hour: 'numeric', minute: '2-digit' } : {}) };
  if (state?.settings?.timezone) options.timeZone = state.settings.timezone;
  try { return new Intl.DateTimeFormat(undefined, options).format(date); }
  catch (_) { delete options.timeZone; return new Intl.DateTimeFormat(undefined, options).format(date); }
}

function brand() {
  const node = el('a', 'brand');
  node.href = '#';
  node.setAttribute('aria-label', HOSTED ? 'WhatsApp overview' : 'GroupBrief overview');
  if (HOSTED) {
    const logo = el('img');
    logo.src = '/cloud-static/whatsapp.png';
    logo.width = 32; logo.height = 32; logo.alt = '';
    node.append(logo, document.createTextNode('WhatsApp'));
  } else node.append(el('span', 'brand-mark'), document.createTextNode('GroupBrief'));
  node.firstChild.setAttribute('aria-hidden', 'true');
  node.addEventListener('click', event => { event.preventDefault(); if (state) switchView('overview'); });
  return node;
}

function renderShell() {
  app.replaceChildren();
  const header = el('header', 'header');
  const headerInner = el('div', 'header-inner');
  headerInner.append(brand());
  const nav = el('nav', 'nav');
  nav.setAttribute('aria-label', 'Main views');
  nav.setAttribute('role', 'tablist');
  const views = ['overview', 'tasks', 'chats', 'settings'];
  views.forEach(view => {
    const tab = el('button', '', view[0].toUpperCase() + view.slice(1));
    tab.type = 'button';
    tab.id = `tab-${view}`;
    tab.dataset.view = view;
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-controls', 'main');
    tab.setAttribute('aria-selected', view === activeView ? 'true' : 'false');
    tab.tabIndex = view === activeView ? 0 : -1;
    tab.addEventListener('click', () => switchView(view));
    tab.addEventListener('keydown', event => {
      let index = views.indexOf(view);
      if (event.key === 'ArrowRight') index = (index + 1) % views.length;
      else if (event.key === 'ArrowLeft') index = (index + views.length - 1) % views.length;
      else if (event.key === 'Home') index = 0;
      else if (event.key === 'End') index = views.length - 1;
      else return;
      event.preventDefault();
      switchView(views[index]);
      document.getElementById(`tab-${views[index]}`)?.focus();
    });
    nav.append(tab);
  });
  headerInner.append(nav);
  const status = el('div', 'connection-status');
  status.id = 'connection-status';
  headerInner.append(status);
  if (HOSTED) {
    const account = el('a', 'text-button', 'Account');
    account.href = '/account';
    headerInner.append(account);
  }
  header.append(headerInner);
  const main = el('main', 'page');
  main.id = 'main';
  main.tabIndex = -1;
  main.setAttribute('role', 'tabpanel');
  main.setAttribute('aria-labelledby', `tab-${activeView}`);
  const alerts = el('div');
  alerts.id = 'alerts';
  alerts.setAttribute('aria-live', 'polite');
  const content = el('div');
  content.id = 'content';
  main.append(alerts, content);
  const footer = el('footer', 'footer');
  const footerInner = el('div', 'footer-inner');
  footerInner.append(document.createTextNode('Private by default. Chat reading and AI processing require your permission.'), HOSTED ? externalLink('Made by Mahdhi', 'https://www.linkedin.com/in/m4hdhi/') : el('span', '', 'GroupBrief · Local assistant'));
  footer.append(footerInner);
  app.append(header, main, footer);
  updateHeader();
  updateAlerts();
  renderContent();
}

function updateHeader() {
  const node = document.getElementById('connection-status');
  if (!node) return;
  node.className = `connection-status${isConnected() ? ' connected' : state?.connection?.error ? ' connection-error' : ''}`;
  node.replaceChildren(el('span', 'status-dot'), document.createTextNode(connectionLabel()));
  node.firstChild.setAttribute('aria-hidden', 'true');
}

function alertBox(message, type = '', dismissable = false) {
  const node = el('div', `alert ${type}`.trim());
  node.append(icon('alert'));
  const body = el('div');
  body.append(el('p', '', message));
  node.append(body);
  if (dismissable) {
    const dismiss = el('button', '', '×');
    dismiss.type = 'button';
    dismiss.setAttribute('aria-label', 'Dismiss error');
    dismiss.addEventListener('click', () => { errorMessage = ''; updateAlerts(); });
    node.append(dismiss);
  }
  return node;
}

function updateAlerts() {
  const container = document.getElementById('alerts');
  if (!container) return;
  const signature = JSON.stringify([Boolean(state?.demo), errorMessage, state?.errors || [], state?.settings?.processing_consent, monitoringAllowed()]);
  if (container.dataset.signature === signature) return;
  container.dataset.signature = signature;
  container.replaceChildren();
  if (state?.demo) container.append(el('div', 'demo-banner', 'Demo mode · Sample messages and tasks for a preview. WhatsApp and paid AI services are not connected.'));
  if (!monitoringAllowed()) {
    const paused = alertBox(monitoringEnabled()
      ? 'Monitoring paused. Choose chats in your scope before GroupBrief reads messages.'
      : 'Monitoring paused. Choose your chats and give permission in Chats before GroupBrief reads messages.', 'info');
    paused.querySelector('div').append(textButton('Review chat permissions →', () => switchView('chats')));
    container.append(paused);
  }
  if (errorMessage) container.append(alertBox(errorMessage, '', true));
  for (const error of (state?.errors || []).slice(0, 3)) {
    const text = typeof error === 'string' ? error : error.message || error.detail || error.error || '';
    if (text && text !== errorMessage) container.append(alertBox(text));
  }
}

function switchView(view) {
  if (view === activeView && document.getElementById('content')) return;
  if ((settingsDirty || chatsDirty) && !window.confirm('You have unsaved changes. Leave this view without saving?')) return;
  activeView = view;
  if (view !== 'chats') { chatDraft = null; chatsDirty = false; chatQuery = ''; }
  if (view !== 'settings') settingsDirty = false;
  document.querySelectorAll('.nav [role="tab"]').forEach(tab => {
    const selected = tab.dataset.view === view;
    tab.setAttribute('aria-selected', selected ? 'true' : 'false');
    tab.tabIndex = selected ? 0 : -1;
  });
  document.getElementById('main')?.setAttribute('aria-labelledby', `tab-${view}`);
  renderContent();
}

function renderContent() {
  const content = document.getElementById('content');
  if (!content || !state) return;
  content.replaceChildren();
  if (activeView === 'overview') renderOverview(content);
  if (activeView === 'tasks') renderTasks(content);
  if (activeView === 'chats') renderChats(content);
  if (activeView === 'settings') renderSettings(content);
}

function pageHeading(title, description, actionNode) {
  const node = el('div', 'page-heading');
  const text = el('div');
  text.append(el('h1', '', title), el('p', '', description));
  node.append(text);
  if (actionNode) node.append(actionNode);
  return node;
}

function sectionHeader(title, subtitle) {
  const node = el('div', 'section-heading');
  node.append(el('h2', '', title));
  if (subtitle) node.append(el('p', '', subtitle));
  return node;
}

function emptyState(symbol, title, description, actionNode) {
  const node = el('div', 'empty');
  node.append(icon(symbol), el('h3', '', title), el('p', '', description));
  if (actionNode) node.append(actionNode);
  return node;
}

function analyzeButton() {
  const apiMode = state.settings?.background_analysis_enabled && state.configured?.openai;
  const node = button(apiMode ? 'Analyze now (API)' : 'Refresh messages', node => action('analyze', node, 'Checking…', async () => {
    const result = await api(apiMode ? '/api/analyze' : '/api/refresh-messages', { method: 'POST' });
    showToast(result.message || (result.status === 'running' ? 'A check is already in progress.' : 'Check requested. Your brief will update when processing finishes.'));
    await refreshState(true);
  }));
  node.disabled = busyActions.has('analyze') || !monitoringAllowed();
  if (!monitoringAllowed()) node.title = 'Choose chats and give permission in Chats first.';
  return node;
}

function renderOverview(content) {
  const layout = el('div', 'overview-grid');
  const main = el('div', 'overview-main');
  main.append(pageHeading('Your chats, caught up.', 'Important updates and commitments, in one quiet place.', analyzeButton()));
  if (!state.settings?.background_analysis_enabled) {
    main.append(el('p', 'hint spaced', `ChatGPT mode · No API key required. ${state.stats?.messages_pending || 0} messages await optional API analysis. In ChatGPT, select WhatsApp and ask “What needs my attention?” Enable message sharing in Settings first. Conversation analysis appears in ChatGPT; it does not save tasks or schedule reminders here.`));
  }
  const summaries = el('section', 'section');
  summaries.append(sectionHeader('Recent updates', state.settings?.monitoring_mode === 'all' ? 'All chats, except your exclusions' : 'Your selected chats'));
  const items = state.summaries || [];
  if (items.length) items.slice(0, 8).forEach(summary => summaries.append(summaryRow(summary)));
  else summaries.append(emptyState('document', 'Ask ChatGPT for your first brief.', 'Connect WhatsApp, permit chats, and enable message sharing in Settings. Then ask ChatGPT to summarize them. Saved dashboard briefs are available with optional API analysis.', textButton('Open settings →', () => switchView('settings'))));
  main.append(summaries);
  const tasks = el('section', 'section');
  tasks.append(el('h2', '', 'Upcoming tasks'));
  const openTasks = (state.tasks || []).filter(task => task.status === 'open');
  if (openTasks.length) {
    openTasks.slice(0, 5).forEach(task => tasks.append(taskRow(task)));
    tasks.append(textButton('View all tasks →', () => switchView('tasks')));
  } else tasks.append(emptyState('check', 'A little less to remember.', 'Your commitments and deadlines from permitted chats will appear here, with the original message attached.'));
  main.append(tasks);
  if (state.stats?.last_analysis) {
    const lastCheck = el('p', 'last-check', `Last checked ${dateText(state.stats.last_analysis)} · ${state.settings?.timezone || 'Local time'}`);
    lastCheck.id = 'last-check';
    main.append(lastCheck);
  }
  layout.append(main, connectionPanel());
  content.append(layout);
}

function summaryRow(summary) {
  const row = el('article', 'list-row');
  const meta = el('div', 'row-meta');
  meta.append(el('span', 'group-name', summary.chat_name || summary.group_name || 'Monitored chat'));
  appendChatType(meta, summary);
  meta.append(el('span', '', dateText(summary.created_at)));
  row.append(meta, el('p', 'summary-text', summary.text || ''), evidenceDetails(summary));
  return row;
}

function evidenceDetails(item) {
  const details = el('details', 'evidence');
  const evidence = item.evidence || [];
  const sourceCount = evidence.length || (item.source_ids || []).length;
  details.append(el('summary', '', sourceCount ? `View source messages (${sourceCount})` : 'Source messages'));
  const body = el('div', 'evidence-content');
  if (!evidence.length) body.append(el('p', '', 'The source text is no longer available. It may have been removed by the retention setting.'));
  evidence.forEach(message => {
    const meta = el('div', 'row-meta');
    meta.append(el('strong', '', message.sender || 'Chat participant'), el('span', '', dateText(message.timestamp)));
    body.append(meta, el('p', '', message.body || '(No readable text)'));
  });
  details.append(body);
  return details;
}

function taskRow(task) {
  const row = el('article', 'list-row');
  const body = el('div', 'task-body');
  const marker = el('span', 'task-marker');
  marker.setAttribute('aria-hidden', 'true');
  const details = el('div', 'task-details');
  const meta = el('div', 'row-meta');
  meta.append(el('span', 'group-name', task.chat_name || task.group_name || 'Monitored chat'));
  appendChatType(meta, task);
  if (task.needs_review) meta.append(el('span', 'review-tag', 'Needs your review'));
  if (task.status === 'done') meta.append(el('span', 'done-tag', 'Completed'));
  if (task.status === 'dismissed') meta.append(el('span', 'muted', 'Dismissed'));
  details.append(meta, el('h3', '', task.title || 'Untitled task'));
  details.append(el('div', 'task-time', task.due_at ? `Due ${dateText(task.due_at)}` : 'No deadline given'));
  if (task.reminder_at && task.status === 'open') details.append(el('div', 'task-time', `Reminder ${dateText(task.reminder_at)}`));
  details.append(evidenceDetails(task));
  const actions = el('div', 'task-actions');
  const mutate = (node, payload, label) => action(`task-${task.id}`, node, 'Saving…', async () => {
    await api(`/api/tasks/${encodeURIComponent(task.id)}`, { method: 'PATCH', body: JSON.stringify(payload) });
    showToast(label);
    await refreshState(true);
  });
  if (task.status === 'open') {
    actions.append(button('Mark done', node => mutate(node, { status: 'done' }, 'Task completed.'), 'secondary', 'small'));
    if (task.due_at && !task.needs_review) actions.append(button('Snooze 1 hour', node => mutate(node, { snooze_minutes: 60 }, 'Reminder snoozed for one hour.'), 'tertiary', 'small'));
    if (task.needs_review) actions.append(button('Review deadline', node => {
      const existing = details.querySelector('.deadline-form');
      if (existing) { existing.hidden = !existing.hidden; if (!existing.hidden) existing.querySelector('input').focus(); return; }
      details.append(deadlineForm(task, mutate));
      details.querySelector('.deadline-form input').focus();
    }, 'tertiary', 'small'));
    actions.append(button('Dismiss', node => mutate(node, { status: 'dismissed' }, 'Task dismissed.'), 'tertiary', 'small'));
  } else actions.append(button('Reopen task', node => mutate(node, { status: 'open' }, 'Task reopened.'), 'secondary', 'small'));
  details.append(actions);
  body.append(marker, details);
  row.append(body);
  return row;
}

function deadlineForm(task, mutate) {
  const form = el('form', 'deadline-form spaced');
  const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'this browser’s local time';
  const field = makeField('deadline', `Confirm deadline (${localZone})`, 'datetime-local', '', { required: true });
  const input = field.querySelector('input');
  if (task.due_at) {
    const date = new Date(task.due_at);
    if (!Number.isNaN(date.getTime())) {
      const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
      input.value = local.toISOString().slice(0, 16);
    }
  }
  const save = button('Confirm deadline', null, 'secondary', 'small');
  save.type = 'submit';
  form.append(field, el('p', 'hint', 'Check the original message above. Use Dismiss if this task is not yours.'), save);
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const date = new Date(input.value);
    if (Number.isNaN(date.getTime())) { input.setCustomValidity('Choose a valid date and time.'); input.reportValidity(); return; }
    mutate(save, { due_at: date.toISOString(), needs_review: false }, 'Deadline confirmed.');
  });
  input.addEventListener('input', () => input.setCustomValidity(''));
  return form;
}

function connectionPanel() {
  const panel = el('aside', 'connection-panel');
  panel.setAttribute('aria-label', 'WhatsApp connection');
  panel.append(el('h2', '', isConnected() ? 'WhatsApp is connected.' : 'Connect WhatsApp'));
  if (isConnected()) {
    const connected = el('div', 'connected-panel');
    connected.append(icon('check'), el('h3', '', 'Ready for your next brief.'));
    const count = state.stats?.monitored_chats ?? savedChats().length;
    const scope = state.settings?.monitoring_mode === 'all'
      ? 'All normal private and group chats are included, except your exclusions.'
      : count ? `${count} selected ${count === 1 ? 'chat' : 'chats'} will be checked automatically.` : 'Choose the chats you want GroupBrief to follow.';
    connected.append(el('p', '', monitoringEnabled() ? scope : 'Monitoring is paused. Choose chats and allow processing to start your brief.'));
    if (state.connection?.last_seen) {
      const lastSeen = el('p', '', `Last seen ${dateText(state.connection.last_seen)}`);
      lastSeen.id = 'last-seen';
      connected.append(lastSeen);
    }
    panel.append(connected, button('Choose chats', () => switchView('chats'), 'secondary'));
  } else {
    panel.append(el('p', '', 'Scan the QR code with WhatsApp to link your account. Chat reading starts only after you allow it in Chats.'));
    const qr = el('div', 'qr-box');
    qr.id = 'qr-box';
    panel.append(qr);
    updateQrBox(qr);
    const connect = button(connectButtonLabel(), node => action('connect', node, 'Connecting…', async () => {
      connectInProgress = true;
      qrRequestVersion += 1;
      qrImage = null;
      qrError = '';
      updateQrBox();
      try {
        const result = await api('/api/connect', { method: 'POST' });
        qrRequested = true;
        errorMessage = '';
        updateAlerts();
        applyConnectionResponse(result);
        await refreshQr();
        if (qrImage && !isConnected()) showToast('Open Linked devices in WhatsApp on your phone to scan the QR code.');
      } finally { connectInProgress = false; }
    }), 'secondary');
    connect.id = 'connect-whatsapp';
    connect.disabled = busyActions.has('connect') || connectInProgress;
    panel.append(connect);
    const steps = el('ol', 'steps');
    ['Open WhatsApp on your phone', 'iPhone: Settings → Linked Devices. Android: menu → Linked devices', 'Link a Device, then scan the QR'].forEach(text => steps.append(el('li', '', text)));
    panel.append(steps);
    if (state.connection?.error) panel.append(el('p', 'connection-error-text', state.connection.error));
  }
  panel.append(el('p', 'connection-note', HOSTED ? 'Monitoring requires the hosted service to stay running. Pair using WhatsApp → Linked devices on your phone. To scan the QR, display this page on another screen. This is an unofficial linked-device bridge.' : 'Your PC needs to stay on. This uses an unofficial linked-device bridge.'));
  return panel;
}

function updateQrBox(qr = document.getElementById('qr-box')) {
  if (!qr) return;
  qr.replaceChildren();
  qr.className = `qr-box${qrImage ? ' has-qr' : ''}`;
  if (qrImage) {
    const image = el('img');
    image.src = qrImage;
    image.alt = 'Scan this QR code in WhatsApp Linked Devices to connect.';
    qr.append(image);
  } else qr.append(el('span', '', qrError || (qrRequested ? 'Waiting for WhatsApp…' : 'Ready when you are')));
}

async function refreshQr() {
  if (!token || !qrRequested || isConnected() || qrInFlight) return;
  qrInFlight = true;
  const requestVersion = qrRequestVersion;
  try {
    const result = await api('/api/qr');
    if (requestVersion !== qrRequestVersion || isConnected() || !token) return;
    qrImage = null;
    if (result.ready !== false && result.data && /^image\/(png|jpeg|webp)$/.test(result.mimetype || '')) {
      const cleanData = String(result.data).replace(/^data:image\/[^;]+;base64,/, '');
      if (/^[A-Za-z0-9+/=\r\n]+$/.test(cleanData)) {
        qrImage = `data:${result.mimetype};base64,${cleanData}`;
        qrError = '';
      } else qrError = 'The QR code could not be read. Use Refresh QR code to try again.';
    } else qrError = typeof result.message === 'string' ? result.message : 'Waiting for WhatsApp to prepare a QR code…';
    applyConnectionResponse(result);
  } catch (error) {
    if (requestVersion !== qrRequestVersion || isConnected() || !token) return;
    qrImage = null;
    qrError = readableError(error);
  } finally {
    qrInFlight = false;
  }
  updateQrBox();
}

function renderTasks(content) {
  const container = el('div', 'standalone');
  container.append(pageHeading('One thing at a time.', 'Commitments from your chats, with the context behind each one.'));
  const toolbar = el('div', 'toolbar');
  const filters = el('div', 'filters');
  filters.setAttribute('aria-label', 'Filter tasks');
  [['open', 'Open'], ['done', 'Done'], ['dismissed', 'Dismissed']].forEach(([key, label]) => {
    const node = button(label, () => { taskFilter = key; renderContent(); }, '');
    node.className = '';
    node.setAttribute('aria-pressed', taskFilter === key ? 'true' : 'false');
    filters.append(node);
  });
  toolbar.append(filters, el('span', 'hint', `Times shown in ${state.settings?.timezone || 'your timezone'}`));
  container.append(toolbar);
  const tasks = (state.tasks || []).filter(task => task.status === taskFilter);
  if (tasks.length) tasks.forEach(task => container.append(taskRow(task)));
  else container.append(emptyState('check', taskFilter === 'open' ? 'Nothing waiting on you.' : `No ${taskFilter === 'done' ? 'completed' : 'dismissed'} tasks yet.`, taskFilter === 'open' ? 'When a permitted chat includes a commitment for you, it will appear here. Announcements and decisions stay in your brief. Review the original message before acting.' : 'Your tasks will appear here when you update their status.'));
  if (taskFilter === 'open' && (state.notifications || []).length) {
    const inbox = el('section', 'inbox-section');
    inbox.append(sectionHeader('Reminder activity', 'Recent reminders and digests'));
    (state.notifications || []).slice(0, 6).forEach(notification => {
      const row = el('article', 'notification-row');
      const status = notification.status === 'resolved' ? 'Recovered' : notification.status ? notification.status[0].toUpperCase() + notification.status.slice(1) : 'Recorded';
      row.append(el('h3', '', notification.title || 'Reminder'), el('p', '', notification.body || ''), el('small', 'muted', `${dateText(notification.created_at)} · ${status}`));
      inbox.append(row);
    });
    container.append(inbox);
  }
  content.append(container);
}

function monitoringEnabled() {
  return state?.settings?.processing_consent === true;
}

function monitoringAllowed() {
  if (typeof state?.stats?.monitoring_allowed === 'boolean') return state.stats.monitoring_allowed;
  return monitoringEnabled() && (state.settings?.monitoring_mode === 'all' || savedChats().length > 0);
}

function normalChat(chat) {
  if (!chat || typeof chat.id !== 'string' || !['group', 'private'].includes(chat.type)) return null;
  if (chat.id === 'status@broadcast' || /@(broadcast|newsletter)$/.test(chat.id)) return null;
  return { id: chat.id, name: typeof chat.name === 'string' && chat.name ? chat.name : chat.id, type: chat.type };
}

function savedChats() {
  const settings = state?.settings || {};
  const chats = Array.isArray(settings.selected_chats)
    ? settings.selected_chats
    : (settings.selected_groups || []).map(group => ({ ...group, type: 'group' }));
  return chats.map(normalChat).filter(Boolean);
}

function appendChatType(node, item) {
  const type = item.chat_type || item.type;
  if (type === 'group' || type === 'private') node.append(el('span', '', type === 'group' ? 'Group chat' : 'Private chat'));
}

function getChatDraft() {
  if (!chatDraft) chatDraft = {
    mode: state.settings?.monitoring_mode === 'all' ? 'all' : 'selected',
    selected: new Map(savedChats().filter(chat => !(state.settings?.excluded_chat_ids || []).includes(chat.id)).map(chat => [chat.id, chat])),
    excluded: new Set(state.settings?.excluded_chat_ids || []),
    consent: monitoringEnabled(),
    consentReason: '',
  };
  return chatDraft;
}

function refreshChatsOnConnection(wasConnected) {
  // Metadata only: a recovered connection refreshes the list once. Draft
  // scope/consent choices are never changed or posted by a heartbeat.
  if (!wasConnected && isConnected()) fetchChats();
}

function resetDraftConsent(message) {
  const draft = getChatDraft();
  draft.consent = false;
  draft.consentReason = message;
  const checkbox = document.getElementById('processing-consent');
  if (checkbox) checkbox.checked = false;
}

function renderChats(content) {
  const draft = getChatDraft();
  const container = el('div', 'standalone');
  const refresh = button('Refresh chats', () => fetchChats({ notify: true }), 'secondary');
  refresh.id = 'refresh-chats';
  container.append(pageHeading('Choose your chats.', 'Control which messages the helper may capture. Choose ChatGPT sharing or optional API analysis in Settings.', refresh));

  const scope = el('fieldset', 'chat-scope');
  scope.append(el('legend', '', 'Monitoring scope'));
  for (const [value, title, description] of [
    ['selected', 'Selected chats', 'Only the private and group chats you check below.'],
    ['all', 'All chats', 'Existing and future private and group chats, except your exclusions. Statuses, channels and broadcasts are excluded.'],
  ]) {
    const label = el('label', 'scope-option');
    const radio = el('input');
    radio.type = 'radio';
    radio.name = 'monitoring-mode';
    radio.value = value;
    radio.checked = draft.mode === value;
    const copy = el('span');
    copy.append(el('strong', '', title), el('small', '', description));
    label.append(radio, copy);
    radio.addEventListener('change', () => {
      if (!radio.checked || draft.mode === value) return;
      draft.mode = value;
      chatsDirty = true;
      if (value === 'all') resetDraftConsent('All chats includes future conversations. Check the permission box again before saving this wider scope.');
      paintChatList();
      syncChatControls();
    });
    scope.append(label);
  }
  const permission = el('div', 'chat-permission');
  const consentLabel = el('label', 'consent-label');
  const consent = el('input');
  consent.id = 'processing-consent';
  consent.type = 'checkbox';
  consent.checked = draft.consent;
  consent.setAttribute('aria-describedby', 'consent-detail consent-reason');
  consent.addEventListener('change', () => {
    draft.consent = consent.checked;
    if (consent.checked) draft.consentReason = '';
    chatsDirty = true;
    syncChatControls();
  });
  consentLabel.append(consent, el('span', '', HOSTED ? 'I allow this hosted service to store these chats on its server and use them with the ChatGPT sharing or API analysis options I enable in Settings.' : 'I allow GroupBrief to capture these chats locally and use them with the ChatGPT sharing or API analysis options I enable in Settings.'));
  const consentDetail = el('p', 'hint', 'Your choice takes effect only after saving. Pausing stops new reading and AI processing and deletes stored message text and summaries. Existing task titles are kept.');
  consentDetail.id = 'consent-detail';
  const reason = el('p', 'hint consent-reason');
  reason.id = 'consent-reason';
  reason.setAttribute('aria-live', 'polite');
  permission.append(consentLabel, consentDetail, reason);
  container.append(scope, permission);

  const toolbar = el('div', 'toolbar');
  const search = el('input', 'group-search');
  search.type = 'search';
  search.placeholder = 'Find a chat…';
  search.setAttribute('aria-label', 'Find a WhatsApp chat');
  search.value = chatQuery;
  search.addEventListener('input', () => { chatQuery = search.value; paintChatList(); });
  const count = el('span', 'hint');
  count.id = 'chat-count';
  toolbar.append(search, count);
  const note = el('p', 'group-note');
  note.id = 'chat-selection-note';
  const list = el('div', 'group-list');
  list.id = 'chat-list';
  list.setAttribute('aria-live', 'polite');
  container.append(toolbar, note, list);

  const actions = el('div', 'form-actions');
  const save = button('Save monitoring permissions', node => action('save-chats', node, 'Saving…', async () => {
    const current = getChatDraft();
    if (!current.consent || chatsCache === null || chatsInFlight || (current.mode === 'selected' && !current.selected.size)) return;
    const payload = {
      monitoring_mode: current.mode,
      selected_chats: [...current.selected.values()].map(({ id, name, type }) => ({ id, name, type })),
      excluded_chat_ids: [...current.excluded],
      processing_consent: current.consent,
    };
    await api('/api/settings', { method: 'POST', body: JSON.stringify(payload) });
    state.settings = { ...state.settings, ...payload };
    state.stats = { ...state.stats, monitoring_allowed: true };
    chatDraft = null;
    chatsDirty = false;
    errorMessage = '';
    updateAlerts();
    if (activeView === 'chats') renderContent();
    showToast('Chat scope and processing permission saved. Monitoring is enabled for this scope.');
    await refreshState(true);
  }));
  save.id = 'save-chats';
  const pause = button('Pause monitoring', node => action('pause-monitoring', node, 'Pausing…', async () => {
    await api('/api/settings', { method: 'POST', body: JSON.stringify({ processing_consent: false }) });
    state.settings = { ...state.settings, processing_consent: false };
    state.stats = { ...state.stats, monitoring_allowed: false };
    chatDraft = null;
    chatsDirty = false;
    errorMessage = '';
    updateAlerts();
    if (activeView === 'chats') renderContent();
    showToast('Monitoring paused. Stored messages and summaries were removed; task titles were kept.');
    await refreshState(true);
  }), 'tertiary');
  pause.id = 'pause-monitoring';
  const savedState = el('span', 'hint');
  savedState.id = 'chat-saved-state';
  actions.append(save, pause, savedState);
  container.append(actions);
  content.append(container);
  paintChatList();
  syncChatControls();
  if (chatsCache === null && !chatsInFlight && !chatsError) fetchChats();
}

function fetchChats({ notify = false } = {}) {
  if (chatsInFlight) return chatsFetchPromise;
  chatsInFlight = true;
  chatsError = '';
  syncChatControls();
  paintChatList();
  chatsFetchPromise = (async () => {
    try {
      const result = await api('/api/chats');
      if (!Array.isArray(result.chats)) throw new Error('The chat list could not be read. Refresh chats to try again.');
      chatsCache = result.chats.map(normalChat).filter(Boolean);
      if (chatDraft) for (const chat of chatsCache) if (chatDraft.selected.has(chat.id)) chatDraft.selected.set(chat.id, chat);
      if (notify) showToast('Chat list refreshed. Your unsaved choices are preserved.');
    } catch (error) {
      if (token) chatsError = readableError(error);
    } finally {
      chatsInFlight = false;
      chatsFetchPromise = null;
      if (activeView === 'chats') { paintChatList(); syncChatControls(); }
    }
  })();
  return chatsFetchPromise;
}

function paintChatList() {
  const list = document.getElementById('chat-list');
  if (!list || activeView !== 'chats') return;
  const draft = getChatDraft();
  list.replaceChildren();
  if (chatsError) {
    list.append(alertBox(chatsError));
    const retry = button('Try loading chats again', () => fetchChats(), 'secondary');
    retry.id = 'retry-chats';
    retry.disabled = chatsInFlight;
    list.append(retry);
  }
  if (chatsCache === null) {
    if (chatsInFlight) list.append(el('p', 'muted spaced', 'Loading your chats…'));
    syncChatControls();
    return;
  }
  const known = new Map(chatsCache.map(chat => [chat.id, chat]));
  for (const chat of draft.selected.values()) if (!known.has(chat.id)) known.set(chat.id, { ...chat, unavailable: true });
  if (draft.mode === 'all') for (const id of draft.excluded) if (!known.has(id)) known.set(id, { id, name: id, type: id.endsWith('@g.us') ? 'group' : 'private', unavailable: true });
  const query = chatQuery.toLowerCase().trim();
  const chats = [...known.values()].filter(chat => `${chat.name} ${chat.id}`.toLowerCase().includes(query));
  if (!chats.length) list.append(emptyState('group', query ? 'No matching chats.' : 'Your chats will appear here.', query ? 'Try a different chat name.' : 'Connect WhatsApp from Overview, then refresh this list.'));
  chats.forEach(chat => {
    const label = el('label', 'group-row');
    const checkbox = el('input');
    checkbox.type = 'checkbox';
    checkbox.dataset.chatId = chat.id;
    checkbox.checked = draft.mode === 'all' ? !draft.excluded.has(chat.id) : draft.selected.has(chat.id);
    const text = el('span');
    text.append(el('strong', '', chat.name), el('small', '', `${chat.type === 'private' ? 'Private chat' : 'Group chat'} · ${chat.unavailable ? 'Not in the current chat list' : chat.id}`));
    checkbox.addEventListener('change', () => {
      const savedIds = new Set(savedChats().map(item => item.id));
      const restoringExcluded = checkbox.checked && (state.settings?.excluded_chat_ids || []).includes(chat.id);
      const newlyIncludedPrivate = checkbox.checked && chat.type === 'private' && draft.mode === 'selected' && !savedIds.has(chat.id);
      if (draft.mode === 'all') {
        if (checkbox.checked) draft.excluded.delete(chat.id);
        else { draft.excluded.add(chat.id); draft.selected.delete(chat.id); }
      } else {
        if (checkbox.checked) { draft.excluded.delete(chat.id); draft.selected.set(chat.id, { id: chat.id, name: chat.name, type: chat.type }); }
        else draft.selected.delete(chat.id);
      }
      if (restoringExcluded) resetDraftConsent('Your scope now restores an excluded chat. Check the permission box again before saving.');
      else if (newlyIncludedPrivate) resetDraftConsent('Your scope now includes another private chat. Check the permission box again before saving.');
      chatsDirty = true;
      syncChatControls();
    });
    label.append(checkbox, text);
    list.append(label);
  });
  syncChatControls();
}

function syncChatControls() {
  if (activeView !== 'chats') return;
  const draft = getChatDraft();
  const saving = busyActions.has('save-chats');
  const pausing = busyActions.has('pause-monitoring');
  for (const id of ['refresh-chats', 'retry-chats']) {
    const node = document.getElementById(id);
    if (node) {
      node.disabled = chatsInFlight || saving || pausing;
      node.textContent = chatsInFlight ? 'Loading…' : id === 'refresh-chats' ? 'Refresh chats' : 'Try loading chats again';
    }
  }
  document.querySelectorAll('.chat-scope input, #processing-consent, #chat-list input').forEach(input => { input.disabled = saving || pausing; });
  const save = document.getElementById('save-chats');
  if (save) {
    save.disabled = saving || pausing || chatsInFlight || chatsCache === null || !draft.consent || (draft.mode === 'selected' && !draft.selected.size);
    save.textContent = saving ? 'Saving…' : 'Save monitoring permissions';
  }
  const pause = document.getElementById('pause-monitoring');
  if (pause) { pause.hidden = !monitoringEnabled(); pause.disabled = saving || pausing; pause.textContent = pausing ? 'Pausing…' : 'Pause monitoring'; }
  const count = document.getElementById('chat-count');
  if (count) count.textContent = `${draft.mode === 'all' ? `${draft.excluded.size} excluded` : `${draft.selected.size} selected`}${chatsDirty ? ' · Unsaved changes' : ''}`;
  const note = document.getElementById('chat-selection-note');
  if (note) note.textContent = draft.mode === 'all'
    ? 'Checked chats are included. Uncheck a chat to exclude it. Future normal chats are included automatically; your exclusions stay in place.'
    : 'Check the private and group chats you want to include. Unselected chats are excluded. The list shows names and IDs only; it does not load message bodies.';
  const reason = document.getElementById('consent-reason');
  if (reason) { reason.textContent = draft.consentReason; reason.hidden = !draft.consentReason; }
  const savedState = document.getElementById('chat-saved-state');
  if (savedState) savedState.textContent = chatsDirty ? 'Changes take effect after you save.' : monitoringAllowed() ? 'Monitoring enabled for the saved scope.' : 'Monitoring paused.';
}

function makeField(name, label, type, value, options = {}) {
  const wrapper = el('label', `field${options.wide ? ' wide' : ''}`, label);
  const input = el('input');
  input.name = name;
  input.type = type;
  input.value = value === undefined || value === null ? '' : String(value);
  for (const key of ['min', 'max', 'step', 'placeholder', 'autocomplete', 'maxLength']) if (options[key] !== undefined) input[key] = options[key];
  if (options.required) input.required = true;
  if (type === 'password') { input.autocomplete = 'new-password'; input.spellcheck = false; }
  wrapper.append(input);
  if (options.hint) wrapper.append(el('span', 'hint', options.hint));
  return wrapper;
}

function fieldset(title, description) {
  const node = el('fieldset', 'settings-section');
  node.append(el('legend', '', title), el('p', '', description));
  return node;
}

function booleanField(name, label, checked, hint, disabled = false) {
  const wrapper = el('label', 'consent-label');
  const input = el('input');
  input.type = 'checkbox'; input.name = name; input.checked = checked; input.disabled = disabled;
  const text = el('span', '', label);
  if (hint) text.append(el('small', 'hint', hint));
  wrapper.append(input, text);
  return wrapper;
}

function renderSettings(content) {
  const settings = state.settings || {};
  const container = el('div', 'standalone');
  container.append(pageHeading('Make room for what matters.', 'Set up your brief, your reminders, and the way GroupBrief knows you.'));
  const layout = el('div', 'settings-layout');
  const form = el('form');
  form.id = 'settings-form';
  form.addEventListener('input', () => { settingsDirty = true; const node = document.getElementById('settings-status'); if (node) node.textContent = 'Unsaved changes'; });
  const identity = fieldset('About you', 'Your name and aliases help match tasks in group chats. In private chats, incoming requests addressed to you and your outgoing promises use the conversation context; your name does not need to appear.');
  const identityGrid = el('div', 'form-grid');
  identityGrid.append(
    makeField('display_name', 'Your name', 'text', settings.display_name, { maxLength: 100, autocomplete: 'name', hint: 'Optional. Helps match tasks in group chats; private requests can use conversation context.' }),
    makeField('timezone', 'Timezone', 'text', settings.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', { required: true, placeholder: 'Asia/Dubai', hint: 'An IANA timezone, such as Asia/Dubai or Europe/London.' }),
    makeField('aliases', 'Names people use for you', 'text', (settings.aliases || []).join(', '), { wide: true, maxLength: 600, hint: 'Separate names, nicknames, or your phone number with commas.' }),
  );
  identity.append(identityGrid);
  const schedule = fieldset('Your routine', HOSTED ? 'The assistant runs on the server. Digests and reminder times use the timezone above.' : 'The assistant runs on this PC. Digests and reminder times use the timezone above.');
  const scheduleGrid = el('div', 'form-grid');
  scheduleGrid.append(
    makeField('analysis_interval_minutes', 'Check every (minutes)', 'number', settings.analysis_interval_minutes ?? 30, { required: true, min: 5, max: 1440, step: 1 }),
    makeField('daily_digest_time', 'Daily digest time', 'time', settings.daily_digest_time || '08:30', { required: true }),
    makeField('quiet_start', 'Quiet hours start', 'time', settings.quiet_start || '22:00', { required: true }),
    makeField('quiet_end', 'Quiet hours end', 'time', settings.quiet_end || '07:00', { required: true }),
    makeField('remind_before_minutes', 'Remind before a deadline (minutes)', 'number', settings.remind_before_minutes ?? 60, { required: true, min: 0, max: 10080, step: 1 }),
    makeField('retention_days', 'Keep message history (days)', 'number', settings.retention_days ?? 30, { required: true, min: 7, max: 90, step: 1, hint: 'Old source messages are deleted automatically.' }),
  );
  schedule.append(scheduleGrid);
  const intelligence = fieldset('Optional automatic analysis', 'Default: ask ChatGPT to analyze permitted messages using your ChatGPT plan. To create dashboard briefs and tasks automatically while you are away, enable API analysis below. This sends permitted text to the OpenAI API, billed separately from ChatGPT.');
  intelligence.append(booleanField('background_analysis_enabled', 'Enable automatic analysis using an API key', Boolean(settings.background_analysis_enabled), HOSTED ? 'Off by default. Optional background analysis runs on the server and uses your API billing.' : 'Off by default, even if a key was saved previously. Keep the PC awake for background analysis and reminders.'));
  intelligence.append(el('p', 'config-status', state.configured?.openai ? 'API key saved · Used for analysis only when you enable the option above or explicitly request API analysis.' : 'No API key needed for ChatGPT mode. You can leave this section blank.'));
  const intelligenceGrid = el('div', 'form-grid');
  intelligenceGrid.append(
    makeField('openai_api_key', state.configured?.openai ? 'Replace optional OpenAI API key' : 'OpenAI API key (optional)', 'password', '', { wide: true, placeholder: state.configured?.openai ? 'Configured · enter a new key to replace it' : 'Leave blank for ChatGPT mode', maxLength: 500, hint: 'The saved key is never returned to this page.' }),
    makeField('model', 'OpenAI model', 'text', settings.model || '', { required: true, maxLength: 80, hint: 'Use a model available to your API project.' }),
    makeField('max_calls_per_day', 'Maximum AI calls per day', 'number', settings.max_calls_per_day ?? 48, { required: true, min: 1, max: 500, step: 1, hint: 'A usage guardrail, not a currency budget.' }),
  );
  intelligence.append(intelligenceGrid);
  const windows = fieldset('Windows reminders', 'The installed GroupBrief app can show reminders and digests directly on this PC. Keep it running in the system tray; Pushover is optional.');
  windows.append(booleanField('desktop_notifications', 'Show Windows desktop notifications', Boolean(settings.desktop_notifications),
    state.configured?.desktop ? 'Windows Focus and notification settings can silence alerts.' : 'Available in the Windows desktop installer.', !state.configured?.desktop));
  windows.append(button('Test Windows notification', node => action('test-desktop', node, 'Sending…', async () => {
    if (settingsDirty) throw new Error('Save your settings before testing notifications.');
    if (!state.configured?.desktop || !state.settings.desktop_notifications) throw new Error('Enable Windows notifications in the installed desktop app first.');
    await api('/api/test-notification', { method: 'POST' });
    showToast('Notification accepted. Check this PC and any configured Pushover device.');
  }), 'secondary'));
  const chatgpt = fieldset('ChatGPT · No API key required', 'ChatGPT can read permitted text messages and captions when you ask, then analyze them within your conversation using your ChatGPT plan. Your plan limits and plugin availability apply. This does not automatically create local reminders.');
  chatgpt.append(booleanField('chatgpt_messages_enabled', 'Allow ChatGPT to read permitted messages on request', Boolean(settings.chatgpt_messages_enabled),
    `${HOSTED ? 'Shares message text captured on the server' : 'Shares locally captured message text'}, sender names and timestamps with ChatGPT. Only chats covered by your Chats permission are included. Exclusions and retention still apply. Turn off to stop future reads; content already shared remains in that ChatGPT conversation.`, !state.configured?.chatgpt_plugin));
  chatgpt.append(booleanField('chatgpt_enabled', 'Allow ChatGPT to read my permitted briefings and tasks', Boolean(settings.chatgpt_enabled),
    'This is separate from chat-processing permission. ChatGPT reads the brief when you use the plugin; it does not automatically post into an existing ChatGPT conversation.', !state.configured?.chatgpt_plugin));
  const chatgptStatus = el('p', 'hint', HOSTED ? 'Save your sharing permissions, then connect this hosted account from a supported ChatGPT client. Account contains the remote connection URL. No local installation is needed.' : state.configured?.chatgpt_plugin
    ? 'Save permission, then make the plugin available. Restart ChatGPT Windows, open Plugins → Personal, and install WhatsApp by Mahdhi. Use it in a local Work chat.'
    : 'Install the Windows desktop package to use its bundled local ChatGPT plugin.');
  chatgptStatus.setAttribute('role', 'status');
  if (!HOSTED) chatgpt.append(button('Make available in ChatGPT', node => action('register-chatgpt', node, 'Preparing…', async () => {
    if (settingsDirty) throw new Error('Save your settings before connecting ChatGPT.');
    if (!state.settings.chatgpt_enabled && !state.settings.chatgpt_messages_enabled) throw new Error('Check and save ChatGPT sharing permission first.');
    const result = await api('/api/chatgpt/register', { method: 'POST' });
    errorMessage = ''; updateAlerts();
    chatgptStatus.textContent = result.message;
    showToast('Plugin is available. Complete installation in the ChatGPT Windows app.');
  }), 'secondary'), chatgptStatus);
  if (HOSTED) chatgpt.append(chatgptStatus);
  const reminders = fieldset('Optional phone notifications', HOSTED ? 'Pushover can deliver saved-task reminders to supported phones. Its service and app requirements apply. Reading messages in ChatGPT does not create saved tasks or reminders here.' : 'Pushover can also deliver reminders to your phone. Install its app and save the user key and application token below. Windows reminders work independently.');
  reminders.append(el('p', `config-status${state.configured?.pushover ? '' : ' missing'}`, state.configured?.pushover ? 'Pushover configured · Leave both fields blank to keep current credentials.' : 'Pushover is not configured. Reminders will still appear in this dashboard.'));
  const remindersGrid = el('div', 'form-grid');
  remindersGrid.append(
    makeField('pushover_user', 'Pushover user key', 'password', '', { maxLength: 100 }),
    makeField('pushover_token', 'Pushover application API token', 'password', '', { maxLength: 100 }),
  );
  reminders.append(remindersGrid);
  const pushLinks = el('p', 'hint spaced');
  pushLinks.append(externalLink('Set up Pushover', 'https://pushover.net/'), document.createTextNode(' · '), externalLink('Create an application token', 'https://pushover.net/apps/build'));
  reminders.append(pushLinks, button('Send a test notification', node => action('test-notification', node, 'Sending…', async () => {
    if (settingsDirty) throw new Error('Save your settings before sending a test notification.');
    await api('/api/test-notification', { method: 'POST' });
    showToast('Notification accepted. Check your configured notification devices.');
  }), 'secondary'));
  const actions = el('div', 'form-actions');
  const save = button('Save settings', null);
  save.type = 'submit';
  const status = el('span', 'hint', 'Changes take effect after you save.');
  status.id = 'settings-status';
  actions.append(save, status);
  form.append(identity, chatgpt, intelligence, schedule);
  if (!HOSTED) form.append(windows);
  form.append(reminders, actions);
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const timezone = String(data.get('timezone')).trim();
    try { new Intl.DateTimeFormat(undefined, { timeZone: timezone }).format(); }
    catch (_) { const input = form.elements.namedItem('timezone'); input.setCustomValidity('Enter a valid IANA timezone, such as Asia/Dubai.'); input.reportValidity(); return; }
    const payload = {
      display_name: String(data.get('display_name')).trim(),
      aliases: String(data.get('aliases')).split(',').map(value => value.trim()).filter(Boolean),
      timezone,
      analysis_interval_minutes: Number(data.get('analysis_interval_minutes')),
      daily_digest_time: String(data.get('daily_digest_time')),
      quiet_start: String(data.get('quiet_start')),
      quiet_end: String(data.get('quiet_end')),
      remind_before_minutes: Number(data.get('remind_before_minutes')),
      retention_days: Number(data.get('retention_days')),
      model: String(data.get('model')).trim(),
      max_calls_per_day: Number(data.get('max_calls_per_day')),
      background_analysis_enabled: data.has('background_analysis_enabled'),
    };
    if (state.configured?.desktop) payload.desktop_notifications = data.has('desktop_notifications');
    if (state.configured?.chatgpt_plugin) payload.chatgpt_enabled = data.has('chatgpt_enabled');
    if (state.configured?.chatgpt_plugin) payload.chatgpt_messages_enabled = data.has('chatgpt_messages_enabled');
    for (const key of ['openai_api_key', 'pushover_user', 'pushover_token']) {
      const value = String(data.get(key) || '').trim();
      if (value) payload[key] = value;
    }
    action('save-settings', save, 'Saving…', async () => {
      await api('/api/settings', { method: 'POST', body: JSON.stringify(payload) });
      settingsDirty = false;
      errorMessage = ''; updateAlerts();
      for (const key of ['openai_api_key', 'pushover_user', 'pushover_token']) form.elements.namedItem(key).value = '';
      showToast('Settings saved. Your assistant will use the new routine.');
      await refreshState(true);
    });
  });
  form.elements.namedItem('timezone').addEventListener('input', event => event.target.setCustomValidity(''));
  const aside = el('aside', 'settings-aside');
  aside.append(el('h3', '', 'A quieter inbox.'), el('p', '', 'GroupBrief processes the chats covered by your saved permission and keeps tasks linked to their original messages. Review uncertain tasks before relying on a deadline.'), el('p', '', HOSTED ? 'Your permitted chats and linked-device session are stored on the server. The service operator administers that server. You can stop sharing at any time and revoke ChatGPT access from Account.' : 'Keep this PC on with the assistant running. Your iPhone does not need to stay on the same Wi-Fi after linking.'));
  const privacy = el('p', '');
  privacy.append(document.createTextNode('Only include chats you are permitted to process. Set selected chats or explicitly opt into all chats under Chats. This is an unofficial WhatsApp linked-device connection.'));
  aside.append(privacy, el('h3', 'spaced', 'Take your brief with you.'), el('p', '', 'Download your current summaries and tasks as a Markdown file.'), button('Export current brief', node => action('export', node, 'Preparing…', exportBrief), 'secondary'));
  layout.append(form, aside);
  container.append(layout);
  content.append(container);
}

async function exportBrief() {
  const content = await api('/api/export', { asText: true });
  const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }));
  const link = el('a');
  link.href = url;
  link.download = `groupbrief-${new Date().toISOString().slice(0, 10)}.md`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  showToast('Your brief has been exported.');
}

async function refreshState(forceRender = false) {
  if (!token || refreshInProgress) return;
  refreshInProgress = true;
  try {
    const next = await api('/api/state');
    // Heartbeats update last_seen frequently. Keep open disclosures and keyboard
    // focus intact unless the actual page content changes.
    const pageData = value => value && [value.settings, value.configured, value.summaries, value.tasks, value.notifications, value.connection?.status, value.connection?.error];
    const changed = JSON.stringify(pageData(next)) !== JSON.stringify(pageData(state));
    const wasConnected = isConnected();
    state = next;
    if (isConnected()) {
      qrRequestVersion += 1;
      qrImage = null;
      qrRequested = false;
      qrError = '';
    } else if (['scan_qr_code', 'starting'].includes(connectionState())) qrRequested = true;
    if (!document.getElementById('content')) renderShell();
    else {
      updateHeader();
      updateAlerts();
      const editing = settingsDirty || chatsDirty || document.querySelector('.deadline-form');
      if (forceRender || (changed && !editing && (activeView === 'overview' || activeView === 'tasks'))) renderContent();
      const lastSeen = document.getElementById('last-seen');
      if (lastSeen && state.connection?.last_seen) lastSeen.textContent = `Last seen ${dateText(state.connection.last_seen)}`;
      const lastCheck = document.getElementById('last-check');
      if (lastCheck && state.stats?.last_analysis) lastCheck.textContent = `Last checked ${dateText(state.stats.last_analysis)} · ${state.settings?.timezone || 'Local time'}`;
      if (!wasConnected && isConnected()) showToast('WhatsApp connected. Review your chat permissions to start monitoring.');
    }
    refreshChatsOnConnection(wasConnected);
    if (qrRequested && ['scan_qr_code', 'starting'].includes(connectionState()) && !connectInProgress) refreshQr();
  } catch (error) {
    if (token) {
      errorMessage = readableError(error);
      if (!document.getElementById('content')) renderLoadError();
      else updateAlerts();
    }
  } finally { refreshInProgress = false; }
}

function showLogin(message = '') {
  if (HOSTED) { window.location.assign('/login'); return; }
  app.replaceChildren();
  const shell = el('main', 'login-shell');
  shell.id = 'main';
  shell.append(brand(), el('h1', '', 'Your brief is waiting.'), el('p', '', 'Open the access link from the GroupBrief launcher, or enter your dashboard token below.'));
  if (message) shell.append(alertBox(message));
  const form = el('form');
  const field = makeField('token', 'Dashboard token', 'password', '', { required: true, autocomplete: 'current-password' });
  const input = field.querySelector('input');
  input.autocomplete = 'current-password';
  const submit = button('Open GroupBrief', null);
  submit.type = 'submit';
  form.append(field, submit);
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    token = input.value.trim();
    sessionStorage.setItem(TOKEN_KEY, token);
    input.value = '';
    errorMessage = '';
    app.replaceChildren(el('p', 'loading', 'Opening your local assistant…'));
    refreshState(true);
  });
  shell.append(form, el('p', 'hint', 'The dashboard token is stored in this browser tab’s session. Your local launcher holds the access link.'));
  app.append(shell);
}

function renderLoadError() {
  app.replaceChildren();
  const shell = el('main', 'login-shell');
  shell.id = 'main';
  shell.append(brand(), el('h1', '', 'Let’s reconnect.'), el('p', '', HOSTED ? 'The hosted service is unavailable. Check your connection and try again.' : 'GroupBrief could not reach the local assistant. Check that the Windows launcher is still running.'), alertBox(errorMessage), button('Try again', node => action('retry', node, 'Connecting…', () => refreshState(true)), 'secondary'));
  app.append(shell);
}

window.addEventListener('beforeunload', event => {
  if (settingsDirty || chatsDirty) { event.preventDefault(); event.returnValue = ''; }
});

if (token) {
  app.append(el('p', 'loading', 'Opening your local assistant…'));
  refreshState(true);
} else showLogin();

setInterval(() => {
  if (token && !document.hidden && !busyActions.size && !connectInProgress) refreshState();
}, 20000);
setInterval(() => {
  if (token && !document.hidden && qrRequested && !isConnected() && !connectInProgress) refreshQr();
}, 5000);
