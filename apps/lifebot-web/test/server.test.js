'use strict';
// node --test test/   (no dependencies; network calls are faked)
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

process.env.TIMEZONE = 'Asia/Kolkata';
process.env.SESSION_SECRET = 'test-secret-that-is-long-enough-1234567890';
process.env.NTFY_TOPIC = 'lifebot_test_topic';

const T = require('../api/_lib/time.js');
const { FsVault, GraphVault, clean } = require('../api/_lib/vault.js');
const store = require('../api/_lib/store.js');
const chat = require('../api/_lib/chat.js');
const S = require('../api/_lib/session.js');

function tempVault() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lbv-'));
  fs.cpSync(path.join(__dirname, 'fixture-vault'), dir, { recursive: true });
  return { dir, vault: new FsVault(dir) };
}

/** Replace global fetch; records calls; answers with `respond(url, init)` or 200 {}. */
function fakeFetch(respond) {
  const calls = [];
  const orig = global.fetch;
  global.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), method: init.method || 'GET', headers: init.headers || {}, body: init.body });
    const r = respond ? await respond(String(url), init) : null;
    return r || new Response('{}', { status: 200 });
  };
  return { calls, restore: () => { global.fetch = orig; } };
}

test('time: naive datetimes are India time; stamps are local', () => {
  const d = T.parseLocal('2026-11-09T09:00');
  assert.equal(d.toISOString(), '2026-11-09T03:30:00.000Z');
  assert.equal(T.parseLocal('2026-11-09T09:00Z').toISOString(), '2026-11-09T09:00:00.000Z');
  assert.equal(T.stamp(new Date('2026-11-09T03:30:00Z')), '2026-11-09T09:00');
  assert.equal(T.localIso(new Date('2026-11-09T03:30:00Z')), '2026-11-09T09:00+05:30');
  assert.equal(T.parseLocal('nonsense'), null);
});

test('vault: paths cannot escape the vault or reach private folders', async () => {
  assert.throws(() => clean('../secret'), /Invalid path/);
  assert.throws(() => clean('09_RUNTIME/secret.txt'), /private/);
  assert.throws(() => clean('.obsidian/workspace.json'), /private/);
  assert.throws(() => clean('00_SYSTEM/ME.md', { forWrite: true }), /cannot change/);
  assert.equal(clean('Tasks.md', { forWrite: true }), 'Tasks.md');
  assert.equal(clean('\\Briefings\\x.md'), 'Briefings/x.md');
  const { vault } = tempVault();
  const root = await vault.list('');
  assert.ok(!root.some((e) => e.name === '09_RUNTIME'), 'runtime folder is hidden from listings');
});

