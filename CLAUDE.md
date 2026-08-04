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
| Seat watcher | `watch.py`, `config.json` (watch targets + priority chain), `state.json` (last-seen open/closed per CRN, committed by the workflow, auto-prunes CRNs dropped from `watch[]`) |
| Discovery/ranking pipeline (run manually, not scheduled) | `discover.py` → `enrich.py` → `rank.py`, outputs in `discovery/` (see `discovery/CONTEXT.md`) |
| Prereq-chain report (run manually) | `discover.py --chain-report` → `discovery/prereq-chain.md`, ALL sections of `config.json` `priority.chain` courses regardless of seats/modality |
| Scheduling | `.github/workflows/watch.yml` — GitHub Actions cron, `*/5 * * * *`. See "Cron cadence" below — the declared interval is not what actually happens. `workflow_dispatch` (manual/ad-hoc) is a single shot. |
| Session restore | `RESTORE.md` (current state snapshot), `.claude/commands/restore.md`, `.claude/commands/save.md` |

## Known-wrong

`README.md` used to describe an old PowerShell system (`Watch-Seats.ps1`, `cloud/check_seats.sh`).
The live system is Python + GitHub Actions (`watch.py` + `watch.yml`). Those two legacy files
are still in the repo but unused — don't extend them, extend `watch.py`.

## Cron cadence (observed 2026-08-02 → 08-04, unresolved)

Declared `*/5 * * * *`. Actual gaps between scheduled runs: 50min–3h17m, consistently over
2+ days — not occasional congestion, systemic. GitHub deprioritizes scheduled workflows on
free-tier public repos; not fixable from `watch.yml` config. The 5-pass/`sleep 50` loop inside
a run only tightens sampling *within* that run — between runs the real gap is unpredictable,
up to several hours. **The old "~50s real polling" claim in this file was wrong and is
retired** — that described the intra-run loop, not the interval between scheduled runs, which
is what actually determines how long a seat can sit open before the bot notices. Workaround
when you need a check now: `gh workflow run watch.yml` (manual dispatch, single shot).

## Point sampling (inherent — do not "fix")

Separate from the cadence problem above. Detection is a state-to-state diff between polls.
A seat that opens and closes inside one interval is invisible at any poll rate — Banner has
no push API, so no polling frequency eliminates this, it only narrows the window. Combined
with the cadence problem, the real miss window right now is closer to hours than seconds.

## Verified alert semantics (2026-08-04, E2E test, runs 30885283731 + 30885376082)

- Absent → open counts as a new-open and fires an alert (not just closed → open with prior
  state). A CRN newly added to `watch[]` that's already open alerts on its first observed run.
- A CRN removed from `watch[]` is auto-pruned from `state.json` on the next run — no manual
  cleanup needed, no stale-key leak.
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

FINC 303 gates most upper-level FINC and requires: ACCT 203 + ACCT 204 + ECON 200 + ECON 201
+ (MATH 104 or MATH 250) + junior standing. FINC 315 requires FINC 303. `config.json`
`priority.chain` lists all 6 courses (both MATH options included since either satisfies the
requirement); `rank.py` adds `priority.bonus` (currently 6.0) to any candidate matching a
chain course, which dominates the existing ~13-point-max formula so chain sections surface at
the top of `ranked_candidates.md` `ranked` bucket. `watch[]` covers all 6 chain courses'
sections as of 2026-08-04 (previously only 2 of 6 — ACCT 204 / ECON 200).

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
  before push so concurrent/overlapping runs don't fight over it. Auto-prunes CRNs no longer
  in `watch[]`.
- `rank.py` fails loud (`sys.exit`) on missing/malformed `config.json` or an empty
  `registered{}` — never silently defaults to an empty schedule.

## Workflow for a session

Run `/restore` to load `RESTORE.md` and get oriented. When wrapping up state changes
(new registration, new swap decision, watch list edit), run `/save` to refresh `RESTORE.md`
and push.
