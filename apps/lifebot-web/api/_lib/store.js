'use strict';
// Everything the phone app changes in the vault: Tasks.md (shared with the desktop app), plus two files of its
// own under Lifebot/: phone-reminders.json and phone-events.jsonl (same event schema as data/events.jsonl).

const crypto = require('node:crypto');
const Tasks = require('../../lib/tasks.js');
const TaskEdit = require('../../lib/taskedit.js');
const T = require('./time.js');
const ntfy = require('./ntfy.js');
const { httpError } = require('./http.js');

const TASKS_FILE = 'Tasks.md';
const REMINDERS_FILE = 'Lifebot/phone-reminders.json';
const EVENTS_FILE = 'Lifebot/phone-events.jsonl';
const SOURCE = 'lifebot_phone';
const MAX_MARKDOWN = 200 * 1024;

const isConflict = (e) => !!(e && e.extra && e.extra.conflict);

/** Read-modify-write with optimistic locking; on a conflict, re-read and re-apply (the change is re-based). */
async function mutate(vault, file, load, apply, save) {
  for (let attempt = 0; ; attempt++) {
    const cur = await load(vault);
    const next = apply(cur);
    if (next === undefined || next === null) return { state: cur, changed: false };
    try {
      const w = await save(vault, next, cur);
      return { state: w, changed: true };
    } catch (e) {
      if (!isConflict(e) || attempt >= 2) throw e;
    }
  }
}

// ------------------------------------------------------------------ tasks

function taskView(markdown, etag, exists) {
  const tasks = Tasks.listTasks(markdown, T.todayIso());
  return { markdown, etag, exists, tasks, summary: { total: tasks.length, done: tasks.filter((t) => t.checked).length } };
}

async function loadTasks(vault) {
  const f = await vault.read(TASKS_FILE);
  return taskView(f ? f.text : Tasks.DEFAULT_MARKDOWN, f ? f.etag : null, !!f);
}

async function saveTasks(vault, markdown, cur) {
  if (markdown.length > MAX_MARKDOWN) throw httpError(413, 'The task list is too long to save');
  const w = await vault.write(TASKS_FILE, markdown, { etag: cur.etag || undefined });
  return taskView(markdown, w.etag, true);
}

function findTask(view, { id, text }) {
  return view.tasks.find((t) => t.id === id)
    || (typeof text === 'string' && view.tasks.find((t) => t.text === text.trim() && !t.checked))
    || (typeof text === 'string' && view.tasks.find((t) => t.text === text.trim()))
    || null;
}

/** Apply one task operation from the app or from chat. Returns { view, task?, completed? }. */
async function taskOp(vault, op) {
  let touched = null;
  let completed = null;
  const { state } = await mutate(vault, TASKS_FILE, loadTasks, (cur) => {
    switch (op.op) {
      case 'add': {
        const v = TaskEdit.validateText(String(op.text || ''));
        if (!v.ok) throw httpError(400, v.error);
        touched = { text: v.text };
        return Tasks.addTask(cur.markdown, v.text);
      }
      case 'toggle': {
        const t = findTask(cur, op);
        if (!t) throw httpError(404, 'That task is no longer in the list. Reloaded.');
        if (t.checked === !!op.checked) return null;
        touched = t;
        if (op.checked) completed = t;
        return Tasks.toggle(cur.markdown, t.lineIndex, !!op.checked, T.stamp());
      }
      case 'edit': {
        const r = TaskEdit.applyEdit({ markdown: cur.markdown, dateIso: T.todayIso(), id: op.id, oldText: String(op.oldText || ''), newText: String(op.newText || '') });
        if (!r.ok) throw httpError(r.code === 'conflict' ? 409 : r.code === 'not_found' ? 404 : 400, r.error, { conflict: r.code === 'conflict' });
        touched = { id: r.id, text: r.text };
        return r.markdown === cur.markdown ? null : r.markdown;
      }
      case 'remove': {
        const t = findTask(cur, op);
        if (!t) return null;
        touched = t;
        return Tasks.removeTask(cur.markdown, t.lineIndex);
      }
      case 'save': {
        if (typeof op.markdown !== 'string') throw httpError(400, 'markdown is required');
        if (op.etag && cur.etag && op.etag !== cur.etag) throw httpError(409, 'The list changed on another device. Reloaded; make your edit again.', { conflict: true });
        return op.markdown.replace(/\r\n/g, '\n');
      }
      default:
        throw httpError(400, 'Unknown task operation');
    }
  }, saveTasks);
  if (completed) await appendEvent(vault, eventRecord('task_completed', completed.text, { intent: completed.id })).catch(() => {});
  return { view: state, task: touched };
}

