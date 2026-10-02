/**
 * Locating the repo, reading its .env, and choosing a Python interpreter that has the
 * dependencies the agent needs. Pure functions with injectable I/O, so they are testable.
 */
const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');

const REQUIRED_MODULES = ['requests', 'zoneinfo'];
const OPTIONAL_MODULES = ['google.genai', 'openai'];
const PROBE = [
  'import importlib',
  `mods = ${JSON.stringify([...REQUIRED_MODULES, ...OPTIONAL_MODULES])}`,
  'ok = []',
  'for m in mods:',
  '    try:',
  '        importlib.import_module(m); ok.append(m)',
  '    except Exception:',
  '        pass',
  'print(",".join(ok))',
].join('\n');

function findRepoRoot(startDir, exists = fs.existsSync) {
  let dir = path.resolve(startDir);
  for (let i = 0; i < 8; i++) {
    if (exists(path.join(dir, 'src', 'life_agent', '__init__.py'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function parseDotEnv(text) {
  const out = {};
  for (const raw of String(text || '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const i = line.indexOf('=');
    const key = line.slice(0, i).trim();
    let value = line.slice(i + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (key) out[key] = value;
  }
  return out;
}

function candidatePythons(repoRoot, env = process.env, exists = fs.existsSync) {
  const list = [];
  if (env.LIFE_AGENT_PYTHON) list.push(env.LIFE_AGENT_PYTHON);
  const venv = path.join(repoRoot, '.venv', 'Scripts', 'python.exe');
  if (exists(venv)) list.push(venv);
  list.push('python');
  return [...new Set(list)];
}

function runProbe(python) {
  return new Promise((resolve) => {
    execFile(python, ['-c', PROBE], { timeout: 15000, windowsHide: true }, (err, stdout) => {
      resolve(err ? { ok: false } : { ok: true, modules: String(stdout).trim().split(',').filter(Boolean) });
    });
  });
}

/** Pick the interpreter that can import the most modules; it must have every required one. */
async function pickPython(candidates, probe = runProbe) {
  let best = null;
  for (const python of candidates) {
    const res = await probe(python);
    if (!res.ok || !REQUIRED_MODULES.every((m) => res.modules.includes(m))) continue;
    const score = OPTIONAL_MODULES.filter((m) => res.modules.includes(m)).length;
    if (!best || score > best.score) {
      best = { python, score, missing: OPTIONAL_MODULES.filter((m) => !res.modules.includes(m)) };
    }
    if (score === OPTIONAL_MODULES.length) break;
  }
  return best;
}

module.exports = { findRepoRoot, parseDotEnv, candidatePythons, pickPython, REQUIRED_MODULES, OPTIONAL_MODULES };
