# class-bot

CofC (College of Charleston) course registration assistant, term **202710** (Fall 2026).
Two jobs: (1) watch specific CRNs for open seats and push an alert, (2) rank open
async/Express-II sections against remaining degree reqs to suggest better swaps.

**Hard rule: alert only, never auto-register.** Nothing in this repo submits registration
forms. `watch.py` pushes an ntfy notification; the human still has to go grab the seat
in MyPortal/Banner.

## Routing table

| Concern | Files |
|---|---|
| Seat watcher (what runs every 5 min) | `watch.py`, `config.json` (watch targets + ntfy topic), `state.json` (last-seen open/closed per CRN, committed by the workflow) |
| Discovery/ranking pipeline (run manually, not scheduled) | `discover.py` → `enrich.py` → `rank.py`, outputs in `discovery/` (see `discovery/CONTEXT.md`) |
| Scheduling | `.github/workflows/watch.yml` — GitHub Actions cron, `*/5 * * * *` |
| Session restore | `RESTORE.md` (current state snapshot), `.claude/commands/restore.md`, `.claude/commands/save.md` |

## Known-wrong

`README.md` used to describe an old PowerShell system (`Watch-Seats.ps1`, `cloud/check_seats.sh`).
The live system is Python + GitHub Actions (`watch.py` + `watch.yml`). Those two legacy files
are still in the repo but unused — don't extend them, extend `watch.py`.

## Config / secrets

- `config.json`: `term`, `ntfyTopic` (placeholder — real topic set via `NTFY_TOPIC` repo secret
  in Actions, since the repo is public), `watch[]` (list of targets: CRNs, or subject+courseNumber+filters).
- `state.json`: per-CRN `{open, seats}`, auto-committed by the workflow on change
  (`state: update seat tracking [skip ci]`).
- Registered CRNs for ranking/swap comparison are hardcoded in `rank.py` (`REGISTERED_CRNS`) —
  no live registration API, update that dict by hand when the schedule changes.

## Workflow for a session

Run `/restore` to load `RESTORE.md` and get oriented. When wrapping up state changes
(new registration, new swap decision, watch list edit), run `/save` to refresh `RESTORE.md`
and push.
