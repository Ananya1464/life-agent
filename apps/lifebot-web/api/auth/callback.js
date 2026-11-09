'use strict';
const { handler, redirect, query, parseCookies, cookie } = require('../_lib/http.js');
const S = require('../_lib/session.js');

const back = (res, msg, extraCookies = []) => redirect(res, `/?signin_error=${encodeURIComponent(msg)}`, {
  'Set-Cookie': [cookie('lb_oauth', '', { maxAge: 0 }), ...extraCookies],
});

// GET /api/auth/callback?code&state → exchange the code, check it is the allowed account, set the session.
module.exports = handler(['GET'], async (req, res) => {
  const q = query(req);
  if (q.error) return back(res, q.error_description ? String(q.error_description).split('\r\n')[0] : q.error);
  const pending = S.unseal(parseCookies(req).lb_oauth || '');
  if (!pending || !q.state || pending.state !== q.state || Date.now() - pending.t > 10 * 60000) {
    return back(res, 'Sign-in expired or came from somewhere else. Please try again.');
  }
  let tokens;
  try {
    tokens = await S.tokenRequest({ grant_type: 'authorization_code', code: String(q.code || ''), redirect_uri: S.redirectUri(), code_verifier: pending.verifier });
  } catch (e) { return back(res, e.message); }
  const me = await S.whoAmI(tokens.access_token);
  if (!me.email || me.email !== S.allowedEmail()) {
    return back(res, `${me.email || 'That account'} is not allowed to use this Lifebot. Sign in with the account set in ALLOWED_EMAIL.`);
  }
  if (!tokens.refresh_token) return back(res, 'Microsoft did not return a long-lived sign-in. Check the offline_access permission.');
  const cookies = S.sessionCookies({ rt: tokens.refresh_token, email: me.email, name: me.name, since: Date.now() });
  redirect(res, '/', { 'Set-Cookie': [cookie('lb_oauth', '', { maxAge: 0 }), ...cookies] });
});
