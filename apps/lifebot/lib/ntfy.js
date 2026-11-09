/**
 * Phone push via ntfy.sh. Never throws: returns { ok, error? }.
 */
const https = require('node:https');

const TOPIC_RE = /^[A-Za-z0-9_-]{3,64}$/;

function isValidTopic(topic) {
  return typeof topic === 'string' && TOPIC_RE.test(topic);
}

/** HTTP header values must be latin-1; strip anything else (emoji etc.) from the title. */
function safeHeader(value) {
  return String(value).replace(/[^\x20-\x7e]/g, '').slice(0, 120) || 'Lifebot';
}

function send(topic, title, body, request = https.request) {
  return new Promise((resolve) => {
    if (!isValidTopic(topic)) return resolve({ ok: false, error: 'invalid or missing ntfy topic' });
    const payload = Buffer.from(String(body), 'utf8');
    let settled = false;
    const done = (r) => { if (!settled) { settled = true; resolve(r); } };
    try {
      const req = request({
        hostname: 'ntfy.sh', path: `/${topic}`, method: 'POST', timeout: 8000,
        headers: { Title: safeHeader(title), 'Content-Length': payload.length, Tags: 'bell' },
      }, (res) => {
        res.resume();
        done(res.statusCode >= 200 && res.statusCode < 300
          ? { ok: true } : { ok: false, error: `ntfy responded ${res.statusCode}` });
      });
      req.on('timeout', () => { req.destroy(); done({ ok: false, error: 'ntfy timed out' }); });
      req.on('error', (err) => done({ ok: false, error: err.message }));
      req.end(payload);
    } catch (err) {
      done({ ok: false, error: err.message });
    }
  });
}

module.exports = { send, isValidTopic, safeHeader };
