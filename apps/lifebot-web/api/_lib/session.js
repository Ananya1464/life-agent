'use strict';
// Sign-in with your Microsoft account. The refresh token lives only in an encrypted, HttpOnly cookie on your
// phone; the server stores nothing. Access tokens are cached in memory while a server instance is warm.

const crypto = require('node:crypto');
const { parseCookies, cookie, httpError } = require('./http.js');

const AUTHORITY = 'https://login.microsoftonline.com/consumers/oauth2/v2.0';
const SCOPES = 'offline_access User.Read Files.ReadWrite';
const COOKIE = 'lb_s';
const CHUNK = 3600;               // browsers allow ~4 KB per cookie; long tokens are split across lb_s0, lb_s1...
const MAX_CHUNKS = 4;
const SESSION_DAYS = 90;

const tokenCache = new Map();     // sha256(refresh token) -> { accessToken, expiresAt }

function env(name) {
  const v = process.env[name];
  if (!v) throw httpError(500, `Server is missing ${name}. Add it in Vercel → Settings → Environment Variables.`);
  return v;
}

function key() {
  return crypto.createHash('sha256').update(env('SESSION_SECRET')).digest();
}

function seal(obj) {
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv('aes-256-gcm', key(), iv);
  const data = Buffer.concat([c.update(JSON.stringify(obj), 'utf8'), c.final()]);
  return Buffer.concat([iv, c.getAuthTag(), data]).toString('base64url');
}

function unseal(text) {
  try {
    const buf = Buffer.from(text, 'base64url');
    const d = crypto.createDecipheriv('aes-256-gcm', key(), buf.subarray(0, 12));
    d.setAuthTag(buf.subarray(12, 28));
    return JSON.parse(Buffer.concat([d.update(buf.subarray(28)), d.final()]).toString('utf8'));
  } catch {
    return null;
  }
}

function sessionCookies(session) {
  const sealed = seal(session);
  const parts = [];
  for (let i = 0; i < sealed.length; i += CHUNK) parts.push(sealed.slice(i, i + CHUNK));
  if (parts.length > MAX_CHUNKS) throw httpError(500, 'Sign-in token is unexpectedly large');
  const age = SESSION_DAYS * 86400;
  const out = parts.map((p, i) => cookie(`${COOKIE}${i}`, p, { maxAge: age }));
  for (let i = parts.length; i < MAX_CHUNKS; i++) out.push(cookie(`${COOKIE}${i}`, '', { maxAge: 0 }));
  return out;
}

function clearCookies() {
  const out = [];
  for (let i = 0; i < MAX_CHUNKS; i++) out.push(cookie(`${COOKIE}${i}`, '', { maxAge: 0 }));
  return out;
}

function readSession(req) {
  const c = parseCookies(req);
  let joined = '';
  for (let i = 0; i < MAX_CHUNKS && c[`${COOKIE}${i}`]; i++) joined += c[`${COOKIE}${i}`];
  return joined ? unseal(joined) : null;
}

function redirectUri() {
  return `${env('APP_URL').replace(/\/+$/, '')}/api/auth/callback`;
}

async function tokenRequest(params) {
  const body = new URLSearchParams({
    client_id: env('MS_CLIENT_ID'), client_secret: env('MS_CLIENT_SECRET'), scope: SCOPES, ...params,
  });
  const r = await fetch(`${AUTHORITY}/token`, { method: 'POST', body, headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.access_token) {
    const reason = j.error_description ? String(j.error_description).split('\r\n')[0] : `status ${r.status}`;
    throw httpError(401, `Microsoft sign-in failed: ${reason}`, { signIn: true });
  }
  return j;
}

function allowedEmail() {
  return env('ALLOWED_EMAIL').trim().toLowerCase();
}

async function whoAmI(accessToken) {
  const r = await fetch('https://graph.microsoft.com/v1.0/me?$select=id,userPrincipalName,mail,displayName', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!r.ok) throw httpError(401, 'Could not read your Microsoft profile', { signIn: true });
  const me = await r.json();
  return { id: me.id, email: String(me.mail || me.userPrincipalName || '').toLowerCase(), name: me.displayName || '' };
}

/**
 * Resolve the signed-in user and a fresh Graph access token.
 * Returns { accessToken, email, name, setCookies: [] }. Throws 401 { signIn: true } when there is no valid session.
 */
async function requireUser(req) {
  if (devMode()) return { accessToken: null, email: 'dev@local', name: 'Dev', setCookies: [] };
  const s = readSession(req);
  if (!s || !s.rt) throw httpError(401, 'Please sign in', { signIn: true });
  if (s.email !== allowedEmail()) throw httpError(403, 'This Microsoft account is not allowed to use this Lifebot.', { signIn: true });
  const id = crypto.createHash('sha256').update(s.rt).digest('hex');
  const cached = tokenCache.get(id);
  if (cached && cached.expiresAt > Date.now() + 60000) return { accessToken: cached.accessToken, email: s.email, name: s.name, setCookies: [] };
  const t = await tokenRequest({ grant_type: 'refresh_token', refresh_token: s.rt });
  const next = { ...s, rt: t.refresh_token || s.rt };
  const nextId = crypto.createHash('sha256').update(next.rt).digest('hex');
  tokenCache.set(nextId, { accessToken: t.access_token, expiresAt: Date.now() + (Number(t.expires_in) || 3600) * 1000 });
  if (tokenCache.size > 50) tokenCache.delete(tokenCache.keys().next().value);
  return { accessToken: t.access_token, email: s.email, name: s.name, setCookies: next.rt !== s.rt ? sessionCookies(next) : [] };
}

/** Local development against a folder on disk: never active on Vercel. */
function devMode() {
  return !!process.env.VAULT_LOCAL_DIR && process.env.DEV_NO_AUTH === '1' && !process.env.VERCEL;
}

module.exports = {
  AUTHORITY, SCOPES, seal, unseal, sessionCookies, clearCookies, readSession, redirectUri, tokenRequest,
  whoAmI, allowedEmail, requireUser, devMode, env,
};
