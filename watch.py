#!/usr/bin/env python3
"""
Poll Banner for open seats in the sections listed in config.json and push an
alert (ntfy / email) the instant one opens up. Generalizes Watch-Seats.ps1 /
cloud/check_seats.sh to any number of subjects/courses/CRNs on any Banner
school, driven by candidates you found with discover.py.

  export BANNER=ssb.cofc.edu
  python watch.py                 # single check - good for cron / GitHub Actions
  python watch.py --loop 300      # keep running, checking every 300s
"""
import argparse
import json
import os
import smtplib
import sys
import time
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText

from banner import BannerClient

REGISTER_LINK_PATH = "/term/termSelection?mode=search"


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_config(path):
    if not os.path.exists(path):
        sys.exit(f"{path} not found. Run discover.py, then create config.json (see README).")
    with open(path) as f:
        return json.load(f)


def send_ntfy(topic, title, body):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=body.encode(),
        headers={"Title": title, "Priority": "urgent", "Tags": "rotating_light"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


def send_email(cfg, title, body):
    msg = MIMEText(body)
    msg["Subject"] = title
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(cfg["from"], cfg["app_password"])
        smtp.sendmail(cfg["from"], [cfg["to"]], msg.as_string())


def alert(config, title, body):
    notify = config.get("notify", {})

    ntfy_cfg = notify.get("ntfy", {})
    if ntfy_cfg.get("enabled"):
        try:
            send_ntfy(ntfy_cfg["topic"], title, body)
        except Exception as exc:
            log(f"  [ntfy failed: {exc}]")

    email_cfg = notify.get("email", {})
    if email_cfg.get("enabled"):
        try:
            send_email(email_cfg, title, body)
        except Exception as exc:
            log(f"  [email failed: {exc}]")

    print(f"\n=== {title} ===\n{body}\n")


def check_once(client, config, host, notified):
    term = config["term"]
    link = f"https://{host}{REGISTER_LINK_PATH}"

    for watch in config["watch"]:
        label = watch.get("label") or f"{watch.get('subject', '')} {watch.get('course', '')}".strip()
        crns = set(watch.get("crns") or [])

        page = client.search(term, subject=watch.get("subject", ""), course=watch.get("course", ""), page_max=500)
        sections = page.get("data") or []
        if crns:
            sections = [s for s in sections if s.get("courseReferenceNumber") in crns]

        open_now = [s for s in sections if int(s.get("seatsAvailable") or 0) > 0]
        open_keys = {s["courseReferenceNumber"] for s in open_now}
        previously_open = notified.get(label, set())
        log(f"{label}: checked {len(sections)} section(s), {len(open_now)} open")

        for s in open_now:
            crn = s["courseReferenceNumber"]
            if crn not in previously_open:
                title = f"SEAT OPEN: {s.get('subject')} {s.get('courseNumber')}-{s.get('sequenceNumber')}"
                body = (
                    f"{s.get('subject')} {s.get('courseNumber')}-{s.get('sequenceNumber')} "
                    f"(CRN {crn}) has {s.get('seatsAvailable')} seat(s) open!\n"
                    f"Register: {link}"
                )
                alert(config, title, body)

        notified[label] = open_keys


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--loop", type=int, metavar="SECONDS", help="keep running, polling every SECONDS")
    args = parser.parse_args()

    host = os.environ.get("BANNER")
    if not host:
        sys.exit("Set BANNER to your school's Banner host first, e.g.:\n  export BANNER=ssb.cofc.edu")

    config = load_config(args.config)
    poll_seconds = args.loop or config.get("poll_seconds", 300)

    client = BannerClient(host)
    notified = {}

    log(f"Watching {len(config.get('watch', []))} section group(s) on {host}, term {config.get('term')}")
    while True:
        try:
            client.prime(config["term"])
            check_once(client, config, host, notified)
        except Exception as exc:
            log(f"check failed: {exc} (will retry)")

        if args.loop is None:
            break
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
