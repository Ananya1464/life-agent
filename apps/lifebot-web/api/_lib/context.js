'use strict';
const { requireUser } = require('./session.js');
const { vaultFor } = require('./vault.js');

/** Sign-in check + vault for one request. Refreshed session cookies are attached to the response. */
async function context(req, res) {
  const user = await requireUser(req);
  if (user.setCookies && user.setCookies.length) res.setHeader('Set-Cookie', user.setCookies);
  return { user, vault: vaultFor(user) };
}

module.exports = { context };
