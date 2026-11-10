'use strict';
const { handler, send, query, httpError } = require('./_lib/http.js');
const { context } = require('./_lib/context.js');

const NAME_RE = /^[A-Za-z0-9 ._-]{1,120}\.(svg|png)$/;

// GET /api/image?name=la-hud.svg → one dashboard image from the vault's Dashboard folder (signed-in only).
module.exports = handler(['GET'], async (req, res) => {
  const { vault } = await context(req, res);
  const name = String(query(req).name || '');
  if (!NAME_RE.test(name)) throw httpError(400, 'Not a dashboard image');
  const buf = await vault.readBinary(`Dashboard/${name}`);
  if (!buf) return send(res, 404, { error: 'Image not found' });
  res.statusCode = 200;
  res.setHeader('Content-Type', name.endsWith('.svg') ? 'image/svg+xml' : 'image/png');
  res.setHeader('Cache-Control', 'private, max-age=300');
  res.setHeader('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox");
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.end(buf);
});
