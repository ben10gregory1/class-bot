# discovery/ pipeline notes

Three-stage pipeline, run manually (not scheduled). Order matters — each stage reads
the previous stage's output.

```
discover.py --term 202710   ->  discovery/candidates.csv, discovery/raw_sections.json
enrich.py                   ->  discovery/enriched_candidates.csv
rank.py                     ->  discovery/ranked_candidates.md, discovery/swap_suggestions.md
```

**Path gotcha (unfixed):** `discover.py`'s `--out` default is `candidates.csv` (repo root),
and `raw_sections.json` is hardcoded to write to the root too — neither defaults into
`discovery/`, despite `enrich.py`/`rank.py` defaulting to read from there. Pass
`--out discovery/candidates.csv` explicitly and move `raw_sections.json` into `discovery/`
after running, or the next stage silently reads stale data instead of your fresh pull.

## discover.py

Scrapes CofC Banner (`ssb.cofc.edu`) for term 202710, all ~3033 sections. Classifies each
as ASYNC / SYNC_ONLINE / INPERSON via `classify()` (online + no scheduled meeting = ASYNC).
Default mode filters output to ASYNC + SYNC_ONLINE only — **in-person sections never enter
the ranking pipeline**, even highly-rated ones. `raw_sections.json` is the full unfiltered
dump, cached so later stages can re-derive things (e.g. `sectionAttributes` for req
matching in `rank.py`) without re-hitting Banner.

**`--chain-report` mode** (added 2026-08-04) bypasses the ASYNC/SYNC_ONLINE filter entirely:
reports every section — any modality, any seat count, including closed and in-person — for
whatever courses are listed in `config.json` `priority.chain`. Writes
`discovery/prereq-chain.md`, flags ASYNC and Express-II-in-person separately. This exists
because the normal pipeline would silently drop prereq-gate sections that are in-person or
currently closed, which is exactly the data you need to see for a gate course, not filter out.

## enrich.py

Adds RateMyProfessors data per instructor via RMP's undocumented GraphQL endpoint, with
a JSON cache (`--cache`, default `/tmp/rmp_cache.json`) so repeat runs don't re-hit RMP.
Cache is keyed by professor display name — a name collision (two "J. Smith"s) would
silently merge their ratings.

**Known issues:**
- `rmp_tags` (`teacherRatingTags`) comes back empty for most profs — this is RMP API
  behavior (tags only populate on a direct node lookup, not the search-result node),
  not a bug. Don't treat empty tags as a failed lookup.
- `rmp_flag = low_data` when `numRatings < 5` — score is still computed, just noisy.
- `rmp_flag = no_rmp` when the prof isn't found at all; `api_error` if the endpoint
  errored after retries (endpoint is undocumented and drifts).

## rank.py

Scores every row with usable RMP data (`rmp_flag == ok`):

```
composite = retake%/100 * 3.0
          + rating/5 * 2.5
          + (5 - difficulty)/5 * 1.5
          + req_bonus        (+3 if section fills a remaining degree req)
          + seats_bonus      (+1 if seats>10, +2 if seats>25)
          + modality_bonus   (+1 if ASYNC, or INPERSON in Express II / part-of-term 3)
```

Literal max ~13 (not clamped to 10 — the weighted terms alone sum to 7, bonuses add up
to 6 more). Ranking is relative, not against an absolute scale.

Req matching (`req_hit()`) uses `sectionAttributes` from `raw_sections.json` (Humanities /
Social Science tags) plus hardcoded subject rules: MATH or PHIL-with-"logic" → Math/Logic,
LATN 201+ → Foreign Lang, ACCT/ECON/FINC 100-299 → Finance core.

**Priority-chain bonus** (added 2026-08-04): `+priority.bonus` (currently 6.0, from
`config.json`) on top of the composite for any row whose subject+number matches
`priority.chain` — the FINC 303 prereq gate courses. Dominates the ~13-point-max formula
on purpose, so gate courses surface at the top of the `ranked` bucket regardless of RMP
signal. See `CLAUDE.md` "Degree chain" section for the actual prereq structure.

Rows with `retake_pct == 0` and `numRatings > 20` are bucketed `avoid` regardless of
composite score (surfaced separately, never suggested as a swap).

`suggest_swaps()` runs automatically at the end of `rank.py` — for each CRN in
`config.json` `registered{}` (no longer hardcoded — `rank.py` reads it via `load_registered()`,
fails loud with `sys.exit` if the file is missing/malformed or the dict is empty), finds the
highest-composite open (`seats > 0`) section sharing the same `req` tag, and writes
`discovery/swap_suggestions.md`. Update `config.json` `registered{}` by hand when the actual
schedule changes; there's no live registration API.

## Output files

`discovery/` is gitignored by default (`.gitignore` has `discovery/`) — most files here
are regenerated scratch output. `ranked_candidates.md`, `prereq-chain.md`, and this
`CONTEXT.md` are force-added exceptions (`git add -f`) since they're worth keeping in
history. Everything else (`candidates.csv`, `enriched_candidates.csv`, `raw_sections.json`,
`swap_suggestions.md`, `shortlist.md`, `open-now.md`, etc.) is local-only unless force-added.
