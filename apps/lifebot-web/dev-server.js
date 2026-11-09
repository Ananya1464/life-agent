'use strict';
// Run the phone app on your computer against a local folder, for testing:
//   VAULT_LOCAL_DIR=path/to/a/copy/of/ANANYA-OS DEV_NO_AUTH=1 LIFEBOT_INSECURE_COOKIES=1 node dev-server.js
// Then open http://localhost:3000. It refuses to run without VAULT_LOCAL_DIR, so it never touches OneDrive.

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

if (!process.env.VAULT_LOCAL_DIR) {
  console.error('Set VAULT_LOCAL_DIR to a COPY of your vault folder first.');
  process.exit(1);
}
const ROOT = __dirname;
const PORT = Number(process.env.PORT) || 3000;
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.txt': 'text/plain' };

http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (url.pathname.startsWith('/api/')) {
    const file = path.join(ROOT, `${url.pathname.replace(/\/+$/, '')}.js`);
    if (!file.startsWith(path.join(ROOT, 'api')) || url.pathname.includes('/_lib/') || !fs.existsSync(file)) { res.statusCode = 404; return res.end('{"error":"Not found"}'); }
    req.query = Object.fromEntries(url.searchParams.entries());
    try { return await require(file)(req, res); } catch (e) { console.error(e); res.statusCode = 500; return res.end('{"error":"crash"}'); }
  }
  let p = decodeURIComponent(url.pathname);
  if (p === '/') p = '/index.html';
  const file = path.join(ROOT, p);
  if (!file.startsWith(ROOT) || /[\\/](api|test|node_modules)[\\/]/.test(file.slice(ROOT.length)) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; return res.end('Not found'); }
  res.setHeader('Content-Type', TYPES[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
}).listen(PORT, () => console.log(`Lifebot web (local test) on http://localhost:${PORT}  vault: ${process.env.VAULT_LOCAL_DIR}`));
