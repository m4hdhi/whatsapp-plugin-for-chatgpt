'use strict';
// Local WAHA-compatible read-only adapter. No send, logout or account-delete API.
const http = require('node:http');
const crypto = require('node:crypto');
const path = require('node:path');

function serialized(value) {
  return typeof value === 'string' ? value : value?._serialized || '';
}

// A restored profile can finish syncing before the library subscribes to the
// hasSynced change event. Run its own ready handshake in that case.
async function resumeSyncedSession() {
  if (!window.WWebJS && !window.__groupBriefSyncRecovery &&
      window.require('WAWebSocketModel').Socket.hasSynced === true &&
      typeof window.onAppStateHasSyncedEvent === 'function') {
    window.__groupBriefSyncRecovery = true;
    await window.onAppStateHasSyncedEvent();
  }
}

async function recoverColdStartup(page) {
  try {
    await page.waitForFunction(() => {
      try { return !['UNLAUNCHED', 'OPENING', 'PAIRING'].includes(window.require('WAWebSocketModel').Socket.state); }
      catch (_) { return false; }
    }, { timeout: 15000, polling: 500 });
  } catch (_) {
    const state = await page.evaluate(() => {
      try { return window.require('WAWebSocketModel').Socket.state; }
      catch (_) { return null; }
    });
    // Restored Chromium profiles can stall on the initial document. Refresh
    // once before the library installs its authentication/event bindings.
    if (state === 'UNLAUNCHED') await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
  }
}
function normalId(id) {
  return typeof id === 'string' && /^[1-9]\d*(?:-\d+)?@g\.us$|^[1-9]\d*(?::\d+)?@(c\.us|s\.whatsapp\.net|lid)$/.test(id);
}

// Puppeteer serializes this function. It deliberately has no outer references.
function metadataProjection(query) {
  const numeric = (value, fallback, low, high) => Number.isFinite(Number(value))
    ? Math.max(low, Math.min(high, Math.floor(Number(value)))) : fallback;
  const limit = numeric(query.limit ?? 1000, 1000, 1, 1000);
  const offset = numeric(query.offset ?? 0, 0, 0, 50000);
  const chats = window.require('WAWebCollections').Chat.getModelsArray();
  const rows = [];
  for (const chat of chats) {
    const id = typeof chat.id === 'string' ? chat.id : chat.id?._serialized;
    if (typeof id !== 'string') continue;
    const group = /^[1-9]\d*(?:-\d+)?@g\.us$/.test(id);
    if (!group && !/^[1-9]\d*(?::\d+)?@(c\.us|s\.whatsapp\.net|lid)$/.test(id)) continue;
    const title = chat.formattedTitle || chat.name;
    rows.push({ id, name: typeof title === 'string' ? title.slice(0, 200) : id,
      type: group ? 'group' : 'private', isGroup: group,
      archived: Boolean(chat.archive ?? chat.archived),
      unreadCount: Number.isFinite(Number(chat.unreadCount)) ? Math.max(0, Number(chat.unreadCount)) : 0,
      timestamp: Number.isFinite(Number(chat.t)) ? Number(chat.t) : null });
  }
  rows.sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  return rows.slice(offset, offset + limit);
}

function messageProjection(message) {
  // Recent WhatsApp serializers omit MsgKey._serialized. Keep a deterministic
  // key from its explicit identity fields, including the group participant.
  const key = message.id;
  const id = serialized(key) || (key && typeof key.fromMe === 'boolean' &&
    typeof key.id === 'string' && key.id && normalId(serialized(key.remote))
    ? 'msg:' + crypto.createHash('sha256').update(JSON.stringify([
      key.fromMe, serialized(key.remote), key.id, serialized(key.participant),
    ])).digest('hex') : '');
  const from = serialized(message.from);
  const to = serialized(message.to);
  const chat = message.fromMe ? to : from;
  const type = message.type;
  if (!id || !normalId(chat) || !['chat', 'image', 'video', 'document'].includes(type)) return null;
  if (typeof message.body !== 'string' || !message.body.trim()) return null;
  return { id, from, to, fromMe: Boolean(message.fromMe), body: message.body,
    timestamp: Number(message.timestamp), participant: serialized(message.author),
    _data: { mentionedJidList: (message.mentionedIds || []).map(serialized).filter(Boolean) } };
}

