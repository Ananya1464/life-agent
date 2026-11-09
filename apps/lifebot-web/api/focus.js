'use strict';
const { handler, send, readJson, httpError } = require('./_lib/http.js');
const { context } = require('./_lib/context.js');
const store = require('./_lib/store.js');
const ntfy = require('./_lib/ntfy.js');

const TYPES = ['started', 'paused', 'resumed', 'adjusted', 'completed', 'abandoned'];

// POST /api/focus { type, task: {id, text}, runId, durationSec, endsAt }
// While a session runs, a push is scheduled for its end, so you hear it even with the phone locked.
// Finished and stopped sessions are saved to Lifebot/phone-events.jsonl in the vault (desktop event schema).
module.exports = handler(['POST'], async (req, res) => {
  const { vault } = await context(req, res);
  const b = await readJson(req);
  if (!TYPES.includes(b.type)) throw httpError(400, 'Unknown focus event');
  const runId = String(b.runId || '').replace(/[^A-Za-z0-9_-]/g, '').slice(0, 30);
  if (!runId) throw httpError(400, 'runId is required');
  const seq = `lb-focus-${runId}`;
  const taskText = String((b.task && b.task.text) || 'Free focus').slice(0, 300);
  const intent = `lifebot_phone:${String((b.task && b.task.id) || 'adhoc').slice(0, 120)}:${runId}`;

  let push = null;
  if (['started', 'resumed', 'adjusted'].includes(b.type)) {
    const end = new Date(Number(b.endsAt));
    push = Number.isFinite(end.getTime()) ? await ntfy.schedule(seq, end, 'Focus done', `Time is up: ${taskText}. Take your break.`, 'avocado') : null;
  } else {
    await ntfy.cancel(seq);
  }
  if (b.type === 'started') await store.appendEvent(vault, store.eventRecord('focus_started', taskText, { intent }));
  if (b.type === 'completed' || b.type === 'abandoned') {
    await store.appendEvent(vault, store.eventRecord(`focus_${b.type}`, taskText, { intent, durationSec: b.durationSec }));
  }
  send(res, 200, { ok: true, pushScheduled: !!(push && push.ok) });
});
