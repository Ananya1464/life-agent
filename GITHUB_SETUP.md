# GitHub Deployment — Step-by-Step Guide

Your life-agent runs completely free on GitHub Actions. This guide walks you through every step.

## What You'll Set Up

| What | Time | Cost |
|---|---|---|
| Private GitHub repo | 5 min | Free |
| GitHub Secrets (API keys) | 5 min | Free |
| Notion "Reminders" database (phone push) | 5 min | Free |
| Notion "Tomorrow's Goals" property | 2 min | Free |
| **Total** | **~17 min** | **$0/month** |

---

## Step 1: Create a Private GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Fill in:
   - **Repository name**: `life-agent` (or anything you like)
   - **Description**: `Personal daily life automation agent`
   - ⚠️ **Visibility**: Select **Private** (this keeps all your data private!)
   - **Do NOT** initialize with README (you already have one)
3. Click **Create repository**

## Step 2: Push Your Code to GitHub

Open a terminal in your `D:\life-agent` folder and run these commands:

```powershell
cd D:\life-agent

# Initialize git (skip if already a git repo)
git init

# Make sure .env and .venv are ignored (they contain secrets)
# Your .gitignore should already have these, but double check:
cat .gitignore

# Add all files
git add .

# Commit
git commit -m "Initial commit: life-agent with daily automation"

# Connect to your private repo (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/life-agent.git

# Push
git branch -M main
git push -u origin main
```

> ⚠️ **IMPORTANT**: Make sure `.env` is in your `.gitignore` file! It contains your real API keys. The `.env` file should NEVER be pushed to GitHub. Check with:
> ```powershell
> git status
> ```
> If `.env` shows up as a tracked file, remove it:
> ```powershell
> git rm --cached .env
> echo ".env" >> .gitignore
> git add .gitignore
> git commit -m "Remove .env from tracking"
> ```

## Step 3: Add Secrets to GitHub

Your API keys need to be stored as GitHub Secrets (encrypted, never visible in logs).

1. Go to your repo on GitHub
2. Click **Settings** (tab at the top)
3. In the left sidebar: **Secrets and variables** → **Actions**
4. Click **New repository secret** for each:

