'use strict';
// Read and write files in the Obsidian vault.
//   GraphVault: the vault in OneDrive, through Microsoft Graph (production).
//   FsVault:    a local folder (VAULT_LOCAL_DIR) for development and tests.
// Paths are relative to the vault root (ANANYA-OS). Writes are limited to the files this app owns.

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { httpError } = require('./http.js');

const GRAPH = 'https://graph.microsoft.com/v1.0';
const HIDDEN = /^(\.obsidian|\.trash|09_RUNTIME)(\/|$)/i;          // never read through the app
const WRITABLE = [/^Tasks\.md$/, /^Lifebot\/phone-[a-z-]+\.(json|jsonl)$/];

/** Normalise and validate a vault-relative path. Throws 400 on anything that escapes the vault. */
function clean(rel, { forWrite = false } = {}) {
  const p = String(rel || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
  if (p.split('/').some((s) => s === '..' || s === '.')) throw httpError(400, 'Invalid path');
  if (p && HIDDEN.test(p)) throw httpError(403, 'That part of the vault is private to the laptop');
  if (forWrite && !WRITABLE.some((re) => re.test(p))) throw httpError(403, 'The phone app cannot change that file');
  if (p.length > 400) throw httpError(400, 'Path too long');
  return p;
}

function conflict() {
  return httpError(409, 'This file changed on another device. Reloaded the latest version; try again.', { conflict: true });
}

class GraphVault {
  constructor(accessToken, root = process.env.VAULT_PATH || 'Desktop/ananya/ANANYA-OS') {
    this.token = accessToken;
    this.root = root.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
  }

  itemUrl(rel) {
    const full = [this.root, rel].filter(Boolean).join('/');
    return `${GRAPH}/me/drive/root:/${full.split('/').map(encodeURIComponent).join('/')}`;
  }

  async call(url, init = {}) {
    const r = await fetch(url, { ...init, headers: { Authorization: `Bearer ${this.token}`, ...(init.headers || {}) } });
    if (r.status === 401) throw httpError(401, 'Your Microsoft sign-in expired', { signIn: true });
    if (r.status === 429 || r.status === 503) throw httpError(503, 'OneDrive is busy. Try again in a minute.');
    return r;
  }

  async read(rel) {
    const p = clean(rel);
    const meta = await this.call(this.itemUrl(p));
    if (meta.status === 404) return null;
    if (!meta.ok) throw httpError(502, `OneDrive could not open ${p} (${meta.status})`);
    const item = await meta.json();
    if (item.folder) throw httpError(400, `${p} is a folder`);
    const dl = item['@microsoft.graph.downloadUrl'];
    const body = dl ? await fetch(dl) : await this.call(`${this.itemUrl(p)}:/content`);
    if (!body.ok) throw httpError(502, `OneDrive could not download ${p} (${body.status})`);
    return { text: await body.text(), etag: item.eTag || item.cTag || null, modified: item.lastModifiedDateTime || null };
  }

  async readBinary(rel) {
    const p = clean(rel);
    const r = await this.call(`${this.itemUrl(p)}:/content`);
    if (r.status === 404) return null;
    if (!r.ok) throw httpError(502, `OneDrive could not download ${p} (${r.status})`);
    return Buffer.from(await r.arrayBuffer());
  }

  /** Write text. With `etag`, refuses (409) if the file changed since it was read. */
  async write(rel, text, { etag } = {}) {
    const p = clean(rel, { forWrite: true });
    const headers = { 'Content-Type': 'text/plain; charset=utf-8' };
    if (etag) headers['If-Match'] = etag;
    const r = await this.call(`${this.itemUrl(p)}:/content`, { method: 'PUT', headers, body: text });
    if (r.status === 412) throw conflict();
    if (!r.ok) throw httpError(502, `OneDrive could not save ${p} (${r.status})`);
    const item = await r.json().catch(() => ({}));
    return { etag: item.eTag || item.cTag || null };
  }

  async list(rel) {
    const p = clean(rel);
    let url = `${this.itemUrl(p)}:/children?$top=200&$select=name,lastModifiedDateTime,size,folder,file`;
    if (!p) url = `${this.itemUrl('')}:/children?$top=200&$select=name,lastModifiedDateTime,size,folder,file`;
    const out = [];
    for (let page = 0; url && page < 10; page++) {
      const r = await this.call(url);
      if (r.status === 404) return [];
      if (!r.ok) throw httpError(502, `OneDrive could not list ${p || 'the vault'} (${r.status})`);
      const j = await r.json();
      for (const it of j.value || []) out.push({ name: it.name, modified: it.lastModifiedDateTime, size: it.size, isFolder: !!it.folder });
      url = j['@odata.nextLink'] || null;
    }
    return out.filter((e) => !HIDDEN.test(p ? `${p}/${e.name}` : e.name));
  }
}

class FsVault {
  constructor(dir = process.env.VAULT_LOCAL_DIR) { this.dir = path.resolve(dir); }
  abs(p) { return path.join(this.dir, ...p.split('/').filter(Boolean)); }
  static tag(text) { return '"' + crypto.createHash('sha1').update(text).digest('hex') + '"'; }

  async read(rel) {
    const p = clean(rel);
    try {
      const text = await fs.readFile(this.abs(p), 'utf8');
      const st = await fs.stat(this.abs(p));
      return { text, etag: FsVault.tag(text), modified: st.mtime.toISOString() };
    } catch (e) { if (e.code === 'ENOENT') return null; throw e; }
  }

  async readBinary(rel) {
    const p = clean(rel);
    try { return await fs.readFile(this.abs(p)); } catch (e) { if (e.code === 'ENOENT') return null; throw e; }
  }

  async write(rel, text, { etag } = {}) {
    const p = clean(rel, { forWrite: true });
    if (etag) {
      const cur = await this.read(p);
      if (cur && cur.etag !== etag) throw conflict();
    }
    await fs.mkdir(path.dirname(this.abs(p)), { recursive: true });
    await fs.writeFile(this.abs(p), text, 'utf8');
    return { etag: FsVault.tag(text) };
  }

  async list(rel) {
    const p = clean(rel);
    try {
      const names = await fs.readdir(this.abs(p), { withFileTypes: true });
      const out = [];
      for (const d of names) {
        const st = await fs.stat(path.join(this.abs(p), d.name));
        out.push({ name: d.name, modified: st.mtime.toISOString(), size: st.size, isFolder: d.isDirectory() });
      }
      return out.filter((e) => !HIDDEN.test(p ? `${p}/${e.name}` : e.name));
    } catch (e) { if (e.code === 'ENOENT') return []; throw e; }
  }
}

function vaultFor(user) {
  if (process.env.VAULT_LOCAL_DIR && !process.env.VERCEL) return new FsVault();
  return new GraphVault(user.accessToken);
}

module.exports = { GraphVault, FsVault, vaultFor, clean, WRITABLE };
