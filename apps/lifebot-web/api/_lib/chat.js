'use strict';
// Lifebot chat on the phone: a port of src/life_agent/lifebot/chat.py. Same persona, same one-JSON-object-per-step
// tool loop. Tools here act on the vault in OneDrive (tasks, reminders, notes, briefings, the Focus Log).
// Tools that need the laptop (git project status) are not offered.

const T = require('./time.js');
const store = require('./store.js');
const { clean } = require('./vault.js');

const MAX_TOOL_STEPS = 4;
const HISTORY_TURNS = 10;
const MAX_MESSAGE_CHARS = 2000;
const PROFILE_FILE = '00_SYSTEM/ME.md';

const PERSONA = `You are Lifebot, Ananya's personal chief of staff. Right now she is using you on her phone. You help with tasks, focus sessions, reminders, planning, and questions about her notes and recent focus data. She wants to understand and own her work, so explain briefly and do not take over.

HOW YOU WORK
1. Separate what is VERIFIED (from a tool result or the state below) from ASSUMPTIONS and from what you could not check. Label them when it matters: Verified / Not verified / Assumption. Never present a guess as a fact.
2. Ask before assuming. If something essential is missing (available hours, wake and sleep times, fixed commitments, deadlines, which project matters most), ask one short question instead of inventing it. Do not build a strict hourly schedule until you know her available time; until then offer flexible blocks.
3. Never claim an action happened unless a tool result says so. Writing a plan, or issuing a tool call, is not completion. You cannot run tests, send messages, submit applications, or delete anything; say so plainly and tell her what she must do.
4. Never invent deadlines, people, applications, test results, statistics, notes, tasks or reminders. If a deadline is not given, say none is known and mark any date you propose as "proposed".
5. Plan in small testable steps: one phase, one decision, one artifact, test, then proceed. Give each step an acceptance criterion. Prefer finishing and verifying one milestone over starting several. Defer lower priorities explicitly. Avoid scope creep.
6. Use honest status words: proposed, in progress, verified, blocked. Mark nothing complete without evidence.
7. Privacy first: use only what is needed from her notes, do not repeat private details unnecessarily, and ask before any consequential action (sending, submitting, deleting, pushing).
8. For an end-of-day report give: completed with evidence, blocked, deferred, next actions. No aspirational summaries.

STYLE: warm, direct, concrete, no emojis, never guilt or shame. She is reading on a phone: simple replies stay short (a few sentences). A requested plan or report may be structured with short headings and bullets, under about 250 words.

TOOLS: when she asks for something a tool can do (add or complete a task, set a reminder, start focus on a task, read notes or briefings), use the tool, then confirm in one short sentence based on the result. Reminder times must be future local datetimes like 2026-10-02T09:00 (her time zone); resolve words like "tomorrow 9am" or "in 30 minutes" from the current time given below. If a tool returns an Error, fix the arguments and retry once, or explain plainly. Project git status is only available on her laptop.`;

function extractJson(text) {
  text = String(text || '').trim();
  const candidates = [];
  const fenced = /```(?:json)?\s*(\{[\s\S]*?\})\s*```/.exec(text);
  if (fenced) candidates.push(fenced[1]);
  candidates.push(text);
  const start = text.indexOf('{');
  if (start !== -1) {
    let depth = 0, inStr = false, esc = false;
    for (let i = start; i < text.length; i++) {
      const ch = text[i];
      if (inStr) { if (esc) esc = false; else if (ch === '\\') esc = true; else if (ch === '"') inStr = false; continue; }
      if (ch === '"') inStr = true;
      else if (ch === '{') depth++;
      else if (ch === '}') { depth--; if (depth === 0) { candidates.push(text.slice(start, i + 1)); break; } }
    }
  }
  for (const c of candidates) {
    try { const o = JSON.parse(c); if (o && typeof o === 'object' && !Array.isArray(o)) return o; } catch { /* next */ }
  }
  return null;
}

function tool(fn, desc, params) { return { fn, desc, params }; }

