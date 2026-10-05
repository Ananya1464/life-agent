'use strict';
// Pure nudge engine. Local time = now - tzOffsetMin*60000 (tzOffsetMin is JS getTimezoneOffset(): UTC minus local).
const MIN = 60000;
const DAY = 1440 * MIN;
const MAX_LOG = 50;
const GAP_MIN = 60 * MIN;           // global minimum gap between any two nudges
const GAP_BACKOFF = 180 * MIN;      // gap after 2 ignored/dismissed in a row
const STOP_STREAK = 4;              // 4 ignored/dismissed in a row => silent for the rest of the day
const PENDING_STALE = 20 * MIN;     // an unanswered nudge older than this counts as ignored
const IDLE_AFTER = 90 * MIN;        // no focus for this long => idle_start may fire
const CARRIED_REST = 3 * DAY;     // never ask about the same carried task again within this long (no daily nagging)
const KIND_COOLDOWN = { morning_pick: DAY, carried_over: DAY, wrapup: DAY, idle_start: 120 * MIN };

// Wording variants, each a tiny concrete step; {t} is the task text. Positive, no guilt.
const WORDS = {
  morning_pick: [
    ['One thing today?', 'Want to start with "{t}"? Just 5 minutes.'],
    ['Pick your one thing', 'How about "{t}" first? A tiny start is plenty.'],
    ['Fresh day', 'Would "{t}" be a good first step? 5 minutes is enough.'],
  ],
  idle_start: [
    ['Tiny start?', 'Want to give "{t}" 5 minutes?'],
    ['Ready when you are', 'Open "{t}" and do just the first bit. 5 minutes.'],
    ['A small step', 'Shall we try 5 minutes on "{t}"?'],
  ],
  carried_over: [
    ['Do, keep, or drop?', '"{t}" has been around a while. Do it now, keep it, or let it go?'],
    ['Quick check-in', 'What would you like for "{t}"? Do, keep, or drop.'],
    ['Tidy one thing', '"{t}" is still open. Do it, keep it, or drop it?'],
  ],
  wrapup: [
    ['What moved today?', 'Nice, "{t}" counts. Want to jot a one-line wrap-up?'],
    ['Today in a line', 'Some progress happened, like "{t}". Want to note it?'],
    ['Small win check', 'Something moved today. Want to capture it in one line?'],
  ],
};

const clip = (s) => { s = String(s == null ? '' : s).trim(); return s.length > 60 ? s.slice(0, 57) + '...' : s; };
const hm = (s, d) => { const m = /^(\d{1,2}):(\d{2})$/.exec(s || ''); return m ? (+m[1]) * 60 + (+m[2]) : d; };
/** Local day number for an epoch ms. */
const dayOf = (ms, off) => Math.floor((ms - off * MIN) / DAY);
/** Local minutes since midnight. */
const minOf = (ms, off) => Math.floor((((ms - off * MIN) % DAY) + DAY) % DAY / MIN);

/** Quiet window check; supports windows that wrap midnight. */
function inQuiet(m, start, end) {
  if (start === end) return false;
  return start < end ? m >= start && m < end : m >= start || m < end;
}

/** Outcome as the engine sees it: a long-unanswered nudge counts as ignored. */
function effective(e, now) {
  return e.outcome == null && now - e.at > PENDING_STALE ? 'ignored' : e.outcome;
}

/** Task she chose, else first open non-carried today task. Carried tasks only come via carried_over. */
function pickTarget(tasks, currentTaskId) {
  const open = tasks.filter((t) => !t.checked);
  return open.find((t) => t.id === currentTaskId) || open.find((t) => t.isToday && !t.carried) || null;
}

/** Fill a template; variant rotates per kind so the same wording never repeats back to back. */
function build(kind, action, task, sent, extra) {
  const set = WORDS[kind];
  const last = [...sent].reverse().find((e) => e.kind === kind && Number.isInteger(e.v));
  const v = kind === 'wrapup' && !task ? set.length - 1 : last ? (last.v + 1) % set.length : sent.length % set.length;   // last wrapup variant is task-free
  const t = task ? clip(task.text) : '';
  const n = { kind, taskId: task ? task.id : null, title: set[v][0], body: set[v][1].replace('{t}', t), action, v };
  if (extra) n.minutes = extra;
  return n;
}

