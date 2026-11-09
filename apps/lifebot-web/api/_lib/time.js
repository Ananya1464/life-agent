'use strict';
// Local-time helpers in Ananya's time zone (the server runs in UTC).

const TZ = () => process.env.TIMEZONE || 'Asia/Kolkata';
const pad = (n) => String(n).padStart(2, '0');

/** Offset of the zone at instant `d`, in minutes east of UTC (e.g. +330 for India). */
function offsetMinutes(d = new Date(), tz = TZ()) {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'longOffset' }).formatToParts(d);
  const name = (parts.find((p) => p.type === 'timeZoneName') || {}).value || 'GMT';
  const m = /GMT([+-])(\d{1,2})(?::(\d{2}))?/.exec(name);
  if (!m) return 0;
  return (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3] || 0));
}

/** Wall-clock fields of instant `d` in the zone. */
function local(d = new Date(), tz = TZ()) {
  const shifted = new Date(d.getTime() + offsetMinutes(d, tz) * 60000);
  return {
    y: shifted.getUTCFullYear(), mo: shifted.getUTCMonth() + 1, d: shifted.getUTCDate(),
    h: shifted.getUTCHours(), mi: shifted.getUTCMinutes(), dow: shifted.getUTCDay(),
  };
}

function todayIso(d = new Date()) {
  const l = local(d);
  return `${l.y}-${pad(l.mo)}-${pad(l.d)}`;
}

/** "2026-11-09T14:05" in local time, the format Lifebot writes into "(done ...)" markers. */
function stamp(d = new Date()) {
  const l = local(d);
  return `${l.y}-${pad(l.mo)}-${pad(l.d)}T${pad(l.h)}:${pad(l.mi)}`;
}

function offsetString(mins) {
  const a = Math.abs(mins);
  return `${mins >= 0 ? '+' : '-'}${pad(Math.floor(a / 60))}:${pad(a % 60)}`;
}

/** ISO with the zone's offset, e.g. 2026-11-09T14:05+05:30. */
function localIso(d = new Date()) {
  return `${stamp(d)}${offsetString(offsetMinutes(d))}`;
}

/**
 * Parse a datetime a person or the model typed. A value without an offset ("2026-11-09T09:00") is local time
 * in the zone; a value with Z or an offset is taken as written. Returns a Date or null.
 */
function parseLocal(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  const v = value.trim().replace(' ', 'T');
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(v)) {
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(v);
  if (!m) return null;
  const guess = Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
  // subtract the offset that applies at that wall-clock time (two passes cover DST edges)
  let t = guess - offsetMinutes(new Date(guess)) * 60000;
  t = guess - offsetMinutes(new Date(t)) * 60000;
  return new Date(t);
}

module.exports = { TZ, offsetMinutes, local, todayIso, stamp, localIso, parseLocal, offsetString };
