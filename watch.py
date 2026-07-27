#!/usr/bin/env python3
# watch.py - multi-target CofC seat watcher. Fires ntfy push on closed->open only.
# Usage: python watch.py            (one pass; loop it via Task Scheduler or GH Actions cron)
#        python watch.py --loop 60  (local daemon, seconds between passes)
# Config: config.json (local file, or CONFIG_URL env -> GitHub raw, editable from phone)

import argparse, json, os, sys, time
import requests
from discover import session, fetch_all, classify, meets

STATE = os.environ.get("STATE_FILE", "state.json")
CONFIG_URL = os.environ.get("CONFIG_URL")


def load_config():
    if CONFIG_URL:
        return requests.get(CONFIG_URL, timeout=20,
                            headers={"Cache-Control": "no-cache"}).json()
    return json.load(open("config.json"))


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    json.dump(st, open(STATE, "w"))


def matches(sec, t):
    """True if section satisfies a watch target."""
    if t.get("crns"):
        return sec.get("courseReferenceNumber") in t["crns"]
    if t.get("subject") and t["subject"] != "*" and sec.get("subject") != t["subject"]:
        return False
    if t.get("courseNumber") and sec.get("courseNumber") != t["courseNumber"]:
        return False
    if t.get("partOfTerm") and str(sec.get("partOfTerm")) != str(t["partOfTerm"]):
        return False
    if t.get("asyncOnly") and classify(sec) != "ASYNC":
        return False
    if t.get("maxCredits") and float(sec.get("creditHourLow") or 0) > t["maxCredits"]:
        return False
    return True


def notify(cfg, title, body, url):
    topic = cfg["ntfyTopic"]
    try:
        requests.post(f"https://ntfy.sh/{topic}", data=body.encode(),
                      headers={"Title": title, "Priority": "urgent",
                               "Tags": "school", "Click": url}, timeout=20)
    except Exception as e:
        print(f"notify fail: {e}", file=sys.stderr)


def reg_url(term, crn):
    base = os.environ.get("BANNER", "https://bannerweb.cofc.edu")
    return f"{base}/StudentRegistrationSsb/ssb/classRegistration/classRegistration"


def one_pass(cfg, st):
    term = cfg["term"]
    s = session(term)
    secs = fetch_all(s, term)
    hits = 0
    for t in cfg["watch"]:
        for sec in secs:
            if not matches(sec, t):
                continue
            crn = sec.get("courseReferenceNumber")
            open_now = (sec.get("seatsAvailable") or 0) > 0
            was_open = st.get(crn, {}).get("open", False)
            st[crn] = {"open": open_now, "seats": sec.get("seatsAvailable")}
            if open_now and not was_open:
                hits += 1
                label = f'{sec.get("subject")} {sec.get("courseNumber")}-{sec.get("sequenceNumber")}'
                prof = ", ".join(f.get("displayName", "") for f in (sec.get("faculty") or []))
                notify(cfg,
                       f'SEAT: {label} ({t.get("label", "watch")})',
                       f'{sec.get("courseTitle")}\nCRN {crn} | {sec.get("seatsAvailable")} open\n'
                       f'{prof}\n{classify(sec)} | part {sec.get("partOfTerm")}',
                       reg_url(term, crn))
    save_state(st)
    print(f"{time.strftime('%H:%M:%S')} scanned {len(secs)} sections, {hits} new openings")
    return hits


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--loop", type=int, default=0)
    a = p.parse_args()
    while True:
        try:
            one_pass(load_config(), load_state())
        except Exception as e:
            print(f"pass failed: {e}", file=sys.stderr)
        if not a.loop:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
