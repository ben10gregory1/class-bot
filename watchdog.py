#!/usr/bin/env python3
# watchdog.py - pings ntfy if the Cloudflare Worker has stopped dispatching watch.yml.
# Runs on the GitHub schedule, so it still works when the Worker or its token is dead,
# and NTFY_TOPIC stays out of Cloudflare. Off until config.json sets dispatchWatchdog.
# A watchdog problem never fails the job: the seat check is what matters.

import json, os, sys
from datetime import datetime, timezone
import requests

MAX_AGE_MIN = 60


def latest_dispatch():
    r = requests.get(
        f'https://api.github.com/repos/{os.environ["GITHUB_REPOSITORY"]}'
        "/actions/workflows/watch.yml/runs",
        params={"event": "workflow_dispatch", "per_page": 1},
        headers={"Authorization": f'Bearer {os.environ["GITHUB_TOKEN"]}',
                 "Accept": "application/vnd.github+json"},
        timeout=20)
    r.raise_for_status()
    runs = r.json()["workflow_runs"]
    if not runs:
        return None
    return datetime.fromisoformat(runs[0]["created_at"].replace("Z", "+00:00"))


def check(now=None):
    """Returns the alert text, or None if dispatches are recent."""
    latest = latest_dispatch()
    if latest is None:
        return "No Worker dispatch runs found."
    age = ((now or datetime.now(timezone.utc)) - latest).total_seconds() / 60
    if age <= MAX_AGE_MIN:
        return None
    return f"Last Worker dispatch was {age / 60:.1f} h ago. Check the token and Cloudflare logs."


def main():
    try:
        if not json.load(open("config.json")).get("dispatchWatchdog"):
            print("watchdog off")
            return
        problem = check()
        if not problem:
            print("watchdog ok")
            return
        print(f"watchdog alert: {problem}")
        r = requests.post(f'https://ntfy.sh/{os.environ["NTFY_TOPIC"]}', data=problem.encode(),
                          headers={"Title": "class-bot: seat checks slowed down", "Tags": "warning"},
                          timeout=20)
        print(f"watchdog ntfy: HTTP {r.status_code}")
    except Exception as e:
        # type name only: requests error text includes the URL, which holds the topic
        print(f"watchdog error: {type(e).__name__}", file=sys.stderr)


if __name__ == "__main__":
    main()