// Avoid WWebJS.getChat(): its full chat serializer currently fails for LIDs.
// Only the explicitly requested chat is read; project after the permission time.
async function historyProjection(query) {
  const chats = window.require('WAWebCollections').Chat;
  const chat = chats.getModelsArray().find(c => c.id?._serialized === query.id);
  if (!chat) throw new Error('Requested chat is not loaded');
  const stringId = value => typeof value === 'string' ? value : value?._serialized || '';
  const limit = Math.max(1, Math.min(100, Number(query.limit) || 100));
  const since = Number(query.since) || 0;
  let messages = chat.msgs.getModelsArray();
  // Bound older-history requests and stop once the consent boundary is reached.
  for (let attempt = 0; attempt < 2 && messages.length < limit; attempt++) {
    if (messages.length && Math.min(...messages.map(m => Number(m.t) || 0)) < since) break;
    let timer, loaded;
    try {
      loaded = await Promise.race([
        window.require('WAWebChatLoadMessages').loadEarlierMsgs({ chat }),
        new Promise(resolve => { timer = setTimeout(() => resolve(null), 2000); }),
      ]);
    } catch (_) { break; }
    finally { clearTimeout(timer); }
    if (!loaded?.length) break;
    messages = chat.msgs.getModelsArray();
  }
  return messages.filter(m => !m.isNotification && Number(m.t) >= since &&
    ['chat', 'image', 'video', 'document'].includes(m.type))
    .sort((a, b) => Number(a.t) - Number(b.t)).slice(-limit).map(m => ({
      id: { fromMe: Boolean(m.id.fromMe), remote: stringId(m.id.remote),
        id: m.id.id, participant: stringId(m.id.participant) },
      from: stringId(m.from), to: stringId(m.to), fromMe: Boolean(m.id.fromMe),
      type: m.type, body: m.type === 'chat' ? m.body : m.caption,
      timestamp: Number(m.t), author: stringId(m.author),
      mentionedIds: (m.mentionedJidList || []).map(stringId),
    }));
}

