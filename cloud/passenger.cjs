'use strict';
// cPanel startup file. Private runtime configuration stays outside public_html.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {spawn} = require('node:child_process');

function publicRoute(url) {
  try {
    const pathname = decodeURIComponent(new URL(url, 'https://localhost').pathname);
    return !pathname.startsWith('/hooks/') && pathname !== '/hooks';
  } catch (_) { return false; }
}

function main() {
  process.umask(0o077);
  const directory = process.env.WA_CPANEL_DIR;
  if (!directory || !path.isAbsolute(directory)) throw new Error('Set WA_CPANEL_DIR to the private configuration directory');
  const runtime = JSON.parse(fs.readFileSync(path.join(directory, 'runtime.json'), 'utf8'));
  const config = JSON.parse(fs.readFileSync(path.join(directory, 'config.json'), 'utf8'));
  const host = new URL(config.public_url).host;
  const socketPath = path.join(directory, 'run', 'gateway.sock');
  let child, stopping = false, nextStart = 0;
  function start() {
    if (stopping || child || Date.now() < nextStart) return;
    nextStart = Date.now() + 10000;
    child = spawn(runtime.python, ['-m', 'cloud.cpanel'], {
      cwd:path.resolve(__dirname, '..'), env:{...process.env, WA_CPANEL_DIR:directory},
      stdio:['ignore', 'inherit', 'inherit'],
    });
    child.once('error', () => { child = null; });
    child.once('exit', () => { child = null; });
  }
  start();
  const server = http.createServer((request, response) => {
    if (request.headers.host !== host || !publicRoute(request.url)) {
      response.writeHead(404); response.end(); return;
    }
    const upstream = http.request({socketPath, path:request.url, method:request.method,
      headers:{...request.headers, host}, timeout:95000}, result => {
      response.writeHead(result.statusCode, result.headers); result.pipe(response);
    });
    upstream.once('timeout', () => upstream.destroy());
    upstream.once('error', () => {
      start();
      if (!response.headersSent) response.writeHead(503, {'Content-Type':'text/plain', 'Retry-After':'10', 'Cache-Control':'no-store'});
      response.end('WhatsApp is starting. Please try again in a few seconds.');
    });
    request.once('aborted', () => upstream.destroy());
    request.pipe(upstream);
  });
  server.requestTimeout = 100000;
  server.headersTimeout = 15000;
  // Passenger intercepts listen(). With a normal Node process, bind loopback.
  server.listen(Number(process.env.PORT || 3000), '127.0.0.1');
  for (const event of ['SIGTERM', 'SIGINT']) process.once(event, () => {
    stopping = true;
    server.close();
    if (child) child.kill('SIGTERM');
    setTimeout(() => process.exit(0), 15000).unref();
  });
}
if (require.main === module) main();
module.exports = {publicRoute, main};
