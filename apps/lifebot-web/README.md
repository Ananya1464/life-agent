# Lifebot on your phone

An installable web app with the same Chat, Typewriter tasks, avocado Focus timer, Reminders and Briefings as the desktop
Lifebot. It works when the laptop is off, because it reads and writes your Obsidian vault **in OneDrive** directly.

## How it fits with the desktop app

| | Where it lives | Phone | Laptop |
|---|---|---|---|
| Tasks | `ANANYA-OS/Tasks.md` (vault) | read + edit | read + edit (unchanged) |
| Briefings, Dashboard, Focus Log | `ANANYA-OS/Briefings`, `ANANYA-OS/Dashboard` | read | writes them (unchanged) |
| Phone reminders | `ANANYA-OS/Lifebot/phone-reminders.json` | read + edit | not yet (part 2) |
| Phone focus sessions + ticked tasks | `ANANYA-OS/Lifebot/phone-events.jsonl` (same schema as `data/events.jsonl`) | writes | not merged yet (part 2) |
| Laptop reminders, chat history, `events.jsonl` | on the laptop only | not visible | unchanged |

- Every task change re-reads `Tasks.md` from OneDrive first and saves with OneDrive's version check, so a change made on the
  laptop in the meantime is never overwritten.
- `09_RUNTIME` and `.obsidian` are never read. The phone can only write `Tasks.md` and its own files in `Lifebot/`.
- Push notifications go through **ntfy** (the topic your desktop Lifebot already uses). ntfy can hold a scheduled push for up
  to **3 days**, so a reminder further out is scheduled the next time you open the app within 3 days of it. A focus session
  schedules a "Focus done" push for its end time, so you hear it with the phone locked.
- Chat uses the same persona and JSON tool loop as `src/life_agent/lifebot/chat.py`, with Gemini first and NVIDIA as the
  fallback. Its tools act on the vault (tasks, phone reminders, briefings, notes, the Focus Log). Project git status is laptop-only.
  It reads `00_SYSTEM/ME.md` as your profile.

## One-time setup (about 20 minutes)

### 1. Register the app with Microsoft (lets it open your OneDrive vault)
Microsoft no longer lets a personal account register apps without a directory (tenant). If **New registration** says you
need a directory, create a free Azure account first at <https://azure.microsoft.com/free> with the same Microsoft account.
It usually asks for a card to verify you; registering an app in Microsoft Entra ID is free. Use your real details.

1. Go to <https://entra.microsoft.com> and sign in with the Microsoft account that owns your OneDrive.
2. **Applications → App registrations → New registration**.
   - Name: `Lifebot`
   - Supported account types: **Personal Microsoft accounts only**
   - Redirect URI: platform **Web**, value `https://YOUR-APP.vercel.app/api/auth/callback` (fill in after step 2; you can edit it later under **Authentication**)
3. Copy the **Application (client) ID** → this is `MS_CLIENT_ID`.
4. **Certificates & secrets → New client secret** (24 months) → copy the **Value** → `MS_CLIENT_SECRET`. Put a reminder in your
   calendar for when it expires.
5. **API permissions**: make sure Microsoft Graph has `User.Read`, `Files.ReadWrite` and `offline_access` (delegated). Add the
   last two with **Add a permission → Microsoft Graph → Delegated permissions**.

### 2. Deploy on Vercel
1. Push this branch to GitHub.
2. <https://vercel.com> → **Add New → Project** → import the `life-agent` repo.
3. **Root Directory**: `apps/lifebot-web`. Framework preset: **Other**. No build command.
4. **Environment Variables**: add everything from `vercel-env.example` (APP_URL is the `https://….vercel.app` address Vercel shows).
   `SESSION_SECRET`: any long random text (40+ characters). `ALLOWED_EMAIL`: your Microsoft account email.
5. Deploy. Then put the real redirect URI in the Microsoft app registration (step 1.2) if you had not yet.

### 3. On your phone
1. Open the Vercel address in **Safari** (iPhone) or **Chrome** (Android) and sign in with Microsoft.
2. Add it to the home screen (Share → **Add to Home Screen**).
3. Reminders tab → **Send test** to check the ntfy push arrives.

## Run it locally (optional)
Uses a copy of a vault folder and skips sign-in. Never point it at your real vault.

    cd apps/lifebot-web
    VAULT_LOCAL_DIR=test/fixture-vault DEV_NO_AUTH=1 LIFEBOT_INSECURE_COOKIES=1 node dev-server.js
    node --test test/server.test.js

## Part 2 (next)
- Desktop Lifebot imports `Lifebot/phone-events.jsonl` into `data/events.jsonl` (dedupe on `dedupe_key`) so phone focus
  sessions count in the dashboard, streaks and levels.
- Desktop Lifebot shows phone reminders, and phone shows laptop reminders, in one list.
