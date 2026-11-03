# class-bot

CofC (College of Charleston) course registration assistant, watching term **202720** (Spring 2027) since 2026-11-02.
Two jobs: (1) watch specific CRNs for open seats and push an alert, (2) rank open
async/Express-II sections against remaining degree reqs to suggest better swaps.

**Hard rule: alert only, never auto-register.** Nothing in this repo submits registration
forms. `watch.py` pushes an ntfy notification; the human still has to go grab the seat
in MyPortal/Banner.

## Routing table

| Concern | Files |
|---|---|
| Seat watcher | `watch.py`, `config.json` (watch targets + priority chain), `state.json` (last-seen open/closed per CRN, committed by the workflow; does NOT prune CRNs dropped from `watch[]`, stale keys are ignored) |
| Discovery/ranking pipeline (run manually, not scheduled) | `discover.py` → `enrich.py` → `rank.py`, outputs in `discovery/` (see `discovery/CONTEXT.md`) |
| Prereq-chain report (run manually) | `discover.py --chain-report` → `discovery/prereq-chain.md`, ALL sections of `config.json` `priority.chain` courses regardless of seats/modality |
| Scheduling | `.github/workflows/watch.yml` — GitHub Actions cron, `*/5 * * * *`. See "Cron cadence" below — the declared interval is not what actually happens. `workflow_dispatch` (manual/ad-hoc) is a single shot. `cron-worker/` — Cloudflare Worker that dispatches every 10 min (setup in `cron-worker/README.md`). `watchdog.py` — pings ntfy from scheduled runs if dispatches stop. |
| Session restore | `RESTORE.md` (current state snapshot), `.claude/commands/restore.md`, `.claude/commands/save.md` |

## Known-wrong

The old PowerShell system (`Watch-Seats.ps1`, `cloud/check_seats.sh`, the `~/cofc-seat-bot`
folder and its "CofC Seat Watcher" Windows scheduled task) was deleted 2026-10-04. Old ntfy
topic strings remain in git history (public repo); that topic is unused.

## Cron cadence (observed 2026-08-02 → 08-04, unresolved)

Declared `*/5 * * * *`. Actual gaps between scheduled runs: 50min–3h17m, consistently over
2+ days — not occasional congestion, systemic. GitHub deprioritizes scheduled workflows on
free-tier public repos; not fixable from `watch.yml` config. The 5-pass/`sleep 50` loop inside
a run only tightens sampling *within* that run — between runs the real gap is unpredictable,
up to several hours. **The old "~50s real polling" claim in this file was wrong and is
retired** — that described the intra-run loop, not the interval between scheduled runs, which
is what actually determines how long a seat can sit open before the bot notices. Workaround
when you need a check now: `gh workflow run watch.yml` (manual dispatch, single shot).

**Update 2026-10-04 (measured via `gh api`):** scheduled gaps Sep 11→Oct 4 were 95–410 min,
plus an 8-day total outage (Sep 24 → Oct 2, workflow likely auto-disabled then re-enabled —
cause unconfirmed; bot `[skip ci]` commits probably don't count as repo activity for GitHub's
60-day inactivity disable, so a human push resets the clock). `workflow_dispatch` runs start
2–11 s after creation (n=12). Empty dispatch inputs are safe: `env_target()` returns None →
normal `watch[]`, one pass. **Fix path:** external cron (cron-job.org or a Cloudflare Worker)
POSTs `workflow_dispatch` every 5 min with a fine-grained PAT (class-bot only, Actions
read/write). GitHub schedule stays as fallback. "Leave the laptop on" does nothing by itself —
Actions doesn't run on the laptop; a laptop-side trigger dies on Modern Standby sleep.
Never run `watch.py` on the laptop alongside Actions — separate state = double alerts.

**Update 2026-11-02, fix built in `cron-worker/`, live only once Ben deploys it** (steps in
`cron-worker/README.md`; check `gh run list --event workflow_dispatch` for real status).
Scheduled gaps over the last 40 runs: 130–621 min, median 300, so still throttled.

- Trigger: Cloudflare Worker cron `*/10 * * * *` POSTs `workflow_dispatch` with no inputs, one
  pass per tick. Token is a Wrangler secret (fine-grained, class-bot only, Actions read/write,
  no expiration). 10 min rather than 5 to go easy on Banner; change one line in
  `cron-worker/wrangler.toml` for a registration crunch.
- Dispatch runs took a median 39 s, max 71 s (n=15, full-scan era), so they don't overlap.
- A scheduled run takes ~5.5 min and blocks ticks while it runs. `concurrency: seat-watch`
  holds one pending run, and a newer tick cancels it, so an occasional "cancelled" run is
  expected and harmless. Only one run touches `state.json` at a time.
- GitHub `schedule:` stays as the fallback: it's free and it's the only thing polling if the
  Worker or token dies. `watchdog.py` runs on scheduled runs and pings ntfy if the newest
  dispatch is over 60 min old, so `NTFY_TOPIC` stays out of Cloudflare. Off until
  `config.json` sets `dispatchWatchdog: true`, which is the last step of the Worker setup.
- Usage: 144 dispatches/day, free on a public repo. On Workers Free that's under 0.3% of 100k
  requests/day and 1 of 5 cron triggers.
- Banner load: `fetch_watched()` queries only the courses in `watch[]`, so targets need
  `subject` + `courseNumber`. A target without a subject (ad-hoc CRNs) forces a full scan, and
  a watched CRN missing from course results logs a warning and falls back to a full scan.
  Point-sampling still applies, the miss window just drops to about 10 min.

