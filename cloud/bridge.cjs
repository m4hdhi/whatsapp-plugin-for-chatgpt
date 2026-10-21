'use strict';
// One unprivileged container and persistent session volume per account.
const path = require('node:path');
const http = require('node:http');
const {Client, LocalAuth} = require('../native/bridge/node_modules/whatsapp-web.js');
const QRCode = require('../native/bridge/node_modules/qrcode');
const {LocalBridge, recoverColdStartup, resumeSyncedSession} = require('../native/bridge/bridge.cjs');

async function main() {
  const uid = process.env.WA_ACCOUNT;
  const apiKey = process.env.WAHA_API_KEY;
  const hookSecret = process.env.APP_WEBHOOK_SECRET;
  if (!/^[a-z][a-z0-9-]{2,39}$/.test(uid || '') ||
      !/^[a-f0-9]{64}$/.test(apiKey || '') || !/^[a-f0-9]{64}$/.test(hookSecret || '')) {
    throw new Error('Invalid worker configuration');
  }
  class CompatibleClient extends Client {
    async inject() {
      if (!this.bootChecked) { this.bootChecked = true; await recoverColdStartup(this.pupPage); }
      await super.inject();
      await this.pupPage.evaluate(resumeSyncedSession);
    }
  }
  const socketDir = process.env.WA_CLOUD_SOCKET_DIR;
  const sessionRoot = socketDir ? process.env.WA_SESSION_ROOT : '/session';
  const chrome = socketDir ? process.env.WA_CHROME : '/usr/bin/chromium';
  if (socketDir && (![socketDir, sessionRoot, chrome].every(p => p && path.isAbsolute(p)))) {
    throw new Error('Invalid private runtime paths');
  }
  const bridge = new LocalBridge({apiKey, hookSecret, allowedHost: `bridge-${uid}:3000`, hookUrl: `http://gateway:8000/hooks/${uid}`,
    ...(socketDir ? {fetch: (url, options) => new Promise((resolve, reject) => {
      const request = http.request({socketPath:path.join(socketDir, 'gateway.sock'),
        path:new URL(url).pathname, method:'POST', signal:options.signal,
        headers:{...options.headers, host:'gateway:8000'}}, response => {
        response.resume(); resolve({ok:response.statusCode >= 200 && response.statusCode < 300});
      });
      request.on('error', reject); request.end(options.body);
    })} : {}),
    qrEncoder: async value => (await QRCode.toBuffer(value, {type:'png', margin:4, width:360})).toString('base64'),
    clientFactory: () => new CompatibleClient({
      authStrategy: new LocalAuth({clientId:'groupbrief', dataPath:path.join(sessionRoot, 'whatsapp')}),
      webVersionCache: {type:'none'},
      puppeteer: {executablePath:chrome, headless:true,
        // The worker is isolated by its container, non-root UID, private network
        // and dedicated volume. Container Chromium cannot use its SUID sandbox.
        args:[...(socketDir ? [] : ['--no-sandbox']), '--disable-dev-shm-usage', '--no-first-run']},
      authTimeoutMs:120000, qrMaxRetries:0, takeoverOnConflict:false,
    }),
  });
  if (socketDir) {
    await new Promise((resolve, reject) => {
      bridge.server.once('error', reject);
      bridge.server.listen(path.join(socketDir, `bridge-${uid}.sock`), resolve);
    });
  } else await bridge.listen(3000, '0.0.0.0');
  void bridge.start();
  process.once('SIGTERM', () => void bridge.close());
  process.once('SIGINT', () => void bridge.close());
}
main().catch(() => { process.stderr.write('WhatsApp worker startup failed. Check its private configuration.\n'); process.exitCode = 1; });