class LocalBridge {
  constructor(options) {
    this.options = options;
    this.status = 'STOPPED';
    this.qr = null;
    this.client = null;
    this.generation = 0;
    this.starting = false;
    this.stopping = false;
    this.retryTimer = null;
    this.retries = 0;
    this.outbox = [];
    this.sending = false;
    this.server = http.createServer((req, res) => this.route(req, res));
    this.server.requestTimeout = 20000;
    this.server.headersTimeout = 10000;
  }
  session() {
    const info = this.client?.info;
    const me = info?.wid ? { id: serialized(info.wid), lid: serialized(info.lid) } : null;
    return { name: 'default', status: this.status, me };
  }
  async start(restart = false) {
    if (this.starting || this.stopping || ['WORKING', 'STARTING', 'SCAN_QR_CODE'].includes(this.status)) return;
    this.starting = true;
    const generation = ++this.generation;
    this.qr = null;
    this.status = 'STARTING';
    try {
      if (this.client) { try { await this.client.destroy(); } catch (_) {} }
      if (generation !== this.generation || this.stopping) return;
      const client = this.options.clientFactory();
      this.client = client;
      const current = () => generation === this.generation && !this.stopping;
      client.on('qr', async value => {
        if (!current()) return;
        try {
          const data = await this.options.qrEncoder(value);
          if (current()) { this.qr = data; this.status = 'SCAN_QR_CODE'; }
        } catch (_) { if (current()) this.status = 'FAILED'; }
      });
      client.on('ready', () => { if (current()) { this.status = 'WORKING'; this.qr = null; this.retries = 0; } });
      client.on('auth_failure', () => { if (current()) { this.status = 'FAILED'; this.qr = null; this.retries = 3; } });
      client.on('disconnected', reason => {
        if (!current()) return;
        this.status = 'FAILED'; this.qr = null;
        // An explicit account logout requires the user to link again.
        if (String(reason).toUpperCase() !== 'LOGOUT' && this.retries++ < 3) {
          clearTimeout(this.retryTimer);
          this.retryTimer = setTimeout(() => this.start(true), 3000 * this.retries);
          this.retryTimer.unref();
        }
      });
      client.on('message_create', message => {
        if (!current() || this.status !== 'WORKING') return;
        const payload = messageProjection(message);
        if (payload) this.enqueue(payload);
      });
      // Do not block HTTP start/QR polling on WhatsApp authentication.
      Promise.resolve(client.initialize()).catch(() => {
        if (current()) { this.status = 'FAILED'; this.qr = null; }
      });
    } catch (_) { if (generation === this.generation) this.status = 'FAILED'; }
    finally { this.starting = false; }
  }
  enqueue(payload) {
    if (this.outbox.length >= 5000) return; // Bounded memory; recent-history recovery is secondary.
    this.outbox.push({ event: { session: 'default', event: 'message.any', payload }, tries: 0 });
    void this.flush();
  }
  async flush() {
    if (this.sending || this.stopping) return;
    this.sending = true;
    try {
      while (this.outbox.length && !this.stopping) {
        const item = this.outbox[0];
        const body = JSON.stringify(item.event);
        const signature = crypto.createHmac('sha512', this.options.hookSecret).update(body).digest('hex');
        try {
          const response = await (this.options.fetch || fetch)(this.options.hookUrl, {
            method: 'POST', headers: { 'content-type': 'application/json', 'X-Webhook-Hmac': signature, 'X-Webhook-Hmac-Algorithm': 'sha512' },
            body, signal: AbortSignal.timeout(10000), redirect: 'error' });
          if (response.ok) { this.outbox.shift(); continue; }
        } catch (_) {}
        if (++item.tries >= 10) { this.outbox.shift(); continue; }
        const timer = setTimeout(() => void this.flush(), Math.min(60000, 1000 * 2 ** item.tries));
        timer.unref();
        break;
      }
    } finally { this.sending = false; }
  }
  json(res, status, value) {
    res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(JSON.stringify(value));
  }
  async route(req, res) {
    const supplied = Buffer.from(String(req.headers['x-api-key'] || ''));
    const expected = Buffer.from(this.options.apiKey);
    if (supplied.length !== expected.length || !crypto.timingSafeEqual(supplied, expected)) return this.json(res, 401, { error: 'Unauthorized' });
    if (req.headers.origin || !/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(req.headers.host || '')) return this.json(res, 403, { error: 'Local service only' });
    let url;
    try { url = new URL(req.url, 'http://127.0.0.1'); } catch (_) { return this.json(res, 400, { error: 'Invalid request' }); }
    let bytes = 0;
    try {
      for await (const chunk of req) { bytes += chunk.length; if (bytes > 1048576) return this.json(res, 413, { error: 'Request too large' }); }
      if (req.method === 'GET' && url.pathname === '/api/sessions/default') return this.json(res, 200, this.session());
      if (req.method === 'POST' && (url.pathname === '/api/sessions' || /^\/api\/sessions\/default\/(start|restart)$/.test(url.pathname))) {
        void this.start(url.pathname.endsWith('restart'));
        return this.json(res, 201, this.session());
      }
      if (req.method === 'GET' && url.pathname === '/api/default/auth/qr') {
        if (this.status === 'SCAN_QR_CODE' && this.qr) return this.json(res, 200, { mimetype: 'image/png', data: this.qr });
        return this.json(res, 422, { status: this.status });
      }
      if (req.method === 'POST' && url.pathname === '/internal/stop') {
        this.json(res, 200, { status: 'stopping' });
        void this.close(); return;
      }
      if (this.status !== 'WORKING') return this.json(res, 422, { status: this.status });
      if (req.method === 'GET' && ['/api/default/chats', '/api/default/groups'].includes(url.pathname)) {
        // Fail closed rather than implement stock chat serialization.
        if (url.pathname.endsWith('chats') && url.searchParams.get('metadataOnly') !== 'true') return this.json(res, 400, { error: 'metadataOnly=true is required' });
        const rows = await this.client.pupPage.evaluate(metadataProjection, Object.fromEntries(url.searchParams));
        return this.json(res, 200, url.pathname.endsWith('groups') ? rows.filter(row => row.isGroup).map(({ id, name }) => ({ id, name })) : rows);
      }
      const history = url.pathname.match(/^\/api\/default\/chats\/([^/]+)\/messages$/);
      if (req.method === 'GET' && history) {
        const id = decodeURIComponent(history[1]);
        if (!normalId(id)) return this.json(res, 400, { error: 'Invalid chat' });
        const since = Number(url.searchParams.get('filter.timestamp.gte') || 0);
        const limit = Math.min(100, Math.max(1, Number(url.searchParams.get('limit')) || 100));
        const messages = await this.client.pupPage.evaluate(historyProjection, { id, since, limit });
        const rows = messages.map(messageProjection).filter(row => row && row.timestamp >= since && id === (row.fromMe ? row.to : row.from));
        return this.json(res, 200, rows);
      }
      const identity = url.pathname.match(/^\/api\/default\/lids\/([^/]+)$/);
      if (req.method === 'GET' && identity) {
        const id = decodeURIComponent(identity[1]);
        if (!normalId(id) || !id.endsWith('@lid')) return this.json(res, 400, { error: 'Invalid identity' });
        const rows = await this.client.getContactLidAndPhone([id]);
        const value = rows.find(row => serialized(row.lid) === id);
        return this.json(res, 200, { lid: id, pn: value ? serialized(value.pn) || null : null });
      }
      return this.json(res, 404, { error: 'Unsupported operation' });
    } catch (_) { if (!res.headersSent) this.json(res, 503, { error: 'Local WhatsApp operation unavailable. Check the connection and try again.' }); }
  }
  async listen(port = 0) {
    await new Promise((resolve, reject) => { this.server.once('error', reject); this.server.listen(port, '127.0.0.1', resolve); });
    return this.server.address().port;
  }
  async close() {
    if (this.stopping) return;
    this.stopping = true; ++this.generation;
    clearTimeout(this.retryTimer);
    this.outbox = [];
    if (this.client) { try { await this.client.destroy(); } catch (_) {} }
    this.server.close();
    this.server.closeAllConnections();
  }
}

