'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const {
  ENGINE_ANCHOR,
  PINNED_ENGINE_SHA256,
  patchEngineSource,
  verifyPinnedSources,
} = require('./metadata-patch.cjs');

function createHarness(models) {
  let stockCalls = 0;
  let browserCalls = 0;
  const fakeWindow = {
    require(name) {
      assert.equal(name, 'WAWebCollections');
      return { Chat: { getModelsArray: () => models } };
    },
    WWebJS: {
      GetSerialized(id) {
        return typeof id === 'string' ? id : id?._serialized;
      },
      getChatModel() { throw new Error('Message-bearing conversion is forbidden'); },
    },
  };
  const source = patchEngineSource(`class Fixture {
${ENGINE_ANCHOR}
        return this.whatsapp.getChats(pagination, filter);
    }
}
globalThis.Fixture = Fixture;
`);
  const context = vm.createContext({});
  vm.runInContext(source, context);
  const instance = new context.Fixture();
  instance.whatsapp = {
    getChats(pagination, filter) {
      stockCalls += 1;
      return { stock: true, pagination, filter };
    },
    pupPage: {
      async evaluate(callback, query) {
        browserCalls += 1;
        const browserContext = vm.createContext({ window: fakeWindow, query });
        return vm.runInContext(`(${callback.toString()})(query)`, browserContext);
      },
    },
  };
  return {
    instance,
    counts: () => ({ stockCalls, browserCalls }),
  };
}

function clean(value) { return JSON.parse(JSON.stringify(value)); }

test('opt-in metadata path returns only allowed metadata and never reads message/key getters', async () => {
  const model = {
    id: { _serialized: '12125550101@c.us' },
    formattedTitle: 'Synthetic contact',
    archive: true,
    unreadCount: 3,
    t: 1700000000,
  };
  for (const forbidden of ['lastMessage', 'msgs', 'serialize', 'groupMetadata', 'credentials', 'sessionKey']) {
    Object.defineProperty(model, forbidden, {
      enumerable: true,
      get() { throw new Error(`Forbidden getter: ${forbidden}`); },
    });
  }
  const h = createHarness([model]);
  const result = clean(await h.instance.getChats({ metadataOnly: 'true' }));
  assert.deepEqual(result, [{
    id: '12125550101@c.us', name: 'Synthetic contact', type: 'direct', isGroup: false,
    archived: true, unreadCount: 3, timestamp: 1700000000,
  }]);
  assert.deepEqual(h.counts(), { stockCalls: 0, browserCalls: 1 });
});

test('only normal direct and group categories are listed', async () => {
  const ids = [
    '12125550101@c.us', '12125550102@s.whatsapp.net', '123456789@lid',
    '12125550103:4@c.us', '123456789-12345@g.us',
    'status@broadcast', '123@broadcast', '123@newsletter', '123@meta.ai',
    '0@c.us', '0@s.whatsapp.net', '0@lid', '123@unknown', '@g.us', '', null,
  ];
  const h = createHarness(ids.map(id => ({ id, name: 'Synthetic', unreadCount: 0 })));
  const result = clean(await h.instance.getChats({ metadataOnly: 'true' }));
  assert.deepEqual(result.map(row => row.id), [
    '12125550101@c.us', '12125550102@s.whatsapp.net', '12125550103:4@c.us',
    '123456789-12345@g.us', '123456789@lid',
  ]);
  assert.equal(result.find(row => row.id.endsWith('@g.us')).type, 'group');
  assert.equal(result.find(row => row.id.endsWith('@g.us')).isGroup, true);
});

