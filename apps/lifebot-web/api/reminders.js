'use strict';
const { handler, send, readJson } = require('./_lib/http.js');
const { context } = require('./_lib/context.js');
const store = require('./_lib/store.js');
const ntfy = require('./_lib/ntfy.js');

// POST /api/reminders { op: add|remove|done|snooze|sync|test, ... } → the updated list.
module.exports = handler(['POST'], async (req, res) => {
  const { vault } = await context(req, res);
  const body = await readJson(req);
  if (body.op === 'test') {
    const r = await ntfy.sendNow('Lifebot test', 'Phone notifications from Lifebot on your phone are working.');
    return send(res, r.ok ? 200 : 502, r.ok ? { ok: true } : { error: `Could not send: ${r.error}` });
  }
  const { list, created } = await store.reminderOp(vault, body);
  send(res, 200, { reminders: list, created, pushReady: ntfy.ready() });
});
