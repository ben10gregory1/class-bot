# CofC Open-Seat Watcher

Polls College of Charleston's **public** Banner "Browse Classes" API and alerts you
the instant any watched section opens up. No MyPortal login, no Duo.

Currently configured for: **MATH 104, Fall 2026 (term 202710)**, all sections.

## Setup (one time)

1. **Pick your alert method.** Default is **ntfy** (free phone push, no signup):
   - Install the **ntfy** app (App Store / Google Play).
   - Open `Watch-Seats.ps1`, set `$NtfyTopic` to your own hard-to-guess name,
     e.g. `cofc-ben-math104-9x2k`.
   - In the ntfy app, tap **+** and **Subscribe** to that exact topic name.
   - (Anyone who knows the topic name can read it, so make it unguessable.)

   Prefer email instead? Set `$UseNtfy = $false`, `$UseEmail = $true`, and fill in
   `$EmailFrom` + a Gmail **App Password** (Google Account → Security → App passwords).

## Run it

```powershell
cd C:\Users\ben10\cofc-seat-bot
powershell -ExecutionPolicy Bypass -File .\Watch-Seats.ps1
```

Leave the window open. It checks every 60s and pushes the moment a seat frees up.
Stop with **Ctrl+C**.

## Watch a different class

Edit the CONFIG block at the top of `Watch-Seats.ps1`:
- `$Subject` / `$CourseNum` — e.g. `"BIOL"` / `"111"`
- `$WatchCRNs` — leave empty for all sections, or list specific CRNs
- `$Term` — `202710` Fall 2026, `202630` Summer 2026
- `$PollSeconds` — how often to check (keep >= 30 to be polite to the server)

## Notes
- Uses only the public course-search endpoint — the same data anyone can browse at
  https://ssb.cofc.edu/StudentRegistrationSsb/ssb/term/termSelection?mode=search
- It **alerts** you; it does **not** auto-register. When you get the ping, jump into
  MyPortal and grab the seat fast.
- Alerts once per opening. If a section closes and reopens later, you'll be alerted again.

---

## Cloud version (runs 24/7 even with your PC OFF) - GitHub Actions

Files: `cloud/check_seats.sh` + `.github/workflows/watch.yml`. Checks every ~5 min
(GitHub's minimum; schedules are best-effort and can be delayed a few minutes).

**One-time setup:**
1. Create a **public** repo on github.com (public = unlimited free Actions minutes;
    a private repo would exhaust the monthly free minutes in days). Do NOT initialize it with a README.
2. In that repo: **Settings > Secrets and variables > Actions > New repository secret**
   - Name: `NTFY_TOPIC`   Value: `cofc-ben-math104-9x2`
3. Push this folder:
   ```powershell
   cd C:\Users\ben10\cofc-seat-bot
   git remote add origin https://github.com/<YOUR-USERNAME>/cofc-seat-bot.git
   git push -u origin main
   ```
   (First push opens a browser to log into GitHub.)
4. Open the repo's **Actions** tab, enable workflows, and click **Run workflow** to test now.

**Turn the cloud watcher off:** in the repo, Actions tab > "CofC Seat Watcher" > "..." > **Disable workflow** (or just delete the repo).
Note: GitHub auto-pauses scheduled workflows after 60 days of repo inactivity.

## Turn the LOCAL watcher off

```powershell
Disable-ScheduledTask  -TaskName "CofC Seat Watcher"   # pause (re-enable with Enable-ScheduledTask)
Unregister-ScheduledTask -TaskName "CofC Seat Watcher" -Confirm:$false   # remove entirely
```
It uses no AI/tokens - it's just web requests - so it's free to leave running.