test('string pagination is numeric, stable, bounded and independent of raw collection order', async () => {
  const models = Array.from({ length: 350 }, (_, i) => ({
    id: `${10000000000 + i}@c.us`, formattedTitle: 'Synthetic',
  })).reverse();
  const h = createHarness(models);
  const page = clean(await h.instance.getChats({ metadataOnly: 'true', limit: '100', offset: '100' }));
  assert.equal(page.length, 100);
  assert.equal(page[0].id, '10000000100@c.us');
  assert.equal(page.at(-1).id, '10000000199@c.us');
  const last = clean(await h.instance.getChats({ metadataOnly: 'true', limit: '100', offset: '300' }));
  assert.equal(last.length, 50);
  assert.equal((await h.instance.getChats({ metadataOnly: 'true', limit: '-4', offset: '-9' })).length, 1);
  assert.equal((await h.instance.getChats({ metadataOnly: 'true', limit: 'garbage', offset: 'garbage' })).length, 100);
  assert.equal((await h.instance.getChats({ metadataOnly: 'true', limit: 'Infinity', offset: 'Infinity' })).length, 100);
  assert.equal((await h.instance.getChats({ metadataOnly: 'true', limit: '5000', offset: '999999' })).length, 0);
  const larger = createHarness(Array.from({ length: 1100 }, (_, i) => ({ id: `${20000000000 + i}@lid` })));
  assert.equal((await larger.instance.getChats({ metadataOnly: 'true', limit: '5000' })).length, 1000);
});

test('metadata sanitizes malformed counters and supports metadata fallbacks', async () => {
  const h = createHarness([
    { id: '12125550101@c.us', name: 'Fallback title', archived: true, unreadCount: -2, timestamp: Infinity },
    { id: '12125550102@c.us', formattedTitle: {}, unreadCount: '4.8', t: '1700000001' },
  ]);
  const result = clean(await h.instance.getChats({ metadataOnly: 'true' }));
  assert.equal(result[0].name, 'Fallback title');
  assert.equal(result[0].archived, true);
  assert.equal(result[0].unreadCount, 0);
  assert.equal(result[0].timestamp, null);
  assert.equal(result[1].name, null);
  assert.equal(result[1].unreadCount, 4);
  assert.equal(result[1].timestamp, 1700000001);
});

test('stock behavior remains unchanged without exact opt-in', async () => {
  const h = createHarness([]);
  for (const metadataOnly of [undefined, 'false', 'TRUE', '1', true]) {
    const query = { limit: '100', offset: '100', metadataOnly };
    const filter = { ids: ['synthetic'] };
    const result = h.instance.getChats(query, filter);
    assert.equal(result.stock, true);
    assert.equal(result.pagination, query);
    assert.equal(result.filter, filter);
  }
  assert.deepEqual(h.counts(), { stockCalls: 5, browserCalls: 0 });
});

test('patch rejects missing/duplicate anchors and unexpected compiled artifacts', () => {
  assert.throws(() => patchEngineSource('class Unsupported {}'), /exactly one/);
  assert.throws(() => patchEngineSource(ENGINE_ANCHOR + ENGINE_ANCHOR), /exactly one/);
  assert.throws(() => verifyPinnedSources('unsupported', 'unsupported'), /Unsupported WAHA engine/);
});

test('installed pinned artifacts retain query pass-through, original source and valid patch', { skip: !process.env.WAHA_PATCH_TEST_ROOT }, () => {
  const root = process.env.WAHA_PATCH_TEST_ROOT;
  const engine = fs.readFileSync(`${root}/dist/core/engines/webjs/session.webjs.core.js`, 'utf8');
  const original = fs.readFileSync(`${root}/dist/core/engines/webjs/session.webjs.core.js.groupbrief-original`, 'utf8');
  const controller = fs.readFileSync(`${root}/dist/api/chats.controller.js`, 'utf8');
  assert.equal(crypto.createHash('sha256').update(original).digest('hex'), PINNED_ENGINE_SHA256);
  verifyPinnedSources(original, controller);
  assert.throws(() => verifyPinnedSources(original, 'unsupported controller'), /Unsupported WAHA chats controller/);
  assert.equal(engine, patchEngineSource(original));
  assert.match(controller, /getChats\(session, pagination\)\s*\{\s*return session\.getChats\(pagination\);\s*\}/);
  const controllerDecoration = controller.slice(controller.lastIndexOf('__decorate([', controller.indexOf('], ChatsController.prototype, "getChats", null);')), controller.indexOf('], ChatsController.prototype, "getChats", null);'));
  assert.ok(controllerDecoration.includes('(0, common_1.Query)()'));
  assert.ok(!controllerDecoration.includes('UsePipes'));
});
