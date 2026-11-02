# RESTORE — class-bot state snapshot

Watch term: **202720** (Spring 2027, since 2026-11-02). Current registration below is still Fall (202710).
Regenerate anytime: `python rank.py` (ranking), `discover.py --term 202720` (fresh section pull; `--term` still defaults to 202710).

## Registered — current (15 cr, updated 2026-10-04)

| CRN | Course | Cr | Mode | Part of term |
|---|---|---|---|---|
| 11221 | FINC 120-01 | 3 | In person MW 1900-2145 | Express II (10/05 – ~12/05, end date TBC) |
| 11088 | COMM 215-04 | 3 | Online async | Full term |
| 10323 | RELS 105-01 | 3 | Online async (Banner lists MWF 0900-0950; no live meetings per user) | Full term |
| 13931 | SOCY 105-01 | 3 | Online async | Express II |
| 12871 | PRST 336-01 | 3 | Online sync Thu 1800-2045 | Express II |

PALM 118 dropped for PRST 336 (commit d48e221). GEOL 240 (14114) dropped 2026-10-04.
Live Banner shows GEOL 240 = 2 cr (not 1 as in old express2-all.md).

All three prior open decisions resolved: RELS 105 replaced WGST 200, COMM 215 override went
through, SOCY 105 landed over the COMM 215 alt. Now 15 cr (2026-10-04) — no credit gap
remains. Only RELS 105 + SOCY 105 hit a named gen-ed requirement; the other 10 cr is pure
122-count filler, zero major progress this term.

## Watch list (config.json) — Spring 2027 plan (retargeted 2026-11-02)

Ben's picked Spring sections, 15 cr, not confirmed registered. Alerts fire on absent/closed ->
open only: no alert when a section fills, and none for a section that stays open.

| CRN | Course | Time | Prof |
|---|---|---|---|
| 20002 | ACCT 203-05 | TR 1215-1330 | Saboe |
| 20995 | MATH 104-12 | MWF 1100-1150 | Jin |
| 20047 | BLAW 205-03 | MWF 1000-1050 | Ansari-Andrews |
| 20542 | MGMT 301-04 | MW 1730-1845 | Yarborough |
| 20282 | LATN 102-01 | MWF 1300-1350 | McCune |

`priority.chain` (rank.py bonus 6.0, unchanged) = ACCT 203, ACCT 204, ECON 200, ECON 201,
MATH 104, MATH 250. Live Banner 2026-11-02: ECON 200 needs 3 cr of completed college math, so
Ben can't take ECON 200/201 in Spring. FINC 303 lists ACCT 203, ECON 200, MATH 104/107/250 +
junior standing, not ACCT 204 or ECON 201 as the notes claim. ntfy topic: Windows user env var +
`NTFY_TOPIC` GH secret only, never in repo.

Watcher health (2026-10-06): last 8 scheduled runs all succeeded; real gaps ~4–7 h between runs
(GitHub throttling, see CLAUDE.md "Cron cadence"). `gh workflow run watch.yml` for an on-demand check.

## Pending decisions

- **Now:** register the Spring sections above manually in Banner. Alert-only — the bot never registers.
- MATH 116 deferred out of the Spring plan to keep 15 cr; still owed for major calc + gen-ed math.
- Superseded and closed (kept in git history, pre-d48e221): the 2026-08-21 MATH 250 add idea and
  the virtual-through-September in-person conflicts (PALM 118 / GEOL 240 / FINC 120). PALM 118 and
  GEOL 240 were dropped; FINC 120 is attended in person now that Ben is back in Charleston.

## Degree audit snapshot (Class Path.md, 2026-08-04)

BS Finance, Catalog 2025-2026, Sophomore, 3.493 GPA, 46/122 cr (earned+in-progress), 76
remaining. Major GPA 0.000 — zero business credits taken yet. **Spring 2027 is the real
unlock**: the audit-era plan listed ACCT 203, ECON 200, ECON 201, MATH 104/116, BLAW 205 as having
no prereqs. Wrong for ECON (see watch list note); 45 cr / 77 remaining once PALM/GEOL drops are counted.

## Ranked candidates (discovery/ranked_candidates.md)

Regenerated locally 2026-10-04 (348 sections scored, 251 ranked) against the current 15 cr
`registered{}`; last committed version is the 2026-07-27 run. Top of list is gate-chain sections
(MATH 104/250, ACCT 204) via the 6.0 chain bonus — all full or non-Express II, so not actionable
for Fall.

## Source discovery run (discovery/discover_report_202710.txt)

2970 total sections. ASYNC 237 / SYNC_ONLINE 66 / INPERSON 2667. Express II (short part-of-term,
10/07–12/08) = 74 sections, 44 ASYNC. 5 sections on unknown partOfTerm code 9 — flagged, not
guessed.
