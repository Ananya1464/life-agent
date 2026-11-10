'use strict';
const crypto = require('node:crypto');
const { handler, redirect, cookie } = require('../_lib/http.js');
const S = require('../_lib/session.js');

// GET /api/auth/login → Microsoft sign-in page (PKCE + state kept in a short-lived encrypted cookie).
module.exports = handler(['GET'], async (req, res) => {
  if (S.devMode()) return redirect(res, '/');
  const verifier = crypto.randomBytes(32).toString('base64url');
  const state = crypto.randomBytes(16).toString('base64url');
  const challenge = crypto.createHash('sha256').update(verifier).digest('base64url');
  const params = new URLSearchParams({
    client_id: S.env('MS_CLIENT_ID'), response_type: 'code', redirect_uri: S.redirectUri(), response_mode: 'query',
    scope: S.SCOPES, state, code_challenge: challenge, code_challenge_method: 'S256', prompt: 'select_account',
  });
  redirect(res, `${S.AUTHORITY}/authorize?${params}`, {
    'Set-Cookie': cookie('lb_oauth', S.seal({ state, verifier, t: Date.now() }), { maxAge: 600 }),
  });
});
