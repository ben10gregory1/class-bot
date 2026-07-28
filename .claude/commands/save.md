---
description: Save current class-bot state to RESTORE.md and push
---
1. Read `config.json` (watch list), `state.json` (seat status), `rank.py`
   (`REGISTERED_CRNS` — registered courses), and `discovery/swap_suggestions.md`
   (current swap recommendations, if present).
2. Ask the user for anything not derivable from those files: pending decisions
   (drops/adds under consideration, confirmations still needed, credits still needed).
3. Rewrite `RESTORE.md` to reflect current state: watch list + seat status,
   registered courses, pending decisions, top swap suggestions.
4. Check `README.md` and `CLAUDE.md` for drift against the actual repo (new/removed
   scripts, changed workflow, stale instructions) — flag it if found, don't silently fix.
5. `git add -A`, commit (describe what changed in state, not "update RESTORE.md"),
   push. Confirm with the user before pushing if anything looked unusual in `git status`.
