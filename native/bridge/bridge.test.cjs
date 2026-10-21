'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const vm = require('node:vm');
const crypto = require('node:crypto');
const { LocalBridge, metadataProjection, messageProjection, historyProjection, resumeSyncedSession, recoverColdStartup } = require('./bridge.cjs');

test('cold startup retries only a stalled initial document and never reloads pairing', async () => {
  let state = 'UNLAUNCHED', reloads = 0;
  const page = { waitForFunction: async () => { throw new Error('Timed out'); },
    evaluate: async () => state, reload: async () => { reloads++; } };
  await recoverColdStartup(page);
  assert.equal(reloads, 1);
  state = 'PAIRING';
  await recoverColdStartup(page);
  state = 'UNPAIRED';
  await recoverColdStartup(page);
  assert.equal(reloads, 1);
});

test('restored already-synced profiles finish the library handshake once without bypassing pairing', async () => {
  let calls = 0;
  const window = { require: () => ({ Socket: { hasSynced: false } }), onAppStateHasSyncedEvent: async () => { calls++; } };
  const context = vm.createContext({ window });
  const invoke = () => vm.runInContext(`(${resumeSyncedSession.toString()})()`, context);
  await invoke();
  assert.equal(calls, 0);
  window.require = () => ({ Socket: { hasSynced: true } });
  await invoke();
  await invoke();
  assert.equal(calls, 1);
});

test('current WhatsApp structured message IDs survive projection and deduplicate', () => {
  const message = { id: { fromMe: false, remote: '12@lid', id: 'ABC', participant: '34@c.us' },
    from: '12@lid', to: '56@c.us', fromMe: false, type: 'chat', body: 'Submit in five minutes', timestamp: 1792566267 };
  const first = messageProjection(message);
  assert(first, 'structured IDs without _serialized must be captured');
  assert.equal(first.id, messageProjection(structuredClone(message)).id);
  assert.notEqual(first.id, messageProjection({ ...message, id: { ...message.id, id: 'DEF' } }).id);
});

test('history reads only the requested chat after consent without full chat serialization', async () => {
  let loads = 0;
  const old = { t: 5, type: 'chat', get body() { throw new Error('Pre-consent content'); } };
  const recent = { t: 20, type: 'chat', id: { fromMe: false, remote: '12@lid', id: 'ABC' },
    from: '12@lid', to: '56@c.us', body: 'Submit in five minutes', mentionedJidList: [] };
  const requested = { id: { _serialized: '12@lid' }, msgs: { getModelsArray: () => [old, recent] },
    serialize() { throw new Error('Broken full chat serializer'); } };
  const other = { id: { _serialized: '99@lid' }, get msgs() { throw new Error('Other chat content'); } };
  const rows = await vm.runInNewContext(`(${historyProjection.toString()})({id:'12@lid',since:10,limit:100})`, {
    window: { require: name => name === 'WAWebCollections' ? { Chat: { getModelsArray: () => [requested, other] } }
      : { loadEarlierMsgs: async () => { loads++; return []; } } },
  });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].body, 'Submit in five minutes');
  assert.equal(messageProjection(rows[0]).id, messageProjection({ ...recent, timestamp: recent.t, fromMe: false }).id);
  assert.equal(loads, 0);
});

test('slow older-history loading returns the available batch instead of hanging the connection check', async () => {
  let timeoutMs;
  const rows = await vm.runInNewContext(`(${historyProjection.toString()})({id:'12@lid',since:10,limit:100})`, {
    window: { require: name => name === 'WAWebCollections' ? { Chat: { getModelsArray: () => [
      { id: { _serialized: '12@lid' }, msgs: { getModelsArray: () => [] } },
    ] } } : { loadEarlierMsgs: () => new Promise(() => {}) } },
    setTimeout: (callback, milliseconds) => { timeoutMs = milliseconds; queueMicrotask(callback); return 1; },
    clearTimeout: () => {},
  });
  assert.equal(rows.length, 0);
  assert(timeoutMs < 15000, 'browser recovery must finish before the HTTP client timeout');
});

test('metadata projection never serializes messages and bounds numeric pagination', () => {
  const chats = Array.from({ length: 350 }, (_, i) => ({ id: { _serialized: `${1000 + i}@c.us` }, name: `Synthetic ${i}`,
    get lastMessage() { throw new Error('Message body must not be read'); },
    serialize() { throw new Error('No serialization'); } }));
  chats.push({ id: { _serialized: 'status@broadcast' } }, { id: { _serialized: '12@newsletter' } });
  const rows = vm.runInNewContext(`(${metadataProjection.toString()})({limit:'100',offset:'100'})`, {
    window: { require: () => ({ Chat: { getModelsArray: () => chats } }) },
  });
  assert.equal(rows.length, 100);
  assert.equal(rows[0].id, '1100@c.us');
  assert(rows.every(row => Object.keys(row).sort().join(',') === 'archived,id,isGroup,name,timestamp,type,unreadCount'));
});

