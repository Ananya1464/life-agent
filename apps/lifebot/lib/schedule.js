'use strict';
// Which scheduled briefings are due (pure; no I/O). Local time = now - tzOffsetMin*60000 (JS getTimezoneOffset sign).
const MIN = 60000;
const DAY = 1440 * MIN;
const RETRY_AFTER = 30 * MIN;   // after a failed attempt, wait this long before trying again
const MAX_ATTEMPTS = 2;         // per task per day, so a broken task never loops

/** Same slots the Windows scheduler used. `day` is 0=Sunday for weekly tasks. */
const SCHEDULE = [
  { task: 'meal_plan', label: 'Meal plan', time: '07:00' },
  { task: 'ai_edge', label: 'Opportunities and research (AI Edge)', time: '08:00' },
  { task: 'career_prep', label: 'Global career prep: reading list and next steps', time: '09:00', day: 1 },
  { task: 'evening_checkin', label: 'Evening check-in', time: '21:30' },
  { task: 'goal_planner', label: 'Full day plan', time: '21:45' },
  { task: 'tomorrow_planner', label: "Tomorrow's plan", time: '22:00' },
  { task: 'weekly_review', label: 'Weekly review', time: '20:00', day: 0 },
];
const TASKS = SCHEDULE.map((s) => s.task);

const pad = (n) => String(n).padStart(2, '0');
const local = (now, tz) => new Date(now - (tz || 0) * MIN);          // read with getUTC*()
const dayKey = (now, tz) => { const d = local(now, tz); return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`; };
const minutesOf = (hm) => { const m = /^(\d{1,2}):(\d{2})$/.exec(hm); return m ? +m[1] * 60 + +m[2] : 0; };

/**
 * Tasks to run now, earliest slot first. A task is due when its slot today has passed, it has not succeeded today,
 * it is not running, and a failed attempt is old enough to retry (at most MAX_ATTEMPTS a day). Missed slots catch up.
 * runs: { [task]: { day, status: 'ok'|'failed'|'running', at, attempts } }
 */
function due({ now, tzOffsetMin = 0, runs = {}, running = null, schedule = SCHEDULE }) {
  const d = local(now, tzOffsetMin);
  const today = dayKey(now, tzOffsetMin);
  const mins = d.getUTCHours() * 60 + d.getUTCMinutes();
  return schedule
    .filter((s) => s.day === undefined || s.day === d.getUTCDay())
    .filter((s) => mins >= minutesOf(s.time))
    .filter((s) => s.task !== running)
    .filter((s) => {
      const r = runs[s.task];
      if (!r || r.day !== today) return true;
      if (r.status === 'ok' || r.status === 'running') return false;
      return (r.attempts || 0) < MAX_ATTEMPTS && now - (r.at || 0) >= RETRY_AFTER;
    })
    .sort((a, b) => minutesOf(a.time) - minutesOf(b.time));
}

/** Record the start of an attempt (keeps today's attempt count). */
function started(runs, task, now, tzOffsetMin = 0) {
  const today = dayKey(now, tzOffsetMin);
  const prev = runs[task] && runs[task].day === today ? runs[task] : { attempts: 0 };
  return { ...runs, [task]: { day: today, status: 'running', at: now, attempts: (prev.attempts || 0) + 1 } };
}

/** Record the end of an attempt. */
function finished(runs, task, ok, now, error = '') {
  const prev = runs[task] || {};
  return { ...runs, [task]: { ...prev, status: ok ? 'ok' : 'failed', at: now, error: ok ? '' : String(error).slice(0, 300) } };
}

/** The questions Lifebot asks about what she wants to know. Only these choices are accepted and saved. */
const PREF_OPTIONS = {
  wants: ['research_roles', 'remote_jobs', 'fellowships', 'masters_phd', 'scholarships', 'conferences', 'competitions', 'reading'],
  regions: ['India', 'Remote', 'USA', 'UK', 'Europe', 'Singapore', 'Canada', 'Australia', 'Middle East', 'Anywhere'],
  window: ['2 weeks', '1 month', '2 months', '3 months', '6 months', 'any'],
};

/** Validate untrusted answers: unknown choices dropped, free text collapsed to one line and capped. */
function cleanPrefs(input) {
  const i = input && typeof input === 'object' ? input : {};
  const pick = (v, allowed) => (Array.isArray(v) ? allowed.filter((a) => v.includes(a)) : []);
  const text = (v, max) => (typeof v === 'string' ? v.replace(/\s+/g, ' ').trim().slice(0, max) : '');
  return {
    wants: pick(i.wants, PREF_OPTIONS.wants),
    regions: pick(i.regions, PREF_OPTIONS.regions),
    topics: text(i.topics, 300),
    eligibility: text(i.eligibility, 300),
    window: PREF_OPTIONS.window.includes(i.window) ? i.window : '',
    exclude: text(i.exclude, 200),
  };
}

module.exports = { PREF_OPTIONS, cleanPrefs, SCHEDULE, TASKS, RETRY_AFTER, MAX_ATTEMPTS, due, started, finished, dayKey };
