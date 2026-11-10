'use strict';
const { handler, send, readJson } = require('./_lib/http.js');
const { context } = require('./_lib/context.js');
const chat = require('./_lib/chat.js');
const llm = require('./_lib/llm.js');

// POST /api/chat { message, history: [{role, text}] } → { reply, actions }
module.exports = handler(['POST'], async (req, res) => {
  const { vault } = await context(req, res);
  const b = await readJson(req);
  const out = await chat.respond({ message: b.message, history: b.history, vault, generate: (p) => llm.generate(p, { temperature: 0.3 }) });
  send(res, 200, out);
});