test('tasks: add, toggle (local done stamp), edit, remove, all written to Tasks.md', async () => {
  const { dir, vault } = tempVault();
  let r = await store.taskOp(vault, { op: 'add', text: '  call the bank  ' });
  assert.equal(r.task.text, 'call the bank');
  const file = () => fs.readFileSync(path.join(dir, 'Tasks.md'), 'utf8');
  assert.match(file(), /- \[ \] call the bank/);
  const t = r.view.tasks.find((x) => x.text === 'study linux');
  r = await store.taskOp(vault, { op: 'toggle', id: t.id, text: t.text, checked: true });
  assert.match(file(), new RegExp(`- \\[x\\] study linux \\(done ${T.todayIso()}T\\d\\d:\\d\\d\\)`));
  const events = fs.readFileSync(path.join(dir, 'Lifebot/phone-events.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(events[0].kind, 'task_completed');
  assert.equal(events[0].task, 'study linux');
  assert.equal(events[0].source, 'lifebot_phone');
  assert.match(events[0].ts, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$/);
  const steps = r.view.tasks.find((x) => x.text === 'hit 10 k steps');
  r = await store.taskOp(vault, { op: 'edit', id: steps.id, oldText: steps.text, newText: 'hit 12k steps' });
  assert.match(file(), /- \[ \] hit 12k steps/);
  await assert.rejects(store.taskOp(vault, { op: 'edit', id: r.task.id, oldText: 'something else', newText: 'x' }), (e) => e.status === 409);
  await store.taskOp(vault, { op: 'remove', id: r.task.id, text: 'hit 12k steps' });
  assert.doesNotMatch(file(), /12k steps/);
  assert.match(file(), /## Later\n- \[ \] plan the hackathon/, 'headings and other lines are kept');
});

test('tasks: a laptop edit between read and write is not overwritten', async () => {
  const { dir, vault } = tempVault();
  const realWrite = vault.write.bind(vault);
  let first = true;
  vault.write = async (rel, text, opts) => {
    if (first && rel === 'Tasks.md') {                    // the laptop saves a new task just before our write lands
      first = false;
      fs.appendFileSync(path.join(dir, 'Tasks.md'), '- [ ] added on the laptop\n');
    }
    return realWrite(rel, text, opts);
  };
  await store.taskOp(vault, { op: 'add', text: 'added on the phone' });
  const md = fs.readFileSync(path.join(dir, 'Tasks.md'), 'utf8');
  assert.match(md, /added on the laptop/);
  assert.match(md, /added on the phone/);
});

test('tasks: full-text save refuses a stale version', async () => {
  const { vault } = tempVault();
  const v = await store.loadTasks(vault);
  await store.taskOp(vault, { op: 'add', text: 'newer' });
  await assert.rejects(store.taskOp(vault, { op: 'save', markdown: '## Today\n', etag: v.etag }), (e) => e.status === 409);
});

test('reminders: scheduled on ntfy with a sequence id; delete cancels it', async () => {
  const { dir, vault } = tempVault();
  const f = fakeFetch();
  try {
    const at = new Date(Date.now() + 3600e3);
    const { list, created } = await store.reminderOp(vault, { op: 'add', text: 'drink water', at: at.toISOString() });
    assert.equal(list.length, 1);
    assert.equal(created.armedCount, 1);
    const post = f.calls.find((c) => c.method === 'POST');
    assert.match(post.url, /^https:\/\/ntfy\.sh\/lifebot_test_topic\/lb-r[a-z0-9]+-[a-z0-9]+$/);
    const minute = Math.floor(at.getTime() / 60000) * 60;   // reminders are kept to the minute, like the desktop app
    assert.equal(post.headers.At, String(minute));
    assert.equal(post.body, 'drink water');
    const saved = JSON.parse(fs.readFileSync(path.join(dir, 'Lifebot/phone-reminders.json'), 'utf8'));
    assert.equal(saved.reminders[0].armed.length, 1);
    await store.reminderOp(vault, { op: 'remove', id: created.id });
    const del = f.calls.find((c) => c.method === 'DELETE');
    assert.ok(del && del.url === post.url, 'the scheduled push is cancelled');
  } finally { f.restore(); }
});

test('reminders: daily repeats are armed up to 3 days ahead; far ones wait; past ones fire', async () => {
  const { vault } = tempVault();
  const f = fakeFetch();
  try {
    await store.reminderOp(vault, { op: 'add', text: 'stretch', at: new Date(Date.now() + 2 * 3600e3).toISOString(), repeat: 'daily' });
    const posts = f.calls.filter((c) => c.method === 'POST');
    assert.equal(posts.length, 3, 'today, tomorrow and the day after');
    f.calls.length = 0;
    const { created } = await store.reminderOp(vault, { op: 'add', text: 'renew passport', at: new Date(Date.now() + 5 * 86400e3).toISOString() });
    assert.equal(created.armedCount, 0);
    // a one-off whose time has passed while armed becomes "fired"; never armed becomes "missed"
    const now = new Date();
    const list = [
      { id: 'a', text: 'x', at: T.localIso(new Date(now - 60000)), repeat: 'none', status: 'pending', armed: [{ seq: 'lb-a-1', at: now.getTime() - 60000 }] },
      { id: 'b', text: 'y', at: T.localIso(new Date(now - 60000)), repeat: 'none', status: 'pending', armed: [] },
    ];
    // armed `at` must match the reminder time exactly to count as delivered
    list[0].armed[0].at = T.parseLocal(list[0].at).getTime();
    await store.reconcile(list, now);
    assert.equal(list[0].status, 'fired');
    assert.equal(list[1].status, 'missed');
  } finally { f.restore(); }
});

test('reminders: weekday repeats skip Saturday and Sunday in India time', () => {
  const fri = T.parseLocal('2026-11-13T07:00');            // Friday
  const next = store.nextOccurrence(fri, 'weekdays');
  assert.equal(T.localIso(next), '2026-11-16T07:00+05:30'); // Monday
  assert.equal(T.localIso(store.nextOccurrence(fri, 'daily')), '2026-11-14T07:00+05:30');
});

test('reminders: snooze moves the time and re-arms', async () => {
  const { vault } = tempVault();
  const f = fakeFetch();
  try {
    const { created } = await store.reminderOp(vault, { op: 'add', text: 'call mom', at: new Date(Date.now() + 3600e3).toISOString() });
    const { list } = await store.reminderOp(vault, { op: 'snooze', id: created.id, minutes: 10 });
    const r = list.find((x) => x.id === created.id);
    const mins = (Date.parse(r.at) - Date.now()) / 60000;
    assert.ok(mins > 8 && mins <= 10.1, `snoozed ~10 min (${mins})`);
    assert.equal(r.armedCount, 1);
    assert.ok(f.calls.some((c) => c.method === 'DELETE'), 'old push cancelled');
  } finally { f.restore(); }
});

test('reminders: refuses past times and empty text', async () => {
  const { vault } = tempVault();
  await assert.rejects(store.reminderOp(vault, { op: 'add', text: 'late', at: '2020-01-01T09:00' }), /past/);
  await assert.rejects(store.reminderOp(vault, { op: 'add', text: '  ', at: new Date(Date.now() + 1e6).toISOString() }), /required/);
});

test('chat: tool loop adds a task, then replies; fenced JSON is accepted', async () => {
  const { dir, vault } = tempVault();
  const answers = ['```json\n{"tool": "add_task", "args": {"text": "review my notes"}}\n```', '{"reply": "Added it."}'];
  const prompts = [];
  const out = await chat.respond({ message: 'add a task: review my notes', history: [], vault, generate: async (p) => { prompts.push(p); return answers.shift(); } });
  assert.equal(out.reply, 'Added it.');
  assert.deepEqual(out.actions, [{ type: 'tasks_changed' }]);
  assert.match(fs.readFileSync(path.join(dir, 'Tasks.md'), 'utf8'), /- \[ \] review my notes/);
  assert.match(prompts[0], /study linux/, 'the prompt includes her tasks');
  assert.match(prompts[0], /Test profile/, 'and her ME.md profile');
  assert.match(prompts[1], /add_task -> Task added/);
});

test('chat: cannot read private folders; model failure gives a friendly reply', async () => {
  const { vault } = tempVault();
  const answers = ['{"tool": "read_note", "args": {"path": "09_RUNTIME/secret.txt"}}', '{"reply": "I cannot open that."}'];
  const prompts = [];
  const out = await chat.respond({ message: 'read the secret', vault, generate: async (p) => { prompts.push(p); return answers.shift(); } });
  assert.equal(out.reply, 'I cannot open that.');
  assert.match(prompts[1], /read_note -> Error: read_note failed \(That part of the vault is private/);
  const down = await chat.respond({ message: 'hi', vault, generate: async () => { throw new Error('503'); } });
  assert.match(down.reply, /could not reach my brain/);
});

test('chat: start_focus returns an action for the app; briefings are readable', async () => {
  const { vault } = tempVault();
  const answers = ['{"tool": "latest_briefing", "args": {"kind": "meal_plan"}}', '{"tool": "start_focus", "args": {"task": "linux"}}', '{"reply": "Go."}'];
  const prompts = [];
  const out = await chat.respond({ message: 'focus on linux', vault, generate: async (p) => { prompts.push(p); return answers.shift(); } });
  assert.equal(out.actions[0].type, 'start_focus');
  assert.equal(out.actions[0].text, 'study linux');
  assert.match(prompts[1], /Overnight Oats/);
});

test('session: sealed cookie round-trips, is tamper-proof, and splits when long', () => {
  const sess = { rt: 'x'.repeat(5000), email: 'a@b.com' };
  const cookies = S.sessionCookies(sess);
  const set = cookies.filter((c) => !/Max-Age=0/.test(c));
  assert.ok(set.length >= 2, 'long tokens use several cookies');
  assert.ok(cookies.every((c) => /HttpOnly/.test(c) && /SameSite=Lax/.test(c) && /Secure/.test(c)));
  const header = set.map((c) => c.split(';')[0]).join('; ');
  assert.deepEqual(S.readSession({ headers: { cookie: header } }), sess);
  const tampered = header.replace(/lb_s0=(.)/, (m, ch) => `lb_s0=${ch === 'A' ? 'B' : 'A'}`);
  assert.equal(S.readSession({ headers: { cookie: tampered } }), null);
});

test('session: only the allowed account, and no local test mode on Vercel', async () => {
  process.env.ALLOWED_EMAIL = 'me@outlook.com';
  const cookie = S.sessionCookies({ rt: 'r', email: 'someone@else.com' }).filter((c) => !/Max-Age=0/.test(c)).map((c) => c.split(';')[0]).join('; ');
  await assert.rejects(S.requireUser({ headers: { cookie } }), (e) => e.status === 403);
  await assert.rejects(S.requireUser({ headers: {} }), (e) => e.status === 401 && e.extra.signIn);
  process.env.VAULT_LOCAL_DIR = '/tmp/x'; process.env.DEV_NO_AUTH = '1'; process.env.VERCEL = '1';
  assert.equal(S.devMode(), false);
  delete process.env.VERCEL;
  assert.equal(S.devMode(), true);
  delete process.env.VAULT_LOCAL_DIR; delete process.env.DEV_NO_AUTH;
});

test('graph: reads via metadata + download URL, writes with If-Match, maps 412 to a conflict', async () => {
  const f = fakeFetch(async (url, init) => {
    if (url.includes('/root:/Desktop/ananya/ANANYA-OS/Tasks.md') && !url.includes(':/content')) {
      return Response.json({ eTag: '"etag-1"', '@microsoft.graph.downloadUrl': 'https://dl.example/abc', lastModifiedDateTime: '2026-11-09T01:00:00Z' });
    }
    if (url === 'https://dl.example/abc') return new Response('## Today\n- [ ] a\n');
    if (url.endsWith('Tasks.md:/content') && init.method === 'PUT') {
      return init.headers['If-Match'] === '"etag-1"' ? Response.json({ eTag: '"etag-2"' }) : new Response('', { status: 412 });
    }
    if (url.includes('/root:/Desktop/ananya/ANANYA-OS/Briefings:/children')) return Response.json({ value: [{ name: '2026-11-09 meal_plan.md', file: {} }, { name: 'old', folder: {} }] });
    return new Response('', { status: 404 });
  });
  try {
    const g = new GraphVault('token-123');
    const r = await g.read('Tasks.md');
    assert.equal(r.text, '## Today\n- [ ] a\n');
    assert.equal(r.etag, '"etag-1"');
    assert.equal(f.calls[0].headers.Authorization, 'Bearer token-123');
    assert.equal(f.calls[1].headers.Authorization, undefined, 'the pre-signed download URL gets no token');
    assert.deepEqual(await g.write('Tasks.md', 'x', { etag: '"etag-1"' }), { etag: '"etag-2"' });
    await assert.rejects(g.write('Tasks.md', 'x', { etag: '"stale"' }), (e) => e.status === 409 && e.extra.conflict);
    await assert.rejects(g.write('00_SYSTEM/ME.md', 'x'), (e) => e.status === 403);
    assert.equal(await g.read('missing.md'), null);
    const list = await g.list('Briefings');
    assert.deepEqual(list.map((e) => [e.name, e.isFolder]), [['2026-11-09 meal_plan.md', false], ['old', true]]);
    const enc = new GraphVault('t').itemUrl('Briefings/2026-11-09 meal_plan.md');
    assert.ok(enc.endsWith('/root:/Desktop/ananya/ANANYA-OS/Briefings/2026-11-09%20meal_plan.md'));
  } finally { f.restore(); }
});
