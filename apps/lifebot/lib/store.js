/**
 * Tiny JSON file store with atomic writes. A corrupt file is moved aside (never silently lost)
 * and the defaults are used instead.
 */
const fs = require('node:fs');
const path = require('node:path');

function createStore(filePath, defaults) {
  let data = clone(defaults);

  function clone(v) { return JSON.parse(JSON.stringify(v)); }

  function load() {
    try {
      const parsed = JSON.parse(fs.readFileSync(filePath, 'utf8'));
      data = { ...clone(defaults), ...parsed };
    } catch (err) {
      if (err.code !== 'ENOENT') {
        try { fs.renameSync(filePath, `${filePath}.corrupt-${Date.now()}`); } catch (_) { /* best effort */ }
      }
      data = clone(defaults);
    }
    return data;
  }

  function save() {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    const tmp = `${filePath}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
    fs.renameSync(tmp, filePath);
  }

  function get() { return data; }

  /** Mutate via fn(data) and persist. */
  function update(fn) {
    fn(data);
    save();
    return data;
  }

  load();
  return { get, update, save, load };
}

module.exports = { createStore };