/** Decide the single next nudge, or null. */
function decide(input) {
  const { now, tzOffsetMin = 0, tasks = [], currentTaskId = null, pomo = {}, lastFocusEndedAt = null, snoozedUntil = null } = input;
  const st = input.settings || {};
  const sent = ((input.log && input.log.sent) || []).slice().sort((a, b) => a.at - b.at);
  if (st.nudges === false) return null;
  if (pomo.running || pomo.phase === 'focus' || pomo.phase === 'break') return null;
  if (snoozedUntil != null && now < snoozedUntil) return null;
  const mins = minOf(now, tzOffsetMin);
  if (inQuiet(mins, hm(st.quietStart, 1320), hm(st.quietEnd, 480))) return null;

  const today = dayOf(now, tzOffsetMin);
  const todays = sent.filter((e) => dayOf(e.at, tzOffsetMin) === today);
  if (todays.length >= (st.maxPerDay == null ? 5 : st.maxPerDay)) return null;

  let streak = 0;
  for (let i = sent.length - 1; i >= 0; i--) {
    const o = effective(sent[i], now);
    if (o !== 'ignored' && o !== 'dismissed') break;
    streak++;
  }
  const lastAt = sent.length ? sent[sent.length - 1].at : null;
  if (lastAt != null) {
    if (streak >= STOP_STREAK && dayOf(lastAt, tzOffsetMin) === today) return null;
    if (now - lastAt < (streak >= 2 ? GAP_BACKOFF : GAP_MIN)) return null;
  }
  const cooled = (kind) => {
    const e = [...sent].reverse().find((x) => x.kind === kind);
    return !e || now - e.at >= KIND_COOLDOWN[kind];
  };
  const onceToday = (kind) => !todays.some((e) => e.kind === kind);

  const target = pickTarget(tasks, currentTaskId);
  const doneToday = tasks.filter((t) => t.checked && t.isToday);
  const focusedToday = (lastFocusEndedAt != null && dayOf(lastFocusEndedAt, tzOffsetMin) === today);

  if (target && mins < 720 && onceToday('morning_pick') && todays.length === 0) {
    return build('morning_pick', 'pick', target, sent);
  }
  if (mins >= 1080 && onceToday('wrapup') && (doneToday.length || focusedToday)) {
    return build('wrapup', 'wrapup', doneToday[doneToday.length - 1] || target, sent);
  }
  if (mins >= 600 && onceToday('carried_over') && cooled('carried_over')) {
    const rested = (id) => sent.some((x) => x.kind === 'carried_over' && x.taskId === id && now - x.at < CARRIED_REST);
    const c = tasks.filter((t) => !t.checked && t.carried && t.id !== currentTaskId && !rested(t.id))
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))[0];
    if (c) return build('carried_over', 'triage', c, sent);
  }
  if (target && cooled('idle_start') && (lastFocusEndedAt == null || now - lastFocusEndedAt >= IDLE_AFTER)) {
    return build('idle_start', 'start', target, sent, 5);
  }
  return null;
}

/** Record a nudge (outcome null = just sent) or resolve its pending entry; returns a new log. */
function recordOutcome(log, nudge, outcome, now) {
  const sent = ((log && log.sent) || []).map((e) => ({ ...e }));
  const o = outcome == null ? null : outcome;
  if (o !== null) {
    for (let i = sent.length - 1; i >= 0; i--) {
      const e = sent[i];
      if (e.outcome == null && e.kind === nudge.kind && e.taskId === nudge.taskId) { e.outcome = o; return { ...log, sent }; }
    }
  }
  sent.push({ kind: nudge.kind, at: now, taskId: nudge.taskId, outcome: o, v: nudge.v });
  return { ...log, sent: sent.slice(-MAX_LOG) };
}

module.exports = { decide, recordOutcome, WORDS };
