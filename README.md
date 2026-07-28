# class-bot — CofC open-seat watcher + swap ranker

Two tools against College of Charleston's **public** Banner "Browse Classes" API,
no MyPortal login, no Duo:

1. **Seat watcher** — polls specific CRNs every 5 minutes via GitHub Actions, pushes an
   ntfy phone alert the instant a watched section opens up. Alert-only — it never
   registers for you.
2. **Discovery/ranking pipeline** — run by hand when you want fresh recommendations.
   Pulls every async/online section for the term, scores it against your remaining
   degree requirements + RateMyProfessors data, and suggests swaps for your currently
   registered courses.

Currently configured for term **202710** (Fall 2026). See `CLAUDE.md` for the
file-by-file map and `discovery/CONTEXT.md` for pipeline internals.

## Seat watcher

**Files:** `watch.py`, `config.json`, `state.json`, `.github/workflows/watch.yml`.

`config.json` holds the watch list — each target is a CRN list, or a subject/course
filter, or both:

```json
{
  "term": "202710",
  "ntfyTopic": "unused-see-secret",
  "watch": [
    { "label": "fall async targets", "crns": ["13284", "12337"] }
  ]
}
```

The repo is **public**, so the real ntfy topic never lives in `config.json` — it's set
as the `NTFY_TOPIC` repository secret (Settings → Secrets and variables → Actions) and
overrides whatever's in the config at runtime.

`state.json` tracks the last-seen open/closed status per CRN so you only get alerted on
a **closed → open** transition, not every pass. The workflow commits it back to the repo
automatically when it changes (`state: update seat tracking [skip ci]`).

**Setup:**
1. Install the **ntfy** app (App Store / Google Play), subscribe to your topic.
2. Add the `NTFY_TOPIC` repo secret with that topic name.
3. Edit `config.json`'s `watch[]` to your target CRNs/courses, push.
4. Actions tab → enable workflows → **Run workflow** to test immediately (or wait for
   the next 5-minute tick).

**Ad-hoc check** without editing `config.json`: Actions tab → "CofC Seat Watcher" →
**Run workflow**, fill in the `subject` / `course_number` / `crns` / `async_only` inputs.

**Turn it off:** Actions tab → "CofC Seat Watcher" → **...** → **Disable workflow**.
GitHub also auto-pauses scheduled workflows after 60 days of repo inactivity.

## Discovery/ranking pipeline

**Files:** `discover.py`, `enrich.py`, `rank.py`, outputs under `discovery/`.

```bash
pip install -r requirements.txt
python discover.py --term 202710          # -> discovery/candidates.csv, raw_sections.json
python enrich.py                          # -> discovery/enriched_candidates.csv (RMP data)
python rank.py                            # -> discovery/ranked_candidates.md, swap_suggestions.md
```

Registered CRNs to compare swaps against are hardcoded in `rank.py` (`REGISTERED_CRNS`)
— update that dict by hand when your schedule changes. Full scoring formula and known
data-quality caveats are in `discovery/CONTEXT.md`.

## Local development

Run `python watch.py` for a single pass, or `python watch.py --loop 60` to poll locally
every 60s without GitHub Actions. Set `BANNER` env var if the Banner host ever changes;
set `CONFIG_URL` to load `config.json` from a raw GitHub URL instead of the local file.

## Legacy files

`Watch-Seats.ps1` and `cloud/check_seats.sh` are an earlier PowerShell/bash implementation
of the same watcher, superseded by `watch.py` + `watch.yml`. Left in the repo but unused
— don't extend them.
