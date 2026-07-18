# Life Agent 🌱

Your personal scheduled-task agent — a subscription-free replacement for Claude's scheduled tasks. It runs four daily jobs on GitHub Actions (free), thinks with real Claude (API, pay-per-use) or Gemini (free tier), and delivers to your Notion Daily Log + email.

## The four tasks

| Time (IST) | Task | What it does | Delivery |
|---|---|---|---|
| 7:00 AM | `meal_plan` | Vegetarian fat-loss meal plan (~1,600 kcal, 110–120 g protein), rajma/soya lunch rotation, macro math verified | Email + appended to Weight Loss Notion page |
| 8:00 AM | `ai_edge` | Deep-researched "Your AI Edge" briefing (opportunities, papers, leverage idea, market note) | Notion Daily Log "🌅 Your AI Edge" section + email |
| 9:30 PM | `evening_checkin` | Warm weight-loss habit accountability nudge | Email |
| 10:00 PM | `tomorrow_planner` | Reads what you logged today in Notion, writes an adaptive "Tomorrow's plan" into tomorrow's entry | Notion Daily Log "🌙 Tomorrow's Plan" section + email |

## How it works

```
GitHub Actions cron ──▶ main.py <task> ──▶ prompts/<task>.md (your editable prompt)
                                   │
                                   ├─▶ llm.py       (brain: Claude API or Gemini, extended thinking)
                                   ├─▶ research.py  (deep research: plan queries → search → evidence dossier)
                                   ├─▶ quality.py   (self-verification: link checks + critique→revise)
                                   ├─▶ notion_api.py (read/write Daily Log + Weight Loss page)
                                   ├─▶ calendar_feed.py (read-only Google Calendar via secret iCal URL)
                                   └─▶ emailer.py   (Gmail SMTP)
```

Notion is the source of truth. Email and calendar are optional — if their secrets are missing the agent skips them silently, exactly like your old setup.

## How this replicates the way Claude runs each task

Claude's scheduled runs aren't one big prompt — they're a pipeline: **read context → think → research → generate → verify → deliver**. This agent hard-wires the same pipeline:

| Claude behavior | Replicated by |
|---|---|
| Reads today's Notion entry before planning tomorrow | `tomorrow_planner` queries the Daily Log first and injects Achievements + "What I achieved today" into the prompt |
| Extended thinking before answering | Claude API extended thinking / Gemini 2.5 thinking budget (`llm.py`, tune via `THINKING_BUDGET`) |
| Multi-step deep research (not one shallow search) | `research.py`: plan 6 targeted queries → search each on the live web → collect an evidence dossier with URLs/dates → synthesize the briefing only from that evidence |
| Doesn't repeat itself day to day | `ai_edge` reads the last 3 days' briefings from Notion and excludes already-covered items |
| "Verify links resolve; never invent URLs" | `quality.find_dead_links()` HTTP-checks every URL; dead ones trigger a revision |
| Double-checks its own output | `quality.critique_and_revise()` — a second reviewer call grades each draft against the task's own checklist, then a revision call fixes failures |
| Checks the meal-plan macros land at ~1,600 kcal / 110–120 g | Meal-plan checklist forces the reviewer to recompute the arithmetic |
| Update-if-exists / create-if-missing Notion entries, exact 3-section layout | `notion_api.replace_section()` / `create_daily_entry()` with your exact template |
| Skips Gmail silently if unavailable | `emailer.py` never crashes a run |

### The brain (llm.py) — two modes

- **Claude mode** (set `ANTHROPIC_API_KEY`): the agent literally runs on Claude via the API — extended thinking + Anthropic web search. This is real Claude reasoning, no subscription, pay-per-use (~$1–5/month here; deep research is the main cost). Set `CLAUDE_MODEL` to pick the model (default `claude-sonnet-5`; choose a higher tier for maximum thinking strength).
- **Gemini mode** (free fallback): Gemini 2.5 Pro with a thinking budget + Search grounding runs the identical pipeline at zero cost.

Honest note: with Claude mode the brain IS Claude, so outputs are directly comparable to your current scheduled tasks. With the free Gemini mode the pipeline is identical but the model differs — very close, not literally identical.

## Editing / adding tasks

- **Change a prompt**: edit the matching file in `prompts/` — no code changes needed.
- **Change a time**: edit the cron lines in `.github/workflows/agent.yml` (they're UTC; IST − 5:30).
- **Add a new task**: copy any file in `tasks/`, add a prompt in `prompts/`, add the task name to `TASKS` in `main.py`, and add a cron line + case entry in the workflow.

## Replying to the agent

Email here is one-way. The feedback loop is Notion: log your day in the "✍️ What I achieved today" section (and the Achievements property), and the 10 PM planner reads it to adapt tomorrow. Tick the habit tracker on the Weight Loss page after the evening check-in.

See **SETUP.md** for the one-time setup (≈20 minutes).