class Client extends EventEmitter {
  constructor() { super(); this.initialized = 0; this.destroyed = 0; this.pupPage = { evaluate: async () => [{ id: '12@c.us', name: 'Synthetic chat', type: 'private', isGroup: false }] }; }
  async initialize() { this.initialized++; }
  async destroy() { this.destroyed++; }
}
async function fixture() {
  const clients = [], hooks = [];
  const key = 'k'.repeat(64), secret = 's'.repeat(64);
  const bridge = new LocalBridge({ apiKey: key, hookSecret: secret, hookUrl: 'http://127.0.0.1:1/webhooks/waha',
    qrEncoder: async () => 'synthetic-base64', clientFactory: () => { const c = new Client(); clients.push(c); return c; },
    fetch: async (_, options) => { hooks.push(options); return { ok: true }; } });
  const port = await bridge.listen();
  const call = async (url, options = {}) => fetch(`http://127.0.0.1:${port}${url}`, {
    ...options, headers: { 'x-api-key': key, ...options.headers },
  });
  return { bridge, clients, hooks, key, secret, call };
}

test('authenticated lifecycle returns QR states and never restarts an active session', async () => {
  const f = await fixture();
  try {
    assert.equal((await f.call('/api/sessions/default', { headers: { 'x-api-key': '' } })).status, 401);
    assert.equal((await f.call('/api/sessions/default', { headers: { origin: 'https://other.invalid' } })).status, 403);
    await f.call('/api/sessions', { method: 'POST', body: '{}' });
    assert.equal(f.bridge.status, 'STARTING');
    let qr = await f.call('/api/default/auth/qr');
    assert.equal(qr.status, 422);
    f.clients[0].emit('qr', 'synthetic');
    await new Promise(resolve => setImmediate(resolve));
    qr = await f.call('/api/default/auth/qr');
    assert.equal((await qr.json()).data, 'synthetic-base64');
    await f.call('/api/sessions/default/restart', { method: 'POST' });
    assert.equal(f.clients.length, 1);
    f.clients[0].emit('ready');
    await f.call('/api/sessions/default/restart', { method: 'POST' });
    assert.equal(f.clients.length, 1);
    assert.equal((await (await f.call('/api/default/chats?metadataOnly=true')).json())[0].type, 'private');
    assert.equal((await f.call('/api/default/chats')).status, 400);
    assert.equal((await f.call('/api/sendText', { method: 'POST', body: '{}' })).status, 404);
    assert.equal((await f.call('/api/sessions/default/logout', { method: 'POST' })).status, 404);
  } finally { await f.bridge.close(); }
});

test('only text and captions become signed incoming/outgoing message events', async () => {
  const f = await fixture();
  try {
    await f.bridge.start();
    const client = f.clients[0];
    client.emit('ready');
    client.emit('message_create', { id: { _serialized: 'synthetic-1' }, from: '12@c.us', to: '34@c.us', fromMe: false,
      body: 'Synthetic private request', timestamp: 1792483200, type: 'chat', mentionedIds: ['34@c.us'], _data: { secret: 'NOT FORWARDABLE' } });
    client.emit('message_create', { id: 'excluded', from: 'status@broadcast', body: 'Status body', type: 'chat' });
    client.emit('message_create', { id: 'voice', from: '12@c.us', body: '', type: 'ptt' });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(f.hooks.length, 1);
    const hook = f.hooks[0];
    assert.equal(hook.headers['X-Webhook-Hmac'], crypto.createHmac('sha512', f.secret).update(hook.body).digest('hex'));
    assert(!hook.body.includes('NOT FORWARDABLE'));
    assert.equal(JSON.parse(hook.body).payload.body, 'Synthetic private request');
    assert.equal(messageProjection({ from: '12@c.us', to: '34@c.us', fromMe: true, id: 'mine', body: 'I will send it', type: 'chat', timestamp: 1 }).to, '34@c.us');
  } finally { await f.bridge.close(); }
});

test('failed sessions can restart without logout or deletion; stale QR events ignored', async () => {
  const f = await fixture();
  try {
    await f.bridge.start();
    f.clients[0].emit('auth_failure');
    await f.bridge.start(true);
    assert.equal(f.clients.length, 2);
    assert.equal(f.clients[0].destroyed, 1);
    f.clients[0].emit('qr', 'stale');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(f.bridge.qr, null);
    assert.equal(f.bridge.status, 'STARTING');
  } finally { await f.bridge.close(); }
});
