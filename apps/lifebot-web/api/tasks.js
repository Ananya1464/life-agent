'use strict';
const { handler, send, readJson } = require('./_lib/http.js');
const { context } = require('./_lib/context.js');
const store = require('./_lib/store.js');

// POST /api/tasks { op: add|toggle|edit|remove|save, ... } → the updated list.
// Every change re-reads Tasks.md from OneDrive first, so edits made on the laptop are never overwritten.
module.exports = handler(['POST'], async (req, res) => {
  const { vault } = await context(req, res);
  const body = await readJson(req);
  try {
    const { view, task } = await store.taskOp(vault, body);
    send(res, 200, { tasks: view, task });
  } catch (e) {
    if (e.status === 409 || e.status === 404) {
      const view = await store.loadTasks(vault).catch(() => null);
      return send(res, e.status, { error: e.message, conflict: true, tasks: view });
    }
    throw e;
  }
});