// ------------------------------------------------------------------ events (same schema as data/events.jsonl)

function eventRecord(kind, task, { durationSec, intent } = {}) {
  const id = crypto.randomUUID().replace(/-/g, '');
  const date = T.todayIso();
  const rec = { id, ts: new Date().toISOString().replace(/\.(\d{3})Z$/, '.$1000Z'), kind, date, task: String(task || '').slice(0, 300), source: SOURCE, intent_id: intent || null };
  if (durationSec !== undefined) rec.duration_seconds = Math.max(0, Math.round(Number(durationSec) || 0));
  rec.dedupe_key = `${kind}:${date}:${intent || id}:${SOURCE}`;
  return rec;
}

async function appendEvent(vault, rec) {
  await mutate(vault, EVENTS_FILE,
    async (v) => { const f = await v.read(EVENTS_FILE); return { text: f ? f.text : '', etag: f ? f.etag : null }; },
    (cur) => cur.text + (cur.text && !cur.text.endsWith('\n') ? '\n' : '') + JSON.stringify(rec) + '\n',
    async (v, text, cur) => { const w = await v.write(EVENTS_FILE, text, { etag: cur.etag || undefined }); return { text, etag: w.etag }; });
}

// ------------------------------------------------------------------ reminders

const REPEATS = ['none', 'daily', 'weekdays'];
const MAX_TEXT = 200;
const ARM_WINDOW_MS = ntfy.MAX_DELAY_MS - 10 * 60000;   // stay safely inside ntfy's 3-day limit
const MAX_ARMED = 4;
const pad = (n) => String(n).padStart(2, '0');

function newId() { return 'r' + Date.now().toString(36) + crypto.randomBytes(3).toString('hex'); }

/** Same wall-clock time on the next allowed day (time-zone aware). */
function nextOccurrence(atDate, repeat) {
  if (repeat === 'none') return null;
  const hm = T.local(atDate);
  let probe = new Date(atDate.getTime() + 12 * 3600e3);
  for (let i = 0; i < 400; i++) {
    const l = T.local(probe);
    const d = T.parseLocal(`${l.y}-${pad(l.mo)}-${pad(l.d)}T${pad(hm.h)}:${pad(hm.mi)}`);
    const dow = T.local(d).dow;
    if (d.getTime() > atDate.getTime() && !(repeat === 'weekdays' && (dow === 0 || dow === 6))) return d;
    probe = new Date(probe.getTime() + 24 * 3600e3);
  }
  return null;
}

function makeReminder(input, now = new Date()) {
  const text = String((input && input.text) || '').replace(/\s+/g, ' ').trim();
  if (!text) throw httpError(400, 'Reminder text is required');
  if (text.length > MAX_TEXT) throw httpError(400, `Reminder text is too long (max ${MAX_TEXT})`);
  const repeat = (input && input.repeat) || 'none';
  if (!REPEATS.includes(repeat)) throw httpError(400, 'Repeat must be none, daily or weekdays');
  const when = T.parseLocal(input && input.at);
  if (!when) throw httpError(400, 'Reminder time is not a valid date');
  if (when.getTime() < now.getTime() - 60000) throw httpError(400, 'That time is in the past');
  return { id: newId(), text, at: T.localIso(when), repeat, status: 'pending', createdAt: T.localIso(now), armed: [] };
}

const seqFor = (r, d) => `lb-${r.id}-${d.getTime().toString(36)}`;

/** The times this reminder should be armed for right now (within ntfy's window). */
function wanted(r, now) {
  if (r.status !== 'pending') return [];
  const out = [];
  let d = T.parseLocal(r.at);
  while (d && d.getTime() - now.getTime() <= ARM_WINDOW_MS && out.length < MAX_ARMED) {
    if (d.getTime() - now.getTime() >= ntfy.MIN_DELAY_MS) out.push(d);
    if (r.repeat === 'none') break;
    d = nextOccurrence(d, r.repeat);
  }
  return out;
}

/**
 * Bring reminders up to date: past one-offs become "fired" (or "missed" if they were never armed), repeating ones
 * move to their next slot, and everything due within 3 days is scheduled on ntfy. Returns true if anything changed.
 */
