'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {publicRoute} = require('./passenger.cjs');
test('cPanel entrypoint blocks public webhook paths including encoded paths', () => {
  for (const url of ['/hooks/alice', '/hooks', '/%68ooks/alice', '/hooks%2falice', '/broken%']) {
    assert.equal(publicRoute(url), false);
  }
  for (const url of ['/login', '/mcp', '/oauth/authorize?state=abc', '/api/state']) {
    assert.equal(publicRoute(url), true);
  }
});
