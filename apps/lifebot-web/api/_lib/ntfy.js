'use strict';
// Phone push through ntfy (same topic the desktop Lifebot uses). Scheduled messages carry a sequence id so
// they can be cancelled or moved: POST /<topic>/<seq> with an At header, DELETE /<topic>/<seq> to cancel.
// ntfy.sh accepts delays from 10 seconds up to 3 days.

const TOPIC_RE = /^[A-Za-z0-9_-]{3,64}$/;
const SEQ_RE = /^[A-Za-z0-9_-]{1,64}$/;
const MAX_DELAY_MS = 3 * 24 * 3600 * 1000;
const MIN_DELAY_MS = 15 * 1000;

const base = () => (process.env.NTFY_SERVER || 'https://ntfy.sh').replace(/\/+$/, '');
const topic = () => process.env.NTFY_TOPIC || '';
const ready = () => TOPIC_RE.test(topic());

/** HTTP header values must be plain ASCII. */
const header = (v) => String(v).replace(/[^\x20-\x7e]/g, '').slice(0, 120) || 'Lifebot';

function headers(extra = {}) {
  const h = { ...extra };
  if (process.env.NTFY_TOKEN) h.Authorization = `Bearer ${process.env.NTFY_TOKEN}`;
  return h;
}

async function post(path, body, extra) {
  if (!ready()) return { ok: false, error: 'NTFY_TOPIC is not set' };
  try {
    const r = await fetch(`${base()}/${topic()}${path}`, { method: 'POST', headers: headers(extra), body: String(body).slice(0, 3900) });
    return r.ok ? { ok: true } : { ok: false, error: `ntfy responded ${r.status}` };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

function sendNow(title, body, tags = 'bell') {
  return post('', body, { Title: header(title), Tags: tags });
}

/** Schedule `body` for Date `at` under sequence id `seq` (re-posting the same seq replaces it). */
function schedule(seq, at, title, body, tags = 'bell') {
  if (!SEQ_RE.test(seq)) return Promise.resolve({ ok: false, error: 'bad sequence id' });
  const lead = at.getTime() - Date.now();
  if (lead < MIN_DELAY_MS || lead > MAX_DELAY_MS) return Promise.resolve({ ok: false, error: 'outside the ntfy scheduling window' });
  return post(`/${seq}`, body, { Title: header(title), Tags: tags, At: String(Math.floor(at.getTime() / 1000)), Priority: 'high' });
}

async function cancel(seq) {
  if (!ready() || !SEQ_RE.test(seq)) return { ok: false };
  try {
    const r = await fetch(`${base()}/${topic()}/${seq}`, { method: 'DELETE', headers: headers() });
    return { ok: r.ok || r.status === 404 };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

module.exports = { ready, sendNow, schedule, cancel, MAX_DELAY_MS, MIN_DELAY_MS };
