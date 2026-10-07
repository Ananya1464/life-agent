const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// pixel.js and src/life_agent/pixel.py must describe identical sprites
const js = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'pixel.js'), 'utf8');
const py = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'src', 'life_agent', 'pixel.py'), 'utf8');

function grids(src, rowRe) {
  const out = {};
  for (const m of src.matchAll(/(GEM|FLAME|CHEST)\s*=\s*\[([\s\S]*?)\]/g)) {
    out[m[1]] = [...m[2].matchAll(rowRe)].map((r) => r[1]);
  }
  return out;
}

test('sprite grids match between JS and Python and are rectangular', () => {
  const a = grids(js, /'([.a-z]+)'/g);
  const b = grids(py, /"([.a-z]+)"/g);
  assert.deepEqual(Object.keys(a).sort(), ['CHEST', 'FLAME', 'GEM']);
  for (const name of Object.keys(a)) {
    assert.deepEqual(a[name], b[name], `${name} differs`);
    assert.ok(a[name].every((row) => row.length === a[name][0].length), `${name} is not rectangular`);
  }
});

test('palettes match between JS and Python', () => {
  const norm = (name, body, entry) => `${name}:${[...body.matchAll(entry)].map((c) => c[1] + c[2]).sort().join(',')}`;
  const fromJs = [...js.matchAll(/(gem|flame|chest):\s*\{([^}]*)\}/g)]
    .map((m) => norm(m[1], m[2], /(\w):\s*'(#\w+)'/g)).sort();
  const fromPy = [...py.matchAll(/"(gem|flame|chest)":\s*\{([^}]*)\}/g)]
    .map((m) => norm(m[1], m[2], /"(\w)":\s*"(#\w+)"/g)).sort();
  assert.equal(fromJs.length, 3);
  assert.deepEqual(fromJs, fromPy);
});
