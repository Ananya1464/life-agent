/**
 * Which day each task belongs to (pure; no I/O).
 * The shared checklist file has no dates, so Lifebot remembers the day it first saw each task.
 * Tasks first seen before today and still open are "carried over"; the floating card shows today only.
 */
const MARKER = ':lifebot:';

/** Stable key for a task: its text slug (plus #n for duplicates), without the day prefix of its id. */
function keyOf(id) {
  const s = String(id);
  const i = s.indexOf(MARKER);
  return i === -1 ? s : s.slice(i + MARKER.length);
}

/** Re-point an id at another day, keeping the text part. */
function idForDay(id, dateIso) {
  const s = String(id);
  const i = s.indexOf(MARKER);
  return i === -1 ? s : `${dateIso}${s.slice(i)}`;
}

/**
 * Annotate tasks with `date` (first seen), `isToday` and `carried`.
 * Returns { tasks, firstSeen, changed } where firstSeen is the updated map (unseen keys added, gone keys dropped).
 */
function annotate(tasks, firstSeen, todayIso) {
  const known = firstSeen || {};
  const next = {};
  let changed = false;
  const out = tasks.map((t) => {
    const key = keyOf(t.id);
    let date = known[key];
    if (!date) {
      date = t.checked && t.doneTimestamp ? String(t.doneTimestamp).slice(0, 10) : todayIso;   // a done marker tells us the day
      changed = true;
    }
    next[key] = date;
    return { ...t, date, isToday: date >= todayIso, carried: !t.checked && date < todayIso };
  });
  if (tasks.length && Object.keys(known).some((k) => !(k in next))) changed = true;
  // never wipe the memory because the file was momentarily empty or unreadable
  return { tasks: out, firstSeen: tasks.length ? next : known, changed: tasks.length ? changed : false };
}

module.exports = { keyOf, idForDay, annotate };
