# cron-worker

Cloudflare Worker that POSTs `workflow_dispatch` for `watch.yml` every 10 minutes, because
GitHub's own `schedule:` is throttled to gaps of hours. Each dispatch is one `watch.py` pass.
No alerts, Banner calls, or state live here. It only pulls the trigger. Fits the Workers Free
plan.

## Setup

**1. Create the GitHub token.** Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token:

- Resource owner: `ben10gregory1`
- Repository access: **Only select repositories** → `class-bot`
- Repository permissions: **Actions: Read and write**. Nothing else (Metadata: Read is added
  automatically).
- Expiration: **No expiration**. Allowed for personal repos, and the narrow scope limits a leak
  to triggering this one workflow. If the option isn't offered, pick 366 days and add a calendar
  reminder. An expired token fails every tick, and only the slow GitHub schedule keeps running.

Copy it once. Don't commit it or paste it into chat. The repo is public.

**2. Deploy.** Needs a free Cloudflare account. From this folder, in PowerShell:

```powershell
cd cron-worker
npx wrangler@4 login
npx wrangler@4 deploy
npx wrangler@4 secret put GITHUB_TOKEN
```

`secret put` prompts for the token, so it never lands in shell history. Ticks before the secret
is set fail harmlessly with `GITHUB_TOKEN secret unset`.

## Confirm it's firing

Cron changes can take up to 15 minutes to reach Cloudflare's network.

```powershell
npx wrangler@4 tail
```

Look for `dispatch ok: HTTP 200` at the next 10-minute mark. Then confirm GitHub saw it:

```powershell
gh run list --workflow watch.yml --event workflow_dispatch --limit 5
```

You should see runs about 10 minutes apart. Past logs are in the Cloudflare dashboard under
Workers → `class-bot-cron` → Observability (kept 3 days).

**Then turn on the watchdog:** set `"dispatchWatchdog": true` in `config.json` and push. Each
GitHub scheduled run then pings ntfy if the newest dispatch run is over 60 minutes old.

## Reading failures

| Log | Meaning | Fix |
|---|---|---|
| `GITHUB_TOKEN secret unset` | Secret missing | `npx wrangler@4 secret put GITHUB_TOKEN` |
| `HTTP 401` | Token expired, revoked, or wrong | New token, then `secret put` again |
| `HTTP 403` | Token lacks Actions write, or workflow disabled | Check token permissions and the Actions tab |
| `HTTP 404` | Wrong repo settings, or token can't see the repo | Check `[vars]` and token repo access |
| `HTTP 422` | Bad ref, or no `workflow_dispatch` on it | Check `GITHUB_REF` and `watch.yml` |

`watchdog.py` pings you when dispatches stop, but only on GitHub's scheduled runs, so the ping
can lag by hours. A manual `gh workflow run` also counts as a dispatch and can delay it.

## Turn it off

- **Pause:** set `crons = []` in `wrangler.toml`, then `npx wrangler@4 deploy`. Deleting the
  `[triggers]` block does NOT stop it, because omitted crons stay live. The dashboard also
  works: Triggers → menu next to the cron → Delete.
- **Remove:** `npx wrangler@4 delete`, then revoke the token on GitHub.

The GitHub `schedule:` keeps running either way.

## Tests

`npm test` runs the handler against a mocked `fetch`, with no dependencies and no network. To
fire it locally, run `npx wrangler@4 dev` and open
`http://127.0.0.1:8787/cdn-cgi/local/scheduled`. Without a `.dev.vars` file it stops at the
missing token. With a real token there, it starts a real run.