function buildTools(ctx) {
  const { vault } = ctx;
  return {
    list_tasks: tool(async () => {
      const v = await store.loadTasks(vault);
      return v.tasks.length ? v.tasks.map((t) => `- [${t.checked ? 'x' : ' '}] ${t.text} (id ${t.id})`).join('\n') : 'No tasks yet.';
    }, 'Her current task list (Tasks.md in her vault).', {}),
    add_task: tool(async (a) => {
      const { task } = await store.taskOp(vault, { op: 'add', text: a.text });
      ctx.actions.push({ type: 'tasks_changed' });
      return `Task added: '${task.text}'.`;
    }, 'Add a task to her list.', { text: 'task text' }),
    complete_task: tool(async (a) => {
      const view = await store.loadTasks(vault);
      const wanted = String(a.task || '').trim().toLowerCase();
      const t = view.tasks.find((x) => x.id === a.task) || view.tasks.find((x) => !x.checked && x.text.toLowerCase() === wanted)
        || view.tasks.find((x) => !x.checked && wanted && x.text.toLowerCase().includes(wanted));
      if (!t) return 'Error: no open task matches that. Use list_tasks first.';
      await store.taskOp(vault, { op: 'toggle', id: t.id, text: t.text, checked: true });
      ctx.actions.push({ type: 'tasks_changed' });
      return `Marked done: '${t.text}'.`;
    }, 'Tick off one of her open tasks. Only when she says she finished it.', { task: 'task text or id' }),
    list_reminders: tool(async () => {
      const { list } = await store.reminderOp(vault, { op: 'sync' });
      const items = list.filter((r) => r.status === 'pending');
      return items.length ? items.map((r) => `- ${r.text} at ${r.at}${r.repeat !== 'none' ? ` (repeats ${r.repeat})` : ''}`).join('\n') : 'No upcoming reminders set from the phone.';
    }, 'Her upcoming reminders set from the phone app.', {}),
    add_reminder: tool(async (a) => {
      try {
        const { created } = await store.reminderOp(vault, { op: 'add', text: a.text, at: a.at, repeat: (a.repeat || 'none').toLowerCase() });
        ctx.actions.push({ type: 'reminders_changed' });
        return `Reminder set: '${created.text}' at ${created.at}${created.repeat !== 'none' ? `, repeats ${created.repeat}` : ''}.`;
      } catch (e) { return `Error: ${e.message}`; }
    }, "Create a reminder that pushes to her phone. 'at' is a local datetime in the future; 'repeat' is none, daily or weekdays.",
    { text: 'what to remind', at: '2026-10-02T09:00', repeat: 'none' }),
    start_focus: tool(async (a) => {
      const view = await store.loadTasks(vault);
      const wanted = String(a.task || '').trim().toLowerCase();
      const open = view.tasks.filter((t) => !t.checked);
      const t = open.find((x) => x.id === a.task) || open.find((x) => x.text.toLowerCase() === wanted) || open.find((x) => wanted && x.text.toLowerCase().includes(wanted));
      if (!t) return 'Error: no open task matches that. Use list_tasks first or add_task.';
      ctx.actions.push({ type: 'start_focus', taskId: t.id, text: t.text });
      return `Starting a focus session on '${t.text}' (the app opens the timer).`;
    }, 'Start a focus session on one of her open tasks.', { task: 'task text or id' }),
    focus_summary: tool(async () => {
      const f = await vault.read('Dashboard/Focus Log.md');
      if (!f) return 'No Focus Log found in the vault yet.';
      return 'From Dashboard/Focus Log.md (updated by the laptop app; sessions done on the phone since then are not in it):\n' + f.text.slice(0, 5000);
    }, 'Facts about her recent focus sessions (the Focus Log the laptop writes).', {}),
    latest_briefing: tool(async (a) => {
      const kind = String(a.kind || '').trim().toLowerCase().replace(/[^a-z_]/g, '');
      const files = (await vault.list('Briefings')).filter((e) => !e.isFolder && e.name.endsWith('.md') && (!kind || e.name.includes(kind)));
      files.sort((x, y) => y.name.localeCompare(x.name));
      if (!files.length) return 'No briefing found.';
      const f = await vault.read(`Briefings/${files[0].name}`);
      return `Briefings/${files[0].name}:\n` + String(f ? f.text : '').slice(0, 6000);
    }, 'Read her latest saved briefing. kind is one of meal_plan, ai_edge, career_prep, evening_checkin, goal_planner, tomorrow_planner, weekly_review, or empty for the newest of any kind.', { kind: 'meal_plan' }),
    list_notes: tool(async (a) => {
      const folder = clean(a.folder || '');
      const items = await vault.list(folder);
      const lines = items.map((e) => `${folder ? folder + '/' : ''}${e.name}${e.isFolder ? '/' : ''}`).sort();
      return lines.slice(0, 80).join('\n') + (lines.length > 80 ? `\n[${lines.length - 80} more]` : '') || 'No notes found.';
    }, 'List notes in her Obsidian vault (read-only).', { folder: 'optional subfolder' }),
    read_note: tool(async (a) => {
      const p = clean(a.path || '');
      if (!p) return "Error: 'path' is required.";
      const f = await vault.read(p);
      if (!f) return `Error: ${p} was not found.`;
      return f.text.slice(0, 6000) + (f.text.length > 6000 ? '\n[truncated]' : '');
    }, 'Read one vault note by relative path (read-only).', { path: 'relative/path.md' }),
  };
}

