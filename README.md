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