| Secret Name | Where to get the value | Required? |
|---|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) — click "Create API key" | ✅ Yes |
| `NOTION_TOKEN` | [Notion integrations](https://www.notion.so/my-integrations) — your integration's "Internal Integration Secret" | ✅ Yes |
| `GMAIL_ADDRESS` | Your Gmail address: `your-email@gmail.com` | Optional |
| `GMAIL_APP_PASSWORD` | [Google App Passwords](https://myaccount.google.com/apppasswords) — create one for "Mail" | Optional |
| `ICAL_URL` | Google Calendar → Settings → your calendar → "Secret address in iCal format" | Optional |
| `REMINDERS_DB_ID` | See Step 4 below | Optional |

> 💡 **Tip**: You can skip GMAIL_ADDRESS, GMAIL_APP_PASSWORD, and ICAL_URL for now. The agent will just skip email delivery and calendar reading — Notion is the primary delivery anyway.

## Step 4: Set Up Notion for Reminders (Phone Push Notifications)

This step enables the agent to send you push notifications on your phone via the Notion app.

### 4a. Create a "Reminders" Database in Notion

1. Open Notion (web or app)
2. Create a new **Full-page database** (type `/database` and select "Database - Full page")
3. Name it: `📱 Agent Reminders`
4. Set up these properties:
   - **Name** (Title) — already there by default
   - **When** (Date) — click "+ New property" → select "Date"
5. That's it! Just two columns.

### 4b. Get the Database ID

1. Open the Reminders database page in your browser
2. The URL will look like: `https://www.notion.so/YOUR_NAME/1234567890abcdef1234567890abcdef?v=...`
3. The **database ID** is the 32-character hex string after your workspace name and before the `?`
4. Copy it and add it as a GitHub Secret named `REMINDERS_DB_ID`

### 4c. Connect Your Integration to the Database

1. Open the Reminders database page
2. Click the **⋯** (three dots) menu → **Connections** → **Connect to** → select your integration
3. This grants the agent permission to create reminder entries

### 4d. Enable Notion Notifications on Your Phone

1. Install the **Notion app** on your phone (if not already)
2. Go to phone **Settings** → **Notifications** → **Notion** → Enable all notifications
3. In the Notion app: **Settings** → **Notifications** → Enable "Push notifications"
4. The agent creates database entries with reminder timestamps — Notion pushes them to your phone!

## Step 5: Add "Tomorrow's Goals" Property to Daily Log

This lets you set goals that the agent turns into time-blocked plans.

1. Open your **🌱 Daily Life Tracker** database in Notion
2. Click **+** to add a new property
3. Name: `Tomorrow's Goals`
4. Type: **Text** (rich text)
5. Now when you fill this in on any day's entry, the 9:45 PM `goal_planner` task reads it and builds you a full day plan!

**How to use it**: Each evening, open today's Daily Log entry and type your goals in the "Tomorrow's Goals" field. Examples:
- `Finish ML course chapter 5, send 3 professor emails, gym at 6 PM`
- `Complete NLP assignment, apply to 5 jobs, read interpretability paper`
- `Rest day - only 2 job applications and review notes`

## Step 6: Verify Everything Works

### Test manually from GitHub

1. Go to your repo → **Actions** tab
2. Click **Life Agent** in the left sidebar
3. Click **Run workflow** (dropdown button)
4. Select a task (start with `evening_checkin` — it's the lightest)
5. Click **Run workflow**
6. Watch the run — it should complete in 1-3 minutes
7. Check your Notion for the output!

### Test all tasks

Run each task manually to verify:
- `meal_plan` → check email + Notion Weight Loss page
- `ai_edge` → check Notion Daily Log "Your AI Edge" section
- `evening_checkin` → check email
- `goal_planner` → fill "Tomorrow's Goals" first, then run → check Notion
- `tomorrow_planner` → check Notion Daily Log
- `set_reminders` → check Notion Reminders database
- `weekly_review` → check Notion + email

## Step 7: It's Running! 🎉

Once you've verified, the cron schedule kicks in automatically:

| Time (IST) | Task | What Happens |
|---|---|---|
| 7:00 AM | `meal_plan` | Fat-loss meal plan → email + Notion |
| 8:00 AM | `ai_edge` | AI briefing with live research → Notion + email |
| 9:30 PM | `evening_checkin` | Habit accountability nudge → email |
| 9:45 PM | `goal_planner` | Your goals → time-blocked plan → Notion + email |
| 10:00 PM | `tomorrow_planner` | Adaptive tomorrow plan → Notion + email |
| 10:15 PM | `set_reminders` | Plan → Notion reminders → phone push |
| Sun 8:00 PM | `weekly_review` | 7-day performance review → Notion + email |

> 💡 **Note**: GitHub Actions cron can be delayed by up to 10-15 minutes during peak times. Your tasks will still run, just maybe at 7:12 AM instead of exactly 7:00 AM.

---

## Troubleshooting

### "NOTION_TOKEN" error
- Make sure you added the secret in GitHub Settings → Secrets → Actions
- Secret names are CASE SENSITIVE

### Task runs but nothing appears in Notion
- Open the failing run in Actions → read the logs
- Most likely: your Notion integration isn't connected to the page. Go to the Notion page → ⋯ → Connections → Connect your integration

### Reminders not pushing to phone
- Make sure Notion app notifications are enabled on your phone
- Check that REMINDERS_DB_ID is set correctly in GitHub Secrets
- The integration must be connected to the Reminders database

### Want to change task times?
- Edit the cron lines in `.github/workflows/agent.yml`
- Cron is in UTC. IST = UTC + 5:30
- Useful converter: [crontab.guru](https://crontab.guru/)

### Want to switch back to Claude?
- Add `ANTHROPIC_API_KEY` as a GitHub Secret
- Change `LLM_PROVIDER` from `"gemini"` to `"claude"` in the workflow file
- Cost: ~$3-5/month for Claude API

---

## Your Daily Workflow

```
Morning:
  📱 Phone buzzes with meal plan email (7 AM)
  📱 Phone buzzes with AI Edge briefing (8 AM)
  🔔 Notion reminders pop up for each time-blocked task

During the day:
  ✅ Log what you did in Notion → "What I achieved today" section
  ✅ Fill "Achievements" property

Evening:
  📱 Evening check-in email (9:30 PM)
  ✍️ Type tomorrow's goals in "Tomorrow's Goals" field
  📱 Goal planner turns them into a full day plan (9:45 PM)
  📱 Adaptive tomorrow plan (10 PM)
  🔔 Reminders set for tomorrow's plan items (10:15 PM)

Sunday:
  📊 Weekly review with stats and patterns (8 PM)
```

Everything is automatic. The only thing you do is:
1. **Log achievements** in Notion during the day
2. **Set tomorrow's goals** before bed
3. **Respond to nudges** (check emails, follow the plan)