function describe(tools) {
  return Object.entries(tools).map(([name, t]) => {
    const args = Object.entries(t.params).map(([k, v]) => `"${k}": "${v}"`).join(', ');
    return `- ${name}({${args}}): ${t.desc}`;
  }).join('\n');
}

async function profileBlock(vault) {
  try {
    const f = await vault.read(PROFILE_FILE);
    if (f && f.text.trim()) return 'HER PROFILE (from 00_SYSTEM/ME.md in her vault, her own words; treat as stated by her, not independently verified):\n' + f.text.trim().slice(0, 3000);
  } catch { /* fall through */ }
  return 'HER PROFILE: none found. If it would change your answer, ask her for goals, hours and commitments.';
}

async function stateBlock(vault) {
  const [tasks, rem] = await Promise.all([store.loadTasks(vault), store.reminderOp(vault, { op: 'sync' }).catch(() => ({ list: [] }))]);
  const taskLines = tasks.tasks.slice(0, 40).map((t) => `- [${t.checked ? 'x' : ' '}] ${t.text} (id ${t.id})`).join('\n') || '(none)';
  const remLines = rem.list.filter((r) => r.status === 'pending').slice(0, 20).map((r) => `- ${r.text} at ${r.at}`).join('\n') || '(none)';
  return `TASKS:\n${taskLines}\n\nUPCOMING REMINDERS (set from the phone):\n${remLines}`;
}

/** Returns { reply, actions }. Never throws. */
async function respond({ message, history, vault, generate }) {
  message = String(message || '').trim().slice(0, MAX_MESSAGE_CHARS);
  if (!message) return { reply: 'Say something and I will help.', actions: [] };
  const ctx = { vault, actions: [] };
  const tools = buildTools(ctx);
  const scratch = [];
  try {
    const now = new Date();
    const l = T.local(now);
    const dayName = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][l.dow];
    const [profile, state] = await Promise.all([profileBlock(vault), stateBlock(vault)]);
    const convo = (Array.isArray(history) ? history : []).slice(-HISTORY_TURNS)
      .map((h) => `${h && h.role === 'user' ? 'Ananya' : 'Lifebot'}: ${String((h && h.text) || '').slice(0, MAX_MESSAGE_CHARS)}`).join('\n');
    for (let step = 0; step <= MAX_TOOL_STEPS; step++) {
      const parts = [PERSONA, `Current local time: ${dayName} ${T.stamp(now).replace('T', ' ')} (${T.TZ()}).`, profile, state,
        'TOOLS:\n' + describe(tools),
        'Answer with ONE JSON object only: {"tool": "<name>", "args": {...}} or {"reply": "<text for Ananya>"}.'];
      if (convo) parts.push('CONVERSATION SO FAR:\n' + convo);
      parts.push(`Ananya: ${message}`);
      if (scratch.length) parts.push('TOOL RESULTS SO FAR:\n' + scratch.join('\n'));
      parts.push('Lifebot (JSON only):');
      const raw = await generate(parts.join('\n\n'));
      const obj = extractJson(raw);
      if (!obj) return { reply: String(raw || '').trim() || 'Sorry, I had nothing to say.', actions: ctx.actions };
      if ('reply' in obj) return { reply: String(obj.reply).trim(), actions: ctx.actions };
      const name = String(obj.tool || '');
      if (!name) return { reply: String(raw).trim(), actions: ctx.actions };
      const t = tools[name];
      let result;
      if (!t) result = `Error: unknown tool '${name}'. Available: ${Object.keys(tools).join(', ')}.`;
      else if (obj.args !== undefined && (typeof obj.args !== 'object' || obj.args === null || Array.isArray(obj.args))) result = "Error: 'args' must be an object.";
      else {
        try { result = await t.fn(obj.args || {}); } catch (e) { result = `Error: ${name} failed (${e.message || e})`; }
      }
      scratch.push(`${name} -> ${String(result).slice(0, 7000)}`);
    }
    return { reply: 'I could not finish that. Could you rephrase it?', actions: ctx.actions };
  } catch (e) {
    console.error('[lifebot-web] chat failed:', e && e.message);
    return { reply: 'I could not reach my brain just now (the AI service may be down). Your tasks and reminders still work. Try again in a minute.', actions: ctx.actions };
  }
}

module.exports = { respond, extractJson, PERSONA };