**Stale-checkout dedupe (fixed 2026-10-04):** `actions/checkout` defaulted to the trigger-time
SHA, so a run queued behind another loaded old `state.json` and re-alerted. Now checks out
`ref: github.ref_name` (branch tip) and pushes with `git pull --rebase -X theirs` + 3 retries.

**Failed-alert retry:** a CRN is only recorded `open: true` after ntfy returns 2xx. On a network
error, timeout or non-2xx, `state.json` keeps `open: false` with the live seat count, so the next
poll (same run or a later one, since the file is committed/checked out) sees closed → open and
retries. If the seat closes first, the retry is dropped. `open` therefore means "open and alert
delivered", not purely last-seen status. Failed sends log only the error type or HTTP status,
because `requests` error text contains the URL and so the topic. Tests: `python -m unittest
test_watch` (network mocked).


## Point sampling (inherent — do not "fix")

Separate from the cadence problem above. Detection is a state-to-state diff between polls.
A seat that opens and closes inside one interval is invisible at any poll rate — Banner has
no push API, so no polling frequency eliminates this, it only narrows the window. Combined
with the cadence problem, the real miss window right now is closer to hours than seconds.

## Verified alert semantics (2026-08-04, E2E test, runs 30885283731 + 30885376082)

- Absent → open counts as a new-open and fires an alert (not just closed → open with prior
  state). A CRN newly added to `watch[]` that's already open alerts on its first observed run.
- Correction 2026-10-04: CRNs removed from `watch[]` are NOT pruned. `watch.py` has no prune
  code; stale keys stay in `state.json` and are ignored. Harmless unless a CRN is re-added later.
- Full chain confirmed working end to end: fetch → diff → `notify()` → ntfy.sh (200) → phone.

## bash -e in GitHub Actions loops (fixed, commit b962b18)

`[ cond ] && cmd` as the last statement in a `bash -e` step (GH Actions' default shell) exits
1 when `cond` is false — that's a failing statement, not a no-op, and kills the whole step even
though everything before it succeeded. This is why several days of scheduled runs showed
"failure" despite `watch.py` working fine every pass. Use `if cond; then cmd; fi` instead.

## Paths (verified 2026-08-04)

```
Vault:     C:\Users\ben10\OneDrive\Desktop\Vault
class-bot: C:\Users\ben10\projects\class-bot
```

Not siblings — `../Vault` from `class-bot` does not resolve. `prereq.py` (mentioned in old
vault notes as a local-only script reading `../Vault/prereqs.md`) does not exist yet; if it
ever gets built, it must never be imported by `watch.py`, and it must fail open (missing
prereq data should never block or crash the watcher).

## Degree chain — FINC 303 gate (added 2026-08-04)

Live Banner prereqs, checked 2026-11-02 (the audit-era notes had these wrong):

```
FINC 303 <- ACCT 203 + ECON 200 + (MATH 104/107/250) + junior standing
ECON 200 <- 3 cr of completed college math (not concurrent)
ECON 201 <- ECON 200 + 3 cr of completed college math
ACCT 204 <- ACCT 203
FINC 313, FINC 389 <- FINC 303 + junior standing
FINC 315 <- ACCT 203 + ACCT 204 + ECON 200 + ECON 201 + FINC 303 + (MATH 104/107/250) + junior standing
FINC 400 <- FINC 303 + (DSCI 232 or MATH 250) + junior standing
FINC 418 <- FINC 303 + FINC 315 + senior standing
```

`config.json` `priority.chain` lists ACCT 203, ACCT 204, ECON 200, ECON 201, MATH 104, MATH 250;
`rank.py` adds `priority.bonus` (currently 6.0) to any candidate matching a chain course, which
dominates the existing ~13-point-max formula so chain sections surface at the top of
`ranked_candidates.md` `ranked` bucket. `watch[]` is separate: it holds Ben's Spring picks, not
the chain.

## Config / secrets

- `config.json`: `term`, `watch[]` (list of targets: CRNs, or subject+courseNumber+filters),
  `registered{}` (CRN → label, read by `rank.py` — no longer hardcoded), `priority{}`
  (`chain[]` + `bonus`, read by `rank.py` and `discover.py --chain-report`). No `ntfyTopic`
  key — removed 2026-08-04, it was a dead fallback that silently posted to `ntfy.sh/None` if
  the env var was ever unset. Real topic lives in exactly two places: a Windows user env var
  (local) and the `NTFY_TOPIC` GitHub Actions secret (runner). Never in chat, never committed,
  never anywhere else — repo is public. `watch.py` hard-fails (`sys.exit`, no echo of the
  value) if `NTFY_TOPIC` is unset — checked at the top of `main()` before any scanning, and
  again inside `notify()` as a redundant guard.
- `state.json`: per-CRN `{open, seats}`, auto-committed by the workflow on change
  (`state: update seat tracking [skip ci]`), rebased with `git pull --rebase --autostash`
  before push (`-X theirs`, 3 retries since 2026-10-04). Does not prune CRNs dropped from
  `watch[]`.
- `rank.py` fails loud (`sys.exit`) on missing/malformed `config.json` or an empty
  `registered{}` — never silently defaults to an empty schedule.

## Workflow for a session

Run `/restore` to load `RESTORE.md` and get oriented. When wrapping up state changes
(new registration, new swap decision, watch list edit), run `/save` to refresh `RESTORE.md`
and push.