async function main() {
  const { Client, LocalAuth } = require('whatsapp-web.js');
  class CompatibleClient extends Client {
    async inject() {
      if (!this.groupBriefBootChecked) {
        this.groupBriefBootChecked = true;
        await recoverColdStartup(this.pupPage);
      }
      await super.inject();
      await this.pupPage.evaluate(resumeSyncedSession);
    }
  }
  const QRCode = require('qrcode');
  const root = process.env.GROUPBRIEF_DATA_DIR;
  const apiKey = process.env.WAHA_API_KEY;
  const hookSecret = process.env.APP_WEBHOOK_SECRET;
  const hookUrl = process.env.GROUPBRIEF_HOOK_URL;
  const browser = process.env.GROUPBRIEF_CHROMIUM;
  if (!root || !browser || !apiKey || apiKey.length < 32 || !hookSecret || hookSecret.length < 32 || !/^http:\/\/127\.0\.0\.1:\d+\/webhooks\/waha$/.test(hookUrl || '')) throw new Error('Missing local runtime configuration.');
  const bridge = new LocalBridge({ apiKey, hookSecret, hookUrl,
    qrEncoder: async value => (await QRCode.toBuffer(value, { type: 'png', margin: 4, width: 360 })).toString('base64'),
    clientFactory: () => new CompatibleClient({
      authStrategy: new LocalAuth({ clientId: 'groupbrief', dataPath: path.join(root, 'whatsapp') }),
      webVersionCache: { type: 'none' },
      puppeteer: { executablePath: browser, headless: true, args: ['--disable-gpu', '--disable-dev-shm-usage', '--no-first-run', '--disable-background-networking'] },
      authTimeoutMs: 120000, qrMaxRetries: 0, takeoverOnConflict: false,
    }) });
  await bridge.listen(Number(process.env.GROUPBRIEF_BRIDGE_PORT));
  void bridge.start();
  process.once('SIGINT', () => void bridge.close());
  process.once('SIGTERM', () => void bridge.close());
}
module.exports = { LocalBridge, metadataProjection, messageProjection, historyProjection, resumeSyncedSession, recoverColdStartup, normalId };
if (require.main === module) main().catch(() => { process.stderr.write('The local WhatsApp runtime could not start. Reopen GroupBrief.\n'); process.exitCode = 1; });
