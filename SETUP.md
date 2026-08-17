# One-time setup (~20 minutes)

## 1. Get your API keys

**The brain — pick one (or set both; Claude wins if present):**

*Option A — real Claude brain (recommended for quality, pay-per-use, no subscription)*
1. Go to https://console.anthropic.com → API Keys → create one.
2. Add ~$5 credit. At 4 tasks/day this lasts weeks; roughly $1–5/month.
3. This gives the agent actual Claude reasoning with extended thinking + web search.

*Option B — Gemini (free)*
1. Go to https://aistudio.google.com/apikey and sign in with your Google account.
2. Create an API key. Free tier is plenty for the daily runs.

**Notion (required, free)**
1. Go to https://www.notion.so/my-integrations → "New integration".
2. Name it (e.g. "Life Agent"), workspace = yours, capabilities: read + insert + update content.
3. Copy the **Internal Integration Secret** (starts with `ntn_`).
4. **Grant it access to your pages** — this step is easy to miss:
   - Open "🌱 Daily Life Tracker" → ⋯ menu → Connections → add "Life Agent".
   - Open "Weight Loss Plan — 83 → 53 kg" → same thing.

**Gmail App Password (optional — for email delivery)**
1. Enable 2-Step Verification on your Google account if not already on.
2. Go to https://myaccount.google.com/apppasswords → create one named "Life Agent".
3. Copy the 16-character password. (Skip this and the agent just won't email — Notion still works.)

**Google Calendar (optional — read-only)**
1. Google Calendar → ⚙ Settings → click your calendar in the left list.
2. Scroll to "Integrate calendar" → copy the **Secret address in iCal format** URL.
3. Never share this URL publicly — it exposes your calendar. As a GitHub Secret it stays encrypted.

## 2. Create the GitHub repo

1. Create a **private** repo on https://github.com (e.g. `life-agent`).
2. Upload this whole folder (or `git init`, commit, push). Make sure the `.github/workflows/agent.yml` file keeps its path.

## 3. Add the secrets

Repo → Settings → Secrets and variables → Actions → "New repository secret":

| Secret name | Value | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Option A key | one of the two |
| `GEMINI_API_KEY` | Option B key | one of the two |
| `NOTION_TOKEN` | `ntn_...` from step 1 | ✅ |
| `GMAIL_ADDRESS` | your-email@gmail.com | for email |
| `GMAIL_APP_PASSWORD` | 16-char app password | for email |
| `ICAL_URL` | secret iCal URL | for calendar |

## 4. Test it

1. Repo → **Actions** tab → "Life Agent" → **Run workflow** → pick `evening_checkin` → Run.
2. Open the run log — you should see the generated nudge printed, and `[email] sent` if Gmail is set up.
3. Then test `tomorrow_planner` and check tomorrow's entry appears/updates in your Notion Daily Log.
4. Finally test `ai_edge` — watch the log show `[research] searching: ...` lines, link checks, and the Notion write.

## 5. Done

The cron schedule now fires daily at 7:00, 8:00, 21:30, 22:00 IST. Note: GitHub schedules can run a few minutes late at busy times — normal and harmless.

## Troubleshooting

- **Notion 404 / "object not found"** → you skipped step 1.4 (Connections) or the data source ID is wrong.
- **Workflow didn't fire** → GitHub disables schedules on repos with no activity for 60 days; push any commit or click "Enable" in the Actions tab.
- **Gemini 429** → free-tier rate limit; lower `GEMINI_MODEL` to `gemini-2.5-flash` or reduce research queries.
- **Email missing** → check the App Password and that 2-Step Verification is on.