async function reconcile(list, now = new Date()) {
  let changed = false;
  for (const r of list) {
    r.armed = Array.isArray(r.armed) ? r.armed : [];
    if (r.status === 'pending') {
      let at = T.parseLocal(r.at);
      while (at && at.getTime() <= now.getTime()) {
        const wasArmed = r.armed.some((a) => a.at === at.getTime());
        if (r.repeat === 'none') {
          r.status = wasArmed ? 'fired' : 'missed';
          r.firedAt = T.localIso(at);
          at = null;
        } else {
          r.lastFiredAt = T.localIso(at);
          const next = nextOccurrence(at, r.repeat);
          if (!next) { r.status = 'done'; at = null; } else { r.at = T.localIso(next); at = next; }
        }
        changed = true;
      }
    }
    const before = r.armed.length;
    r.armed = r.armed.filter((a) => a.at > now.getTime());          // delivered ones drop off
    if (r.armed.length !== before) changed = true;
    const want = wanted(r, now);
    const wantSeqs = new Set(want.map((d) => seqFor(r, d)));
    for (const a of r.armed.filter((x) => !wantSeqs.has(x.seq))) { await ntfy.cancel(a.seq); changed = true; }
    r.armed = r.armed.filter((x) => wantSeqs.has(x.seq));
    if (!ntfy.ready()) continue;
    for (const d of want) {
      const seq = seqFor(r, d);
      if (r.armed.some((a) => a.seq === seq)) continue;
      const res = await ntfy.schedule(seq, d, 'Lifebot reminder', r.text);
      if (res.ok) { r.armed.push({ seq, at: d.getTime() }); changed = true; }
    }
  }
  return changed;
}

async function cancelAll(r) {
  for (const a of r.armed || []) await ntfy.cancel(a.seq);
  r.armed = [];
}

async function loadReminders(vault) {
  const f = await vault.read(REMINDERS_FILE);
  let list = [];
  if (f) { try { const j = JSON.parse(f.text); list = Array.isArray(j.reminders) ? j.reminders : []; } catch { list = []; } }
  return { list, etag: f ? f.etag : null };
}

async function saveReminders(vault, list, cur) {
  const keep = list.filter((r) => r.status === 'pending' || (Date.now() - Date.parse(r.firedAt || r.completedAt || r.createdAt || 0)) < 14 * 86400e3);
  const text = JSON.stringify({ version: 1, note: 'Written by Lifebot on your phone. Times are local.', reminders: keep }, null, 1) + '\n';
  const w = await vault.write(REMINDERS_FILE, text, { etag: cur.etag || undefined });
  return { list: keep, etag: w.etag };
}

function reminderView(list) {
  const rank = { pending: 0, missed: 1, fired: 2, done: 3 };
  return list
    .map(({ armed, ...r }) => ({ ...r, armedCount: (armed || []).length }))
    .sort((a, b) => (rank[a.status] - rank[b.status]) || String(a.at).localeCompare(String(b.at)));
}

/** op: { op: 'add'|'remove'|'done'|'snooze'|'sync', ... }. Returns the updated list. */
async function reminderOp(vault, op) {
  let created = null;
  const { state } = await (async () => {
      for (let attempt = 0; ; attempt++) {
        const cur = await loadReminders(vault);
        const list = cur.list.map((r) => ({ ...r }));
        const now = new Date();
        let changed = false;
        const find = () => list.find((r) => r.id === op.id);
        switch (op.op) {
          case 'add': created = makeReminder(op, now); list.push(created); changed = true; break;
          case 'remove': { const r = find(); if (r) { await cancelAll(r); list.splice(list.indexOf(r), 1); changed = true; } break; }
          case 'done': {
            const r = find();
            if (r) {
              await cancelAll(r);
              if (r.repeat === 'none' || op.all) { r.status = 'done'; r.completedAt = T.localIso(now); }
              changed = true;
            }
            break;
          }
          case 'snooze': {
            const r = find();
            if (!r) throw httpError(404, 'That reminder is gone');
            const m = Math.min(Math.max(Math.round(Number(op.minutes) || 10), 1), 24 * 60);
            await cancelAll(r);
            r.status = 'pending';
            r.at = T.localIso(new Date(now.getTime() + m * 60000));
            changed = true;
            break;
          }
          case 'sync': break;
          default: throw httpError(400, 'Unknown reminder operation');
        }
        if (await reconcile(list, now)) changed = true;
        if (!changed) return { state: cur };
        try { return { state: await saveReminders(vault, list, cur) }; } catch (e) { if (!isConflict(e) || attempt >= 2) throw e; }
      }
    })();
  return { list: reminderView(state.list), created: created && reminderView([created])[0] };
}

module.exports = {
  TASKS_FILE, REMINDERS_FILE, EVENTS_FILE, loadTasks, taskOp, findTask, eventRecord, appendEvent,
  makeReminder, nextOccurrence, reconcile, reminderOp, reminderView, loadReminders,
};
