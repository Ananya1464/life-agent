'use strict';
// The model call: Gemini first, NVIDIA NIM as the fallback (same providers and env names as the desktop agent).
// Keys stay in Vercel's environment variables; the phone never sees them.

const TIMEOUT_MS = 25000;

async function withTimeout(promiseFn) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try { return await promiseFn(ctl.signal); } finally { clearTimeout(t); }
}

async function gemini(prompt, temperature) {
  const key = process.env.GEMINI_API_KEY;
  if (!key) throw new Error('GEMINI_API_KEY not set');
  const model = process.env.GEMINI_MODEL || 'gemini-2.5-flash';
  const r = await withTimeout((signal) => fetch(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`, {
    method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
    body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: prompt }] }], generationConfig: { temperature, maxOutputTokens: 2048 } }),
  }));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`Gemini ${r.status}: ${String((j.error && j.error.message) || '').slice(0, 160)}`);
  const parts = (((j.candidates || [])[0] || {}).content || {}).parts || [];
  const text = parts.filter((p) => !p.thought).map((p) => p.text || '').join('').trim();
  if (!text) throw new Error('Gemini returned an empty answer');
  return text;
}

async function nvidia(prompt, temperature) {
  const key = process.env.NVIDIA_API_KEY;
  if (!key) throw new Error('NVIDIA_API_KEY not set');
  const model = process.env.NVIDIA_MODEL || 'meta/llama-3.3-70b-instruct';
  const r = await withTimeout((signal) => fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
    method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }], temperature, max_tokens: 2048 }),
  }));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`NVIDIA ${r.status}: ${String((j.error && (j.error.message || j.error)) || j.detail || '').slice(0, 160)}`);
  const text = String((((j.choices || [])[0] || {}).message || {}).content || '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
  if (!text) throw new Error('NVIDIA returned an empty answer');
  return text;
}

const PROVIDERS = { gemini, nvidia };

/** Try the primary provider, then the fallback. Throws only when every provider failed. */
async function generate(prompt, { temperature = 0.3 } = {}) {
  const primary = (process.env.LLM_PROVIDER || 'gemini').toLowerCase();
  const fallback = (process.env.LLM_FALLBACK_PROVIDER || (primary === 'gemini' ? 'nvidia' : 'gemini')).toLowerCase();
  const order = [primary, fallback].filter((p, i, a) => PROVIDERS[p] && a.indexOf(p) === i);
  const errors = [];
  for (const p of order) {
    try { return await PROVIDERS[p](prompt, temperature); } catch (e) { errors.push(`${p}: ${e.message}`); }
  }
  throw new Error(errors.join('; ') || 'No AI provider is configured');
}

module.exports = { generate };
