'use strict';
const { handler, send, query, httpError } = require('./_lib/http.js');
const { context } = require('./_lib/context.js');
const { clean } = require('./_lib/vault.js');
const Brief = require('../lib/briefitems.js');

// GET /api/note?path=Briefings/2026-11-09 meal_plan.md → { path, text, modified, suggestions }
// GET /api/note?folder=02_EXECUTION/Goals → { folder, entries }
module.exports = handler(['GET'], async (req, res) => {
  const { vault } = await context(req, res);
  const q = query(req);
  if (q.folder !== undefined) {
    const folder = clean(q.folder);
    const entries = (await vault.list(folder)).filter((e) => e.isFolder || /\.md$/i.test(e.name))
      .sort((a, b) => (b.isFolder - a.isFolder) || a.name.localeCompare(b.name));
    return send(res, 200, { folder, entries });
  }
  const p = clean(q.path);
  if (!/\.md$/i.test(p)) throw httpError(400, 'Only notes (.md) can be opened here');
  const f = await vault.read(p);
  if (!f) throw httpError(404, `${p} was not found in the vault`);
  const suggestions = p.startsWith('Briefings/') ? Brief.suggestTasks(f.text) : [];
  send(res, 200, { path: p, text: f.text, modified: f.modified, suggestions });
});
