'use strict';
// Small request/response helpers that work both on Vercel (Node runtime) and in dev-server.js.

const MAX_BODY = 256 * 1024;

function send(res, status, body, headers = {}) {
  const isJson = typeof body !== 'string';
  res.statusCode = status;
  res.setHeader('Content-Type', isJson ? 'application/json; charset=utf-8' : 'text/plain; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  for (const [k, v] of Object.entries(headers)) res.setHeader(k, v);
  res.end(isJson ? JSON.stringify(body) : body);
}

function redirect(res, location, headers = {}) {
  res.statusCode = 302;
  res.setHeader('Location', location);
  res.setHeader('Cache-Control', 'no-store');
  for (const [k, v] of Object.entries(headers)) res.setHeader(k, v);
  res.end();
}

/** Parsed JSON body. Vercel may have parsed it already (req.body); otherwise read the stream. */
async function readJson(req) {
  if (req.body !== undefined && req.body !== null && typeof req.body === 'object' && !Buffer.isBuffer(req.body)) return req.body;
  if (typeof req.body === 'string') return safeParse(req.body);
  if (Buffer.isBuffer(req.body)) return safeParse(req.body.toString('utf8'));
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY) throw httpError(413, 'Request is too large');
    chunks.push(c);
  }
  return safeParse(Buffer.concat(chunks).toString('utf8'));
}

function safeParse(text) {
  if (!text) return {};
  try { const v = JSON.parse(text); return v && typeof v === 'object' ? v : {}; } catch { throw httpError(400, 'Body must be JSON'); }
}

function query(req) {
  if (req.query && typeof req.query === 'object') return req.query;
  const u = new URL(req.url, 'http://x');
  return Object.fromEntries(u.searchParams.entries());
}

function parseCookies(req) {
  const out = {};
  String(req.headers.cookie || '').split(';').forEach((part) => {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  });
  return out;
}

function cookie(name, value, { maxAge, httpOnly = true } = {}) {
  const secure = process.env.LIFEBOT_INSECURE_COOKIES === '1' ? '' : '; Secure';
  const age = maxAge === undefined ? '' : `; Max-Age=${maxAge}`;
  return `${name}=${encodeURIComponent(value)}; Path=/${age}; SameSite=Lax${secure}${httpOnly ? '; HttpOnly' : ''}`;
}

function httpError(status, message, extra) {
  const e = new Error(message);
  e.status = status;
  if (extra) e.extra = extra;
  return e;
}

/** Same-origin guard for state-changing calls: the app always sends this header; other sites cannot without CORS. */
function requireAppHeader(req) {
  if (req.headers['x-lifebot'] !== '1') throw httpError(403, 'Missing app header');
}

/** Wrap a handler: method check, JSON errors, never leak stack traces. */
function handler(methods, fn) {
  return async (req, res) => {
    try {
      if (!methods.includes(req.method)) return send(res, 405, { error: 'Method not allowed' }, { Allow: methods.join(', ') });
      if (req.method !== 'GET') requireAppHeader(req);
      await fn(req, res);
    } catch (err) {
      const status = err.status || 500;
      if (status >= 500) console.error('[lifebot-web]', err && err.stack || err);
      if (!res.headersSent) send(res, status, { error: status >= 500 ? 'Something went wrong on the server. Try again.' : err.message, ...(err.extra || {}) }, err.headers || {});
    }
  };
}

module.exports = { send, redirect, readJson, query, parseCookies, cookie, httpError, handler };
