'use strict';
const { handler, send } = require('./_lib/http.js');
const { context } = require('./_lib/context.js');
const store = require('./_lib/store.js');
const ntfy = require('./_lib/ntfy.js');
const T = require('./_lib/time.js');

const BRIEF_RE = /^(\d{4}-\d{2}-\d{2}) ([a-z_]+)\.md$/;

async function briefings(vault) {
  const items = await vault.list('Briefings').catch(() => []);
  return items.filter((e) => !e.isFolder && BRIEF_RE.test(e.name))
    .map((e) => { const m = BRIEF_RE.exec(e.name); return { name: e.name, date: m[1], kind: m[2], modified: e.modified }; })
    .sort((a, b) => (b.date.localeCompare(a.date)) || a.kind.localeCompare(b.kind))
    .slice(0, 60);
}

// GET /api/state → everything the app shows on open. Also arms reminders due in the next 3 days.
module.exports = handler(['GET'], async (req, res) => {
  const { user, vault } = await context(req, res);
  const [tasks, rem, briefs] = await Promise.all([
    store.loadTasks(vault),
    store.reminderOp(vault, { op: 'sync' }).catch((e) => ({ list: [], error: e.message })),
    briefings(vault),
  ]);
  send(res, 200, {
    user: { email: user.email, name: user.name },
    today: T.todayIso(), timezone: T.TZ(), now: T.localIso(),
    tasks, reminders: rem.list, remindersError: rem.error || null,
    pushReady: ntfy.ready(), briefings: briefs,
    chatReady: !!(process.env.GEMINI_API_KEY || process.env.NVIDIA_API_KEY),
  });
});
