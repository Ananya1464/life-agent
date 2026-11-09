/**
 * Reminder logic (pure, no Electron): create, find due, fire, snooze, complete.
 * Times are ISO strings with a UTC offset; recurrence keeps the local wall-clock time.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Reminders = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  const REPEATS = ['none', 'daily', 'weekdays'];
  const MAX_TEXT = 200;
  const pad = (n) => String(n).padStart(2, '0');

  function toLocalIso(d) {
    const off = -d.getTimezoneOffset();
    const a = Math.abs(off);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}` +
      `${off >= 0 ? '+' : '-'}${pad(Math.floor(a / 60))}:${pad(a % 60)}`;
  }

  function parseAt(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function newId() {
    return 'r_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  /** Validate input and build a pending reminder. Throws Error with a user-readable message. */
  function make(input, now) {
    const text = String((input && input.text) || '').trim();
    if (!text) throw new Error('Reminder text is required');
    if (text.length > MAX_TEXT) throw new Error(`Reminder text is too long (max ${MAX_TEXT})`);
    const repeat = (input && input.repeat) || 'none';
    if (!REPEATS.includes(repeat)) throw new Error(`Repeat must be one of: ${REPEATS.join(', ')}`);
    const when = parseAt(input && input.at);
    if (!when) throw new Error('Reminder time is not a valid date');
    if (when.getTime() < now.getTime() - 60000) throw new Error('Reminder time is in the past');
    return { id: newId(), text, at: toLocalIso(when), repeat, status: 'pending', createdAt: toLocalIso(now) };
  }

  /** Next occurrence strictly after `after`, preserving wall-clock time; null for one-off. */
  function nextOccurrence(atDate, repeat, after) {
    if (repeat === 'none') return null;
    const d = new Date(atDate.getTime());
    for (let i = 0; i < 4000; i++) {
      d.setDate(d.getDate() + 1);
      const weekend = d.getDay() === 0 || d.getDay() === 6;
      if (d.getTime() > after.getTime() && !(repeat === 'weekdays' && weekend)) return d;
    }
    return null;
  }

  function due(list, now) {
    return list.filter((r) => {
      const at = parseAt(r.at);
      return r.status === 'pending' && at && at.getTime() <= now.getTime();
    });
  }

  /** Mark a due reminder as fired. Repeating ones advance to the next slot and stay pending. */
  function fire(r, now) {
    if (r.repeat === 'none') return { ...r, status: 'fired', firedAt: toLocalIso(now) };
    const next = nextOccurrence(parseAt(r.at), r.repeat, now);
    return { ...r, at: next ? toLocalIso(next) : r.at, status: next ? 'pending' : 'done', lastFiredAt: toLocalIso(now) };
  }

  function complete(r, now) {
    if (r.repeat !== 'none') return r;
    return { ...r, status: 'done', completedAt: toLocalIso(now) };
  }

  function snooze(r, minutes, now) {
    const m = Math.min(Math.max(Math.round(Number(minutes) || 10), 1), 24 * 60);
    return { ...r, status: 'pending', at: toLocalIso(new Date(now.getTime() + m * 60000)) };
  }

  function describe(r) {
    const at = parseAt(r.at);
    const when = at
      ? at.toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
      : r.at;
    return r.repeat && r.repeat !== 'none' ? `${when} (${r.repeat})` : when;
  }

  return { REPEATS, toLocalIso, parseAt, make, nextOccurrence, due, fire, complete, snooze, describe };
}));
