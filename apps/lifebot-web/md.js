/* Minimal, safe Markdown renderer for vault notes (briefings, dashboard, goals).
   Everything is escaped first; only the formatting below becomes HTML. Obsidian embeds ![[file.svg|760]] become
   images from /api/image. Lines that briefitems.js turned into task ideas get an "+ Add" button. */
(function (root) {
  'use strict';
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function inline(text) {
    let s = esc(text);
    s = s.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);
    s = s.replace(/!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]/g, (_, name) => {
      const n = name.trim();
      return /\.(svg|png)$/i.test(n) ? `<img src="/api/image?name=${encodeURIComponent(n)}" alt="${n}" loading="lazy">` : `<em>${n}</em>`;
    });
    s = s.replace(/\[\[([^\]|]+?)(?:\|([^\]]*))?\]\]/g, (_, target, label) => `<em>${label || target}</em>`);
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`);
    s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (_, pre, url) => `${pre}<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/__([^_]+)__/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
    return s;
  }

  function ideaWrap(html, line, ideas) {
    const idea = ideas.get(line);
    if (!idea) return html;
    return `<div class="idea"><div>${html}</div><button class="add-idea" type="button" data-idea="${esc(idea.text)}">+ Add</button></div>`;
  }

  function render(markdown, opts = {}) {
    const ideas = new Map((opts.suggestions || []).map((s) => [s.line, s]));
    const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
    const out = [];
    let i = 0;
    if (lines[0] === '---') {                                   // skip frontmatter, keep line numbering
      const end = lines.indexOf('---', 1);
      if (end > 0) i = end + 1;
    }
    let list = null;                                            // 'ul' | 'ol'
    let para = [];
    const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
    const flushPara = () => { if (para.length) { out.push(`<p>${para.map((p) => ideaWrap(inline(p.text), p.line, ideas)).join('<br>')}</p>`); para = []; } };

    for (; i < lines.length; i++) {
      const raw = lines[i];
      const line = raw.replace(/\s+$/, '');
      if (/^```/.test(line)) {
        flushPara(); closeList();
        const code = [];
        for (i++; i < lines.length && !/^```/.test(lines[i]); i++) code.push(lines[i]);
        out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);
        continue;
      }
      if (!line.trim()) { flushPara(); closeList(); continue; }
      let m;
      if ((m = /^(#{1,6})\s+(.*)$/.exec(line))) {
        flushPara(); closeList();
        const lvl = Math.min(4, m[1].length);
        out.push(ideaWrap(`<h${lvl}>${inline(m[2])}</h${lvl}>`, i, ideas));
        continue;
      }
      if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { flushPara(); closeList(); out.push('<hr>'); continue; }
      if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
        flushPara(); closeList();
        const cells = (l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
        const head = cells(line);
        const rows = [];
        for (i += 2; i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i]); i++) rows.push(cells(lines[i]));
        i--;
        out.push('<div class="table-wrap"><table><thead><tr>' + head.map((h) => `<th>${inline(h)}</th>`).join('') + '</tr></thead><tbody>'
          + rows.map((r) => '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table></div>');
        continue;
      }
      if ((m = /^\s*>\s?(.*)$/.exec(line))) { flushPara(); closeList(); out.push(`<blockquote>${ideaWrap(inline(m[1]), i, ideas)}</blockquote>`); continue; }
      if ((m = /^\s*[-*+]\s+(.*)$/.exec(line)) || (m = /^\s*\d+[.)]\s+(.*)$/.exec(line))) {
        flushPara();
        const kind = /^\s*\d/.test(line) ? 'ol' : 'ul';
        if (list !== kind) { closeList(); out.push(`<${kind}>`); list = kind; }
        const cb = /^\[([ xX])\]\s*(.*)$/.exec(m[1]);
        const body = cb ? `${cb[1].trim() ? '&#9745;' : '&#9744;'} ${inline(cb[2])}` : inline(m[1]);
        out.push(`<li${cb ? ' class="chk"' : ''}>${ideaWrap(body, i, ideas)}</li>`);
        continue;
      }
      closeList();
      para.push({ text: line.trim(), line: i });
    }
    flushPara(); closeList();
    return out.join('\n');
  }

  root.LifebotMarkdown = { render, escape: esc };
}(typeof self !== 'undefined' ? self : this));
