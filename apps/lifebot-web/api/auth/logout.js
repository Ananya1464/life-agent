'use strict';
const { handler, send } = require('../_lib/http.js');
const S = require('../_lib/session.js');

// POST /api/auth/logout → forget the session on this device.
module.exports = handler(['POST'], async (req, res) => {
  send(res, 200, { ok: true }, { 'Set-Cookie': S.clearCookies() });
});
