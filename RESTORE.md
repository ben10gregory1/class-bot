# RESTORE — class-bot state snapshot

Term: **202710**. Regenerate anytime: `python rank.py` (ranking), `discover.py --term 202710` (fresh section pull).

## Watch list (config.json)

ntfy topic: `unused-see-secret`

| Label | CRNs |
|---|---|
| fall async targets | 13284, 12337 |

## Tracked seat status (state.json)

| CRN | Open | Seats |
|---|---|---|
| 13284 | false | 0 |
| 12337 | false | 0 |

Both watched CRNs currently closed, 0 seats. Watcher will ntfy-alert on change.

## Current swap recommendations (discovery/swap_suggestions.md)

2 of 5 registered CRNs have a higher-scored open alternative:

| Current CRN | Current Course | Score | → | Suggested CRN | Suggested Course | Score | Δ | Req | Seats |
|---|---|---|---|---|---|---|---|---|---|
| 13463 | WGST 200-12 | 6.98 | → | 10323 | RELS 105-01 | 9.62 | +2.64 | Humanities | 12 |
| 11088 | COMM 215-04 (pending) | 10.08 | → | 13931 | SOCY 105-01 | 10.46 | +0.38 | Social Science | 17 |

No swap found (not in this term's data): 11221 FINC 120-01, 14114 GEOL 240-01, 11541 PALM 118-02.

## Ranked candidates (discovery/ranked_candidates.md)

303 sections scored (217 ranked w/ RMP data, 4 avoid-flagged, 82 unranked no RMP).
Composite formula: `retake%/100*3.0 + rating/5*2.5 + (5-difficulty)/5*1.5 + req(+3) + seats(+1 >10 / +2 >25) + modality(+1 ASYNC or Express II in-person)`. Uncapped, max ~13.

Top 5:
| CRN | Course | Modality | Seats | Score |
|---|---|---|---|---|
| 13733 | THTR 176-01 Theatre Appreciation | ASYNC (Express II) | 0 | 10.58 |
| 13931 | SOCY 105-01 Sociology of Sport | ASYNC (Express II) | 17 | 10.46 |
| 13734 | THTR 176-09 Theatre Appreciation | ASYNC (Full Term) | 0 | 10.38 |
| 13659 | ARTH 103-01 Asian Art and Architecture | ASYNC (Full Term) | 0 | 10.34 |
| 13353 | ARTM 225-03 The Art of Creativity | ASYNC (Full Term) | -1 | 10.3 |

Full table: `discovery/ranked_candidates.md`. Related outputs in `discovery/`: `shortlist.md` (min-workload, no fixed meetings, 8 candidates, exam-proctoring unconfirmed), `open-now.md`, `inperson-swap-check.md`, `req-matched-sections.md`, raw data in `raw_sections.json` / `candidates.csv` / `enriched_candidates.csv` / `vocab.json`.

## Source discovery run (discovery/discover_report_202710.txt)

2970 total sections. ASYNC 237 / SYNC_ONLINE 66 / INPERSON 2667. Express II (short part-of-term, 10/07–12/08) = 74 sections, 44 ASYNC. 5 sections on unknown partOfTerm code 9 — flagged, not guessed.
