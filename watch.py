#!/usr/bin/env python3
# watch.py - multi-target CofC seat watcher. Fires ntfy push on closed->open only.
# Usage: python watch.py            (one pass; loop it via Task Scheduler or GH Actions cron)
#        python watch.py --loop 60  (local daemon, seconds between passes)
# Config: config.json (local file, or CONFIG_URL env -> GitHub raw, editable from phone)

import argparse, json, os, sys, time
import requests
from discover import session, fetch_all, classify, meets
import plans as plan_rule

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


def notify(cfg, title, body, url, priority="urgent"):
    # env only, no fallback: a silent no-op alert path is worse than a loud crash
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        sys.exit("FATAL: NTFY_TOPIC unset. Refusing to run blind.")
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode(),
                          headers={"Title": title, "Priority": priority,
                                   "Tags": "school", "Click": url}, timeout=20)
    except Exception as e:
        # type name only: requests error text includes the URL, which holds the topic
        print(f"notify fail: {type(e).__name__}", file=sys.stderr)
        return False
    if not 200 <= r.status_code < 300:
        print(f"notify fail: HTTP {r.status_code}", file=sys.stderr)
        return False
    return True


def reg_url(term, crn):
    base = os.environ.get("BANNER", "https://ssb.cofc.edu")
    return f"{base}/StudentRegistrationSsb/ssb/classRegistration/classRegistration"


def env_target():
    """Ad-hoc target from workflow_dispatch inputs, if any were provided."""
    subj = os.environ.get("AD_HOC_SUBJECT", "").strip()
    crns = os.environ.get("AD_HOC_CRNS", "").strip()
    if not subj and not crns:
        return None
    t = {"label": "ad-hoc request"}
    if crns:
        t["crns"] = [c.strip() for c in crns.split(",") if c.strip()]
    if subj:
        t["subject"] = subj
    course = os.environ.get("AD_HOC_COURSE", "").strip()
    if course:
        t["courseNumber"] = course
    if os.environ.get("AD_HOC_ASYNC_ONLY", "").lower() == "true":
        t["asyncOnly"] = True
    return t


def fetch_watched(s, term, targets):
    """Fetch only the courses the targets name. A target with no subject needs a full scan."""
    queries = set()
    for t in targets:
        if not t.get("subject") or t["subject"] == "*":
            return fetch_all(s, term)
        queries.add((t["subject"], t.get("courseNumber") or ""))
    secs = []
    for subject, course in sorted(queries):
        filters = {"txt_subject": subject}
        if course:
            filters["txt_courseNumber"] = course
        secs += fetch_all(s, term, **filters)
    # A wrong subject or course in config.json would otherwise stop watching a CRN silently.
    found = {sec.get("courseReferenceNumber") for sec in secs}
    missing = sorted({c for t in targets for c in t.get("crns", [])} - found)
    if missing:
        print(f"WARNING: CRNs {missing} not in course results, falling back to a full scan", file=sys.stderr)
        return fetch_all(s, term)
    return secs


def one_pass(cfg, st):
    term = cfg["term"]
    extra = env_target()
    if extra:
        cfg = {**cfg, "watch": cfg["watch"] + [extra]}
    s = session(term)
    plans = cfg.get("plans")
    secs = fetch_watched(s, term, cfg["watch"] + (plan_rule.targets(plans) if plans else []))
    held = set(plans.get("registered", [])) if plans else set()
    watched = set()
    hits = failed = 0
    for t in cfg["watch"]:
        for sec in secs:
            if not matches(sec, t):
                continue
            crn = sec.get("courseReferenceNumber")
            watched.add(crn)
            seats = sec.get("seatsAvailable")
            open_now = (seats or 0) > 0
            prev = st.get(crn, {})
            was_open = prev.get("open", False)
            label = f'{sec.get("subject")} {sec.get("courseNumber")}-{sec.get("sequenceNumber")}'
            prof = ", ".join(f.get("displayName", "") for f in (sec.get("faculty") or []))
            body = (f'{sec.get("courseTitle")}\nCRN {crn} | {seats} open\n'
                    f'{prof}\n{classify(sec)} | part {sec.get("partOfTerm")}')
            delivered = True
            if open_now and not was_open:
                hits += 1
                kind = "LAST SEAT" if seats == 1 else "SEAT"
                delivered = notify(cfg, f'{kind}: {label} ({t.get("label", "watch")})', body,
                                   reg_url(term, crn))
                if not delivered:
                    failed += 1
            elif seats == 1 and prev.get("seats") != 1 and crn not in held and not sec.get("waitCount"):
                if not notify(cfg, f'LAST SEAT: {label} ({t.get("label", "watch")})', body,
                              reg_url(term, crn)):
                    failed += 1
                    seats = prev.get("seats")  # old count stays, so the next poll retries
            # undelivered alert stays open=False, so the next poll sees closed->open and retries
            st[crn] = {"open": open_now and delivered, "seats": seats}
    if plans:
        def send(title, body, priority):
            nonlocal failed
            ok = notify(cfg, title, body, reg_url(term, ""), priority)
            failed += not ok
            return ok
        plan_rule.check(plans, secs, st, send, watched)
    save_state(st)
    print(f"{time.strftime('%H:%M:%S')} scanned {len(secs)} sections, {hits} new openings, {failed} alerts failed")
    return hits


def main():
    # fail fast, before any scanning: a zero-hit run with the secret missing
    # would otherwise report "healthy" while silently having no delivery path
    if not os.environ.get("NTFY_TOPIC"):
        sys.exit("FATAL: NTFY_TOPIC unset. Refusing to run blind.")
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
